import abc
from riaps.run.comp import Component

from interfaces.MQTT import RiapsMQThread


class MqttDevice(Component):
    def __init__(self, mqtt_config):
        super(MqttDevice, self).__init__()
        self.logger.info("MQTT - starting")
        self.thread = None
        self.mqtt_config = mqtt_config

    def handleActivate(self):
        if self.thread is None:  # First clock pulse
            self.thread = RiapsMQThread(self.trigger, self.logger, self.mqtt_config)  # Inside port
            self.thread.start()  # Start
            self.trigger.set_identity(self.thread.get_identity(self.trigger))
            self.trigger.activate()

    def __destroy__(self):
        self.logger.info("__destroy__")
        if self.thread:
            self.thread.deactivate()
            self.thread.terminate()
            self.thread.join()
        self.logger.info("__destroy__ed")

    def send_mqtt(self, msg: dict):
        """ This puts the message on the inside channel,
        so when `handle_polled_sockets` is called it picks up this message
        and publishes it to the broker."""
        self.trigger.send_pyobj(msg)


    @abc.abstractmethod
    def on_trigger(self):  # Internally triggered operation
        """
        This is triggered when a message is received from the mqtt broker.
        Specifically the handle_broker_message function sends it.
        """
        pass


