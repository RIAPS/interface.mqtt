# MQTT + Node Red Example Application

## Overview
This is an example of how to use the device component implementation of MQTT for the RIAPS platform.

The structure of sent message:

```python
import json
payload = {"key": "value"}
msg = {
   "topic": str,  # e.g., "riaps/data"
   "data": json.dumps(payload)}  # e.g., {}
```
received messages are dicts with the keys and values set by the external application.

* Incoming Message flow

|         | External        | MQTT Broker | MQTT.py                 | Application(MqttDevice) |
|---------|-----------------|-------------|-------------------------|-------------------------|
| msg     | Json str        | Json str    | MQTTMessage obj &darr;  |                         | 
| payload | Json str &uarr; |             | Json str => python dict | python dict             |

* Outgoing Messages

|         | Application(MqttDevice)        | MQTT.py                        | MQTT Broker | External                    |
|---------|--------------------------------|--------------------------------|-------------|-----------------------------|
| msg     | python dict                    | python dict => MQTTMessage obj | Json str    | Json str => required format |
| payload | python dict => Json str &uarr; |                                |             |                             | 


# Application Developer Notes

An application using an MQTT device requires:
1. A device configuration YAML file e.g., `cfg/mqtt.yaml`
2. Specification of the device in the application's (dot)riaps file
3. A python class file implementing the MQTT device component specified in the (dot)riaps file. 

### MQTT Device Configuration YAML File
The MQTT device configuration YAML file defines:
1. the parameters required to connect to an MQTT server (see [link](https://pypi.org/project/paho-mqtt/#connect-reconnect-disconnect)). 
2. A list of topics to subscribe to specified under `subscriptions`

### RIAPS Application File
The (dot)riaps file must contain a device that takes a configuration file and provides an inside port called trigger. 
```
device MQTT(config) {
		inside trigger; 
	}
```

### Python MQTT Device Class 

The python class file implementing the MQTT device component specified in the (dot)riaps file inherits from `MqttDevice` class from ` riaps.interfaces.mqtt/MqttDevice.py` and must implement the `on_trigger` handler.
```python
import json
from riaps.interfaces.mqtt.MqttDevice import MqttDevice
...
class MQTT(MqttDevice):
    ...
    def on_trigger(self):
        msg = self.trigger.recv_pyobj()  ## Receive message from mqtt broker
        self.logger.info('on_trigger():%r' % msg)
        # --- message handling logic here ---

    def some_function(self):
        payload = {"data": "some_data"}
        msg = {"data": json.dumps(payload),
               "topic": "some/topic"}
        self.send_mqtt(msg) 
```

The `on_trigger` handler receives the payload of messages sent from the MQTT broker. The payload originally sent to the broker is expected to be a json formatted string that can be converted to a python dictionary with the `json.loads()` function. The output of this function is what is received by the `on_trigger` handler, i.e., a python dictionary. 

#### Sending Messages
Messages can be sent to the MQTT broker using the `send_mqtt` function which takes a dictionary of the form:
```python
msg = {"data": "[your data]",
       "topic": "[your topic]"}
```

The value `[your topic]` needs to match the subscription of the external service that will receive the message, for example, `"riaps/data"`. `[your data]` is the actual message to send. If not given, or set to `"None"`, a zero length message will be used. Passing an int or float will result in the payload being converted to a string representing that number. If you wish to send a true int/float, use `struct.pack()` to create the payload you require. If you want to send a python dictionary first convert it to a string using `json.dumps(payload)`. 

# How to Use this Example

1. Start node red
   1. ```commandline
      $ node-red
      ```
   2. browse to http://127.0.0.1:1880
2. Launch the application using `riaps_ctrl`
 
Elements of the SVG image will be updated by the application, specifically the colors on some relays as well as text by some elements. Additionally, the amplitude of the sine wave displayed in the chart can be set using the `Amplitude` selector and pressing the `SEND AMPLITUDE` button. The `Scenario Control` sends a message, but has no feedback.


# Tests for Library Developers
When installing this package, use the following command to include additional testing packages:
```commandline
sudo python3 -m pip install .[dev]
```

To run the included test example, the `interface.mqtt/example/mqnr.depl` and `required_clients` in `interface.mqtt/tests/test_mqtt.py` must be updated to reflect your canbus device IP address. Then tests can be run with:
```commandline
pytest -s -v .
```

# Troubleshooting

# Package Notes 

# Notes
How to use Node Red JS tabsheet:
[Link](https://github.com/bartbutenaers/node-red-contrib-ui-svg/blob/master/docs/tabsheet_js.md)

# Roadmap
