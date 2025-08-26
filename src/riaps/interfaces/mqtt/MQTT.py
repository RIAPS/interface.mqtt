from pydantic import BaseModel, ValidationError
import abc
import json
import os
import paho.mqtt.client as mqtt
import socket
import threading
import time
import yaml
import zmq


def load_mqtt_config(path_to_config):
    with open(path_to_config, "r") as cfg_file:
        cfg = yaml.safe_load(cfg_file)
        return cfg


# Define a Pydantic model for the expected MQTT message
class MqttMessage(BaseModel):
    data: object  # Accept any JSON-serializable object
    topic: str


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
        self.fileno_to_socket = {}
        self.poller = (
            zmq.Poller()
        )  # Set up poller to wait for messages from either side

        self.broker_connect_config = config["broker_connect_config"]
        self.topics = config["topics"]

    @staticmethod
    def on_connect(client, this, flags, rc):
        """Handler passed to mqtt client"""
        if rc != 0:
            exit(rc)
        else:
            this.logger.info("mqtt cb: connected with result code " + str(rc))
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

    @staticmethod
    def on_publish(client, userdata, mid):
        pass
        # userdata.logger.info(f"on_publish"
        #                      f"client: {client}"
        #                      f"userdata: {userdata}"
        #                      f"mid: {mid}")

    @abc.abstractmethod
    def handle_broker_message(self, msg):
        """This is overwritten by the riaps class"""
        self.logger.info(f"handle_broker_message: {msg}")

    def _handle_polled_sockets(self, socks):
        for fileno, event in socks.items():
            sock = self.fileno_to_socket.get(fileno, None)
            if event & zmq.POLLERR:
                self.logger.error(
                    f"Socket error on fileno={fileno}. Attempting reconnect."
                )
                if sock:
                    try:
                        self.poller.unregister(sock)
                    except Exception:
                        pass
                    try:
                        sock.close()
                    except Exception:
                        pass
                if fileno == self.broker_fileno:
                    self.broker = None
                    self.broker_fileno = None
                continue
            if fileno == self.broker_fileno and event == zmq.POLLIN:
                self.data_recv = None
                self.client.loop_read()
                self.client.loop_write()
                self.client.loop_misc()
                if self.data_recv:
                    try:
                        msg = json.loads(self.data_recv)
                        self.handle_broker_message(msg)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to decode message: {e} | payload: {self.data_recv!r}"
                        )
                    self.data_recv = None

    def run(self):
        try:
            self.logger.info("MQThread starting")
            self._mqtt_client()
            self._mqtt_connect()
            self._poll()
        except Exception as e:
            self.logger.error(
                f"MQThread encountered an unexpected exception and will exit: {e}",
                exc_info=True,
            )

    def _poll(self):
        self.logger.info(f"Start polling")
        while not self.terminated.is_set():
            if not self.active.is_set():
                self.logger.info("MQThread waiting for active")
            self.active.wait(None)  # Pauses the loop until active is set
            if self.active.is_set():  # Check again in case terminate was called
                # If broker is lost, try to reconnect
                if self.broker is None:
                    self.logger.info("Broker lost, attempting to reconnect...")
                    self._mqtt_connect()
                else:
                    socks = dict(
                        self.poller.poll(1000)
                    )  # Run the poller w/ 1 sec timeout
                    (
                        self._handle_polled_sockets(socks)
                        if len(socks) > 0
                        else self.logger.info("MQThread no new message")
                    )
        self.logger.info("MQThread ended")

    def _mqtt_client(self):
        self.logger.info("Creating mqtt client")
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_socket_open = self.on_socket_open
        self.client.on_publish = self.on_publish
        self.client.user_data_set(self)

    def send(self, topic, data, qos):
        try:
            # Validate and serialize using Pydantic
            msg = MqttMessage(data=data, topic=topic)
            payload = msg.model_dump_json()
        except ValidationError as e:
            self.logger.error(f"MQTT send validation error: {e}")
            raise
        MQTTMessageInfo = self.client.publish(
            topic, payload, qos=qos
        )  # pub to the broker
        return MQTTMessageInfo

    def _mqtt_connect(self):
        self.logger.info("Connecting to mqtt broker")
        try:
            rc = self.client.connect(**self.broker_connect_config)
        except ValueError as e:
            self.logger.error(e)
        except socket.error as e:
            self.logger.error(f"Is Mqtt broker running?: {e}")
            time.sleep(1)
            self._mqtt_connect()
        except Exception as e:
            self.logger.error(f"UNEXPECTED ERROR, ADD TO EXCEPTION HANDLER: {e}")

        while self.broker is None:
            """Wait for broker to be active"""
            self.logger.info(f"self.broker: {self.broker}")
            self.client.loop_read()
            self.client.loop_write()
            self.client.loop_misc()
            if self.broker is None:
                self.logger.info("Waiting for broker to be active")
                time.sleep(1)

        self.broker_fileno = self.broker.fileno()
        self.poller.register(self.broker, zmq.POLLIN)  # broker socket
        self.fileno_to_socket[self.broker_fileno] = self.broker

    def activate(self):
        self.active.set()
        self.logger.info("MQThread activated")

    def deactivate(self):
        self.active.clear()
        self.logger.info("MQThread deactivated")

    def terminate(self):
        self.active.set()
        self.terminated.set()
        self.logger.info("MQThread terminating")


class RiapsMQThread(MQThread):
    def __init__(self, trigger, logger, config):
        super().__init__(logger, config)
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
        # TODO: instead of sending on plug this could also be sent on
        #  a topic specific riaps port.
        #  However, that seems more complex and error prone since it
        #  requires modifying the .riaps file to add a port for every
        #  subscribed topic.

        # Get message from the broker and send it to the plug.
        # Which causes on_trigger to fire.

    def _handle_polled_sockets(self, socks):
        if self.plug in socks and socks[self.plug] == zmq.POLLIN:
            # Input from riaps component via the inside port (trigger). Publish to the broker
            msg = self.plug.recv_pyobj()
            self.logger.debug("MQThread pub(%r)" % msg)
            data = msg["data"]
            topic = msg["topic"]
            MQTTMessageInfo = self.client.publish(
                topic, data, qos=2
            )  # pub to the broker
            rc = MQTTMessageInfo.rc
            if rc != 0:
                self.logger.error(
                    f"Failed to send message to broker. rc: {mqtt.error_string(rc)}"
                )
                if (
                    rc == mqtt.MQTT_ERR_NO_CONN
                ):  # if the broker goes down, try to reconnect
                    self._mqtt_connect()

        super(RiapsMQThread, self)._handle_polled_sockets(socks)

    def run(self):
        self.logger.info("MQThread starting")

        self.plug = self.trigger.setupPlug(
            self
        )  # Ask RIAPS port to make a plug (zmq socket) for this end
        self.poller.register(
            self.plug, zmq.POLLIN
        )  # plug socket (connects to trigger port of parent device comp)

        super(RiapsMQThread, self).run()
