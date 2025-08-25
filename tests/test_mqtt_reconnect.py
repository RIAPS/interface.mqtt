import threading
import time
import pytest
from unittest import mock
from riaps.interfaces.mqtt.MQTT import MQThread


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
    broker_connect_config = {"host": "localhost", "port": 1883}
    topics = {"subscriptions": ["test/topic"]}

    def __getitem__(self, key):
        return getattr(self, key)


def test_mqtt_reconnect_on_broker_restart():
    logger = DummyLogger()
    config = DummyConfig()
    with mock.patch("paho.mqtt.client.Client") as MockClient:
        instance = MockClient.return_value
        # Simulate broker down: connect raises socket.error first, then succeeds
        instance.connect.side_effect = [OSError("broker down"), 0]
        instance.loop_read.return_value = None
        instance.loop_write.return_value = None
        instance.loop_misc.return_value = None
        instance.subscribe.return_value = (0, 1)
        instance.publish.return_value = mock.Mock(rc=0)
        # Patch fileno and socket
        dummy_sock = mock.Mock()
        dummy_sock.fileno.return_value = 42
        thread = MQThread(logger, config)
        thread.poller = mock.Mock()
        thread.poller.poll.side_effect = [{}, {}, {}]  # No messages

        # Make sure the mock client is set up
        thread._mqtt_client()

        # Start thread in background
        t = threading.Thread(target=thread._mqtt_connect)
        t.start()
        time.sleep(0.2)
        # Simulate broker socket open after connect succeeds
        thread.on_socket_open(instance, thread, dummy_sock)
        # After first failure, should retry and succeed
        t.join(timeout=2)
        assert instance.connect.call_count == 2
        # Now simulate sending a message
        result = thread.send("test/topic", "payload", qos=0)
        assert result.rc == 0
