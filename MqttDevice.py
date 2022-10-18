from riaps.run.comp import Component

import interface.MQTT


class MqttDevice(Component):
    def __init__(self, mqtt_config):
        super(MqttDevice, self).__init__()
        self.logger.info("MQTT - starting")
        self.thread = None
        self.mqtt_config = mqtt_config

    def on_data(self):
        if self.thread is None:  # First clock pulse
            self.thread = interface.MQTT.MQThread(self.trigger, self.logger, self.mqtt_config)  # Inside port
            self.thread.start()  # Start
            self.trigger.set_identity(self.thread.get_identity(self.trigger))
            self.trigger.activate()
        data = self.data.recv_pyobj()  # Receive data
        self.logger.info('on_data():%r' % data)
        self.trigger.send_pyobj(data)

    def __destroy__(self):
        self.logger.info("__destroy__")
        if self.thread:
            self.thread.deactivate()
            self.thread.terminate()
            self.thread.join()
        self.logger.info("__destroy__ed")

    def on_trigger(self):  # Internally triggered operation (
        msg = self.trigger.recv_pyobj()  # Receive message from internal thread
        self.logger.info('on_trigger():%r' % msg)
        self.ampl.send_pyobj(msg)  # Send it to the echo server

