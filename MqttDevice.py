import abc
from riaps.run.comp import Component

from interfaces.MQTT import RiapsMQThread


class MqttDevice(Component):
    def __init__(self, mqtt_config):
        super(MqttDevice, self).__init__()
        self.logger.info("MQTT - starting")
        self.thread = None
        self.mqtt_config = mqtt_config

    def on_data(self):
        if self.thread is None:  # First clock pulse
            self.thread = RiapsMQThread(self.trigger, self.logger, self.mqtt_config)  # Inside port
            self.thread.start()  # Start
            self.trigger.set_identity(self.thread.get_identity(self.trigger))
            self.trigger.activate()
        data = self.data.recv_pyobj()  # Receive data from SGen
        self.logger.info('on_data():%r' % data)
        msg = {"data": data,
               "topic": "riaps/data"}
        self.trigger.send_pyobj(msg)
        # This puts the message on the plug.
        # So when `handle_polled_sockets` is called it picks up this message
        # and publishes it to the broker.

    def __destroy__(self):
        self.logger.info("__destroy__")
        if self.thread:
            self.thread.deactivate()
            self.thread.terminate()
            self.thread.join()
        self.logger.info("__destroy__ed")

    @abc.abstractmethod
    def on_trigger(self):  # Internally triggered operation
        pass


