# interface.mqtt

## Overview
The library provides a device component implementation of MQTT for the RIAPS platform.
An example of an application using this library is found in the `example` folder.
The designed use model is to include in the (dot)riaps application specification file a device component with the following content in addition to other elements required by the application:

## Dependencies
* [MQTT Server (e.g., FlashMQ)](https://www.flashmq.org/about/)
These are required on the RIAPS `ctrl` node. (This is included by default in the development VM image)

## Optional Dependencies
* [Node-RED](https://nodered.org/docs/getting-started/local)(This is included by default in the development VM image)
