import asyncio
import json
import structlog
import threading
import time
import pytest
from amqtt.broker import Broker
import paho.mqtt.client as paho
from riaps.interfaces.mqtt.MQTT import MQThread


class BrokerController:
    def __init__(self, config):
        self.config = config
        self.loop = None
        self.broker = None
        self.thread = None

    def start(self):
        if self.loop is not None and not self.loop.is_closed():
            return  # Already running
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.broker = Broker(self.config, loop=self.loop)

        def run():
            self.loop.run_until_complete(self.broker.start())
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        time.sleep(1)

    def stop(self):
        if self.loop is None or self.loop.is_closed():
            return
        fut = asyncio.run_coroutine_threadsafe(self.broker.shutdown(), self.loop)
        fut.result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()
        self.loop = None
        self.broker = None
        self.thread = None


@pytest.fixture(scope="module")
def amqtt_broker_controller():
    config = {
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:18883"}},
        "sys_interval": 0,
        "topic-check": {"enabled": False},
    }
    controller = BrokerController(config)
    controller.start()
    yield controller
    if controller.thread:
        controller.stop()


class DummyLogger:
    def info(self, msg):
        pass

    def error(self, msg):
        pass

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass


class DummyConfig:
    broker_connect_config = {"host": "127.0.0.1", "port": 18883, "keepalive": 5}
    topics = {"subscriptions": ["test/integration"]}

    def __getitem__(self, key):
        return getattr(self, key)


def test_mqthread_with_real_broker(amqtt_broker_controller):
    logger = structlog.get_logger("test")
    config = DummyConfig()
    received = []

    def on_message(client, userdata, msg):
        msg = json.loads(msg.payload)
        received.append(msg)

    sub_client = paho.Client()
    sub_client.connect("127.0.0.1", 18883, 5)
    sub_client.subscribe("test/integration")
    sub_client.on_message = on_message
    sub_client.loop_start()

    thread = MQThread(logger, config)
    thread.start()
    thread.activate()
    time.sleep(1)

    thread.send("test/integration", "hello world", qos=0)
    time.sleep(1)

    thread.terminate()
    thread.join()
    sub_client.loop_stop()
    sub_client.disconnect()

    assert "hello world" in received[0]["data"]


def test_mqthread_broker_restart(amqtt_broker_controller):
    logger = structlog.get_logger("test")

    config = DummyConfig()
    received = []

    def on_message(client, userdata, msg):
        received.append(msg.payload.decode())

    sub_client = paho.Client()
    sub_client.connect("127.0.0.1", 18883, 5)
    sub_client.subscribe("test/integration")
    sub_client.on_message = on_message
    sub_client.loop_start()

    thread = MQThread(logger, config)
    thread.start()
    thread.activate()
    time.sleep(1)

    # Send a message (should succeed)
    thread.send("test/integration", "before restart", qos=0)
    time.sleep(1)

    # Stop the broker for 10 seconds
    amqtt_broker_controller.stop()
    print(f"Stop the broker for 10 seconds")
    time.sleep(10)
    amqtt_broker_controller.start()
    time.sleep(2)  # Give time for reconnect

    # Try to send a message after broker restart
    thread.send("test/integration", "after restart", qos=0)
    time.sleep(2)

    thread.terminate()
    thread.join()
    sub_client.loop_stop()
    sub_client.disconnect()

    print("Received:", received)
    print(f"broker?: {thread.broker is not None}")
    # Optionally assert or just observe
