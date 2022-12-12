# interface.mqtt

[Gabor's Instructions](https://github.com/RIAPS/example.mqnr/blob/accff50375c904a468dbd4c22b7c07f26b8e62fe/MQTTNodeRed/README.md)

## Setup
### Install mqtt broker and python module:
1. ```wget https://www.flashmq.org/wp-content/uploads/2021/10/flashmq-repo.gpg```
2. `sudo mv flash-repo.gpg /etc/apt/keyrings`
3. ```echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/flashmq-repo.gpg] http://repo.flashmq.org/apt focal main" | sudo tee /etc/apt/sources.list.d/flashmq.list > /dev/null```
4. add `allow_anonymous true` to `/etc/flashmq/flashmq.conf`
5. `sudo systemctl restart flashmq.service` so that `allow_anonymous` takes effect.
6. ```sudo python3 -m pip install paho-mqtt```

### Start node red
1. `$ node-red` browse to http://127.0.0.1:1880

### Useful documentation
How to use Node Red JS tabsheet:
[Link](https://github.com/bartbutenaers/node-red-contrib-ui-svg/blob/master/docs/tabsheet_js.md)


## App Developer Notes

* (dot)riaps file  must contain a device that takes a configuration file and provide an inside port called trigger. 
```
device MQTT(config) {
		inside trigger; 
	}
```
* The python implementation of the MQTT device component specified in the (dot)riaps file inherits from `MqttDevice` class in `interfaces/MqttDevice.py` and must implement the `on_trigger` handler. 
```python
from interfaces.MqttDevice import MqttDevice
...
class MQTT(MqttDevice):
    ...
    def on_trigger(self):
        msg = self.trigger.recv_pyobj()  ## Receive message from mqtt broker
        self.logger.info('on_trigger():%r' % msg)
```

The `on_trigger` handler receives the payload of messages sent from the mqtt broker. The payload originally send to the broker is expected to be a json formatted string that can be converted to a python dictionary with the `json.loads()` function. The output of this function is what is received by the `on_trigger` handler, i.e., a python dictionary. 
The topics subscribed to by the riaps device component are specified in the `cfg/mqtt.yaml` file under subscriptions. 
This file also specifies the ip and port of the mqtt broker. 



Similarly, to send a message to the mqtt broker there is a `send_mqtt` function. This function takes a python dictionary of the form:
```python
msg = {"data": "[your data]",
       "topic": "[your topic]"}
```

The value [your topic] needs to match the subscription of the external service that will receive the message, for example, `"riaps/data"`. [your data] is the actual message to send. If not given, or set to None a zero length message will be used. Passing an int or float will result in the payload being converted to a string representing that number. If you wish to send a true int/float, use struct.pack() to create the payload you require. If you want to send a python dictionary first convert it to a string using `json.dumps(payload)`. For example:

```python
import json
...
class SomeClass:
    def some_function(self):
        gen1_power = 0
        payload = {"command": "update_text",
                   "selector": "GEN1_text",
                   "text": f"P: {gen1_power}"}
        msg = {"data": json.dumps(payload),
               "topic": "riaps/ctrl"}
        self.send_mqtt(msg) 
```
