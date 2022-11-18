import abc
import json
import os
import paho.mqtt.client as mqtt
import socket
import threading
import time
import yaml
import zmq


class MQThread(threading.Thread):
    """
    Inner MQTT thread
    """
    def __init__(self, logger, config):
        threading.Thread.__init__(self, daemon=True)
        self.client = None
        self.logger = logger
        self.active = threading.Event()
        self.active.clear()
        self.waiting = threading.Event()
        self.terminated = threading.Event()
        self.terminated.clear()
        self.broker = None
        self.broker_fileno = None
        # self.poller = None
        self.poller = zmq.Poller()  # Set up poller to wait for messages from either side

        try:
            if os.path.exists(config):
                # Load config file
                with open(config, 'r') as cfg_file:
                    cfg = yaml.safe_load(cfg_file)
                    self.broker_connect_config = cfg["broker_connect_config"]
                    self.topics = cfg["topics"]
            else:
                self.logger.critical(f"Configuration file does not exist:{config}")
        except OSError:
            self.logger.critical(f"File I/O error:{config}")
    
    @staticmethod
    def on_connect(client, this, flags, rc):
        """Handler passed to mqtt client"""
        if rc != 0:
            exit(rc)
        else:
            this.logger.info("mqtt cb: connected with result code "+str(rc))
            # client.subscribe('riaps/cmd')
            for topic in this.topics["subscriptions"]:
                client.subscribe(topic)
    
    @staticmethod
    def on_socket_open(client, this, sock):
        """Handler passed to mqtt client"""
        this.logger.info("mqtt cb: socket open (%r) %r" % (client, sock))
        this.broker = sock 
        
    @staticmethod
    def on_message(client, this, msg):
        """Handler passed to mqtt client"""
        # stores received message into data_recv class variable.
        # TODO: This seems like it may not be the desired behavior.
        #  What if there are multiple messages? Then this.data_recv could be overwritten before it is processed
        #  in the run loop.
        #  This may be fine if the call to self.client.loop_read() only picks up one message.
        #  MQTTNodeRed/interfaces/MQTT.py:141
        this.logger.info(f"Message from broker: {msg.topic} {str(msg.payload)}")
        this.data_recv = msg.payload

    @abc.abstractmethod
    def handle_broker_message(self, msg):
        """This is overwritten by the riaps class"""
        pass

    def handle_polled_sockets(self, socks):
        if self.broker_fileno in socks and \
                socks[self.broker_fileno] == zmq.POLLIN:  # Input from broker
            self.data_recv = None
            self.client.loop_read()
            self.client.loop_write()
            self.client.loop_misc()
            if self.data_recv:
                msg = json.loads(self.data_recv)
                self.handle_broker_message(msg)
                self.data_recv = None

    def run(self):
        self.logger.info('MQThread starting')
        self.mqtt_client()
        self.mqtt_connect()

        while 1:
            self.active.wait(None)  # Events to handle activation/termination
            if self.terminated.is_set():
                break
            if self.active.is_set():  # If we are active
                socks = dict(self.poller.poll(1000))  # Run the poller w/ 1 sec timeout

                if len(socks) == 0:
                    self.logger.info('MQThread no new message')
                if self.terminated.is_set():
                    break
                self.handle_polled_sockets(socks)
        self.logger.info('MQThread ended')

    def mqtt_client(self):
        self.client = mqtt.Client()
        self.client.on_connect = MQThread.on_connect
        self.client.on_message = MQThread.on_message
        self.client.on_socket_open = MQThread.on_socket_open
        self.client.user_data_set(self)

    def mqtt_connect(self):
        try:
            rc = self.client.connect(**self.broker_connect_config)
        except ValueError as e:
            self.logger.error(e)
        except socket.error as e:
            self.logger.error(f"Is Mqtt broker running?: {e}")
            time.sleep(1)
            self.mqtt_connect()
        except Exception as e:
            self.logger.error(f"UNEXPECTED ERROR, ADD TO EXCEPTION HANDLER: {e}")

        while self.broker is None:
            """Wait for broker to be active"""
            self.logger.info(f"self.broker: {self.broker}")
            self.client.loop_read()
            self.client.loop_write()
            self.client.loop_misc()
            if self.broker is None:
                time.sleep(1)

        self.broker_fileno = self.broker.fileno()
        self.poller.register(self.broker, zmq.POLLIN)  # broker socket

    def activate(self):
        self.active.set()
        self.logger.info('MQThread activated')
                    
    def deactivate(self):
        self.active.clear()
        self.logger.info('MQThread deactivated')
    
    def terminate(self):
        self.active.set()
        self.terminated.set()
        self.logger.info('MQThread terminating')


class RiapsMQThread(MQThread):
    def __init__(self, trigger, logger, config):
        super(RiapsMQThread, self).__init__(logger, config)
        self.trigger = trigger  # inside RIAPS port
        self.plug = None
        self.plug_identity = None

    def get_identity(self, ins_port):
        if self.plug_identity is None:
            while True:
                if self.plug is not None:
                    self.plug_identity = ins_port.get_plug_identity(self.plug)
                    break
                time.sleep(0.1)
        return self.plug_identity
    
    def handle_broker_message(self, msg):
        self.plug.send_pyobj(msg)
        # Get message from the broker and send it to the plug.
        # Which causes on_trigger to fire.
        
    def handle_polled_sockets(self, socks):
        if self.plug in socks and socks[self.plug] == zmq.POLLIN:
            # Input from riaps component via the inside port (trigger). Publish to the broker
            msg = self.plug.recv_pyobj()
            self.logger.info('MQThread pub(%r)' % msg)
            data = msg["data"]
            topic = msg["topic"]
            MQTTMessageInfo = self.client.publish(topic, data, qos=2)  # pub to the broker
            rc = MQTTMessageInfo.rc
            if rc != 0:
                self.logger.error(f"Failed to send message to broker. rc: {mqtt.error_string(rc)}")
                if rc == mqtt.MQTT_ERR_NO_CONN:  # if the broker goes down, try to reconnect
                    self.mqtt_connect()

        super(RiapsMQThread, self).handle_polled_sockets(socks)

    def run(self):
        self.logger.info('MQThread starting')

        self.plug = self.trigger.setupPlug(self)  # Ask RIAPS port to make a plug (zmq socket) for this end
        self.poller.register(self.plug, zmq.POLLIN)  # plug socket (connects to trigger port of parent device comp)

        super(RiapsMQThread, self).run()
