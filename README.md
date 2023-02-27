# RIAPS MQTT Device Interface

## Overview
The library provides a device component implementation of MQTT for the RIAPS platform.
The intended way to use the library is to provide:
1. A device configuration YAML file e.g., `cfg/mqtt.yaml`
2. Specification of the device in the application's (dot)riaps file
3. A python class file implementing the MQTT device component specified in the (dot)riaps file. 
An example of an application using this library is found in the [`example` folder](https://github.com/RIAPS/interface.mqtt/tree/main/example).


## Dependencies
* [MQTT Server (e.g., FlashMQ)](https://www.flashmq.org/about/)
These are required on the RIAPS `ctrl` node. 
   >Note: This is included by default in the development VM image

## Optional Dependencies
* [Node-RED](https://nodered.org/docs/getting-started/local)
   >Note: This is included by default in the development VM image

# Installation

## Install RIAPS MQTT library

* On single node locally
```commandline
sudo python3 -m pip install 'riaps.interfaces.mqtt @ git+https://github.com/RIAPS/interface.mqtt.git'
```
* On cluster of nodes using python fabric
```commandline
riaps_fab sys.sudo:'"python3 -m pip install git+https://github.com/RIAPS/interface.mqtt.git"'
```

* Via cloning
```commandline
git clone https://github.com/RIAPS/interface.mqtt.git
cd interface.mqtt
sudo python3 -m pip install .
```