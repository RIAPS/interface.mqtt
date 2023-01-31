import json

from interfaces.MqttDevice import MqttDevice


class MQTT(MqttDevice):
    def __init__(self, config):
        super(MQTT, self).__init__(config)
        self.fill = "yellow"
        self.count = 0

    def on_data(self):
        data = self.data.recv_pyobj()  # Receive data from SGen
        self.logger.info('on_data():%r' % data)
        msg = {"data": data,
               "topic": "riaps/data"}
        self.send_mqtt(msg)

        self.count += 1
        if self.fill == "yellow":
            self.fill = "blue"
        else:
            self.fill = "yellow"
        payload = [
            {
                "command": "update_style",
                "selector": "#PCC1",
                "style": {"fill": self.fill}
            },
            {
                "command": "update_style",
                "selector": "#PCC2",
                "style": {"fill": self.fill}
            },
            {
                "command": "update_style",
                "selector": "#PCC3",
                "style": {"fill": self.fill}
            },
            {
                "command": "update_style",
                "selector": "#CB108",
                "style": {"fill": self.fill}
            },
            {
                "command": "update_style",
                "selector": "#CB217",
                "style": {"fill": self.fill}
            },
            {
                "command": "update_text",
                "selector": "#PCC1_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#PCC2_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#PCC3_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#C1_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#C2_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#C4_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#C5_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#C6_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#PV1_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#PV2_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#GEN1_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#GEN2_text",
                "text": f"P: {self.count}"
            },
            {
                "command": "update_text",
                "selector": "#GEN3_text",
                "text": f"P: {self.count}"
            }

        ]
        msg = {"data": json.dumps(payload),
               "topic": "riaps/ctrl"}
        self.send_mqtt(msg)  #

    def on_trigger(self):
        msg = self.trigger.recv_pyobj()  ## Receive message from mqtt broker
        self.logger.info('on_trigger():%r' % msg)

        command = msg["command"]

        if command == "amplitude":
            self.ampl.send_pyobj(msg["amplitude"])  # Send it to the echo server
        elif command == "next_scenario":
            self.logger.info(f"begin next scenario")

   
