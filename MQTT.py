import json
import os
import paho.mqtt.client as mqtt
import threading
import time
import yaml
import zmq


class MQThread(threading.Thread):
    """
    Inner MQTT thread
    """
    def __init__(self, trigger, logger, config):
        threading.Thread.__init__(self, daemon=True)
        self.client = None
        self.logger = logger
        self.active = threading.Event()
        self.active.clear()
        self.waiting = threading.Event()
        self.terminated = threading.Event()
        self.terminated.clear()
        self.trigger = trigger              # inside RIAPS port
        self.broker = None
        self.plug = None 
        self.plug_identity = None

        try:
            if os.path.exists(config):
                # Load config file
                with open(config, 'r') as cfg_file:
                    cfg = yaml.safe_load(cfg_file)
                    self.broker_connect_config = cfg["broker_connect_config"]
            else:
                self.logger.critical(f"Configuration file does not exist:{config}")
        except OSError:
            self.logger.critical(f"File I/O error:{config}")
    
    @staticmethod
    def on_connect(client, this, flags, rc):
        this.logger.info("mqtt cb: connected with result code "+str(rc))
        client.subscribe('riaps/cmd')
    
    @staticmethod
    def on_socket_open(client, this, sock):
        this.logger.info("mqtt cb: socket open (%r) %r" % (client, sock))
        this.broker = sock 
        
    @staticmethod
    def on_message(client, this, msg):
        this.logger.info("mqtt cb: recv (%r) [%r] %r" % (client, msg.topic, msg.payload))
        this.data_recv = msg.payload
        
    def get_identity(self, ins_port):
        if self.plug_identity is None:
            while True:
                if self.plug is not None:
                    self.plug_identity = ins_port.get_plug_identity(self.plug)
                    break
                time.sleep(0.1)
        return self.plug_identity
    
    def run(self):
        self.logger.info('MQThread starting')
        
        self.client = mqtt.Client()
        self.client.on_connect = MQThread.on_connect
        self.client.on_message = MQThread.on_message
        self.client.on_socket_open = MQThread.on_socket_open
        self.client.user_data_set(self)

        self.plug = self.trigger.setupPlug(self)    # Ask RIAPS port to make a plug (zmq socket) for this end
        
        self.client.connect(**self.broker_connect_config)

        while self.broker is None:
            self.client.loop_read()
            self.client.loop_write()
            self.client.loop_misc()
                
        self.broker_fileno = self.broker.fileno()
        self.poller = zmq.Poller()                  # Set up poller to wait for messages from either side
        self.poller.register(self.broker, zmq.POLLIN)  # broker socket
        self.poller.register(self.plug, zmq.POLLIN)  # plug socket (connects to trigger port of parent device comp)

        while 1:
            self.active.wait(None)                  # Events to handle activation/termination
            if self.terminated.is_set(): break
            if self.active.is_set():                # If we are active
                socks = dict(self.poller.poll(1000.0))  # Run the poller w/ 1 sec timeout
                
                if len(socks) == 0:
                    self.logger.info('MQThread timeout')
                if self.terminated.is_set(): break
                 
                if self.plug in socks and socks[self.plug] == zmq.POLLIN:   # Input from the plug
                    msg = self.plug.recv_pyobj()
                    self.logger.info('MQThread pub(%r)' % msg)
                    self.client.publish('riaps/out', msg)                    # pub to the broker
                    # self.client.loop_write()
                
                if self.broker_fileno in socks and socks[self.broker_fileno] == zmq.POLLIN:   # Input from broker
                    self.data_recv = None
                    self.client.loop_read()
                    self.client.loop_write()
                    self.client.loop_misc()
                    if self.data_recv:
                        self.logger.info(f"data_recv: {self.data_recv}")
                        msg = json.loads(self.data_recv)
                        self.logger.info('MQThread recv(%r)' % msg)
                        self.plug.send_pyobj(msg)                           # Send it to the plug
                        self.data_recv = None
               
        self.logger.info('MQThread ended')

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

