import pytest
import socket
from unittest.mock import MagicMock, patch
from src.riaps.interfaces.mqtt.MQTT import MQThread, MqttMessage


class DummyLogger:
    def info(self, msg):
        pass

    def error(self, msg):
        pass

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass


@pytest.fixture
def mqtt_config():
    return {
        "broker_connect_config": {"host": "localhost", "port": 18883, "keepalive": 60},
        "topics": {"subscriptions": ["test/topic"]},
    }


# 1. Test successful initial connection and message send
@patch("paho.mqtt.client.Client")
def test_successful_connect_and_send(mock_client, mqtt_config):
    logger = DummyLogger()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()
    mock_client.return_value.connect.return_value = 0
    thread.broker = MagicMock()
    thread.broker.fileno.return_value = 1
    thread.poller = MagicMock()
    thread.fileno_to_socket = {}
    thread._mqtt_connect()
    # Simulate send
    thread.client.publish.return_value = MagicMock(rc=0)
    result = thread.send("test/topic", {"foo": "bar"}, qos=1)
    assert result.rc == 0


# 2. Test handling of invalid broker config (connection error)
@patch("paho.mqtt.client.Client")
def test_connect_invalid_config(mock_client, mqtt_config):
    logger = DummyLogger()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()
    mock_client.return_value.connect.side_effect = socket.error("fail")
    assert not thread._mqtt_connect()


# 3. Test socket error handling in _handle_polled_sockets
@patch("paho.mqtt.client.Client")
def test_handle_polled_sockets_socket_error(mock_client, mqtt_config):
    logger = DummyLogger()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()
    sock = MagicMock()
    fileno = 42
    thread.fileno_to_socket = {fileno: sock}
    thread.broker_fileno = fileno
    thread.broker = sock
    thread.poller = MagicMock()
    socks = {fileno: 4}  # zmq.POLLERR == 4
    thread._handle_polled_sockets(socks)
    assert thread.broker is None
    assert thread.broker_fileno is None


# 4. Test clean shutdown and resource cleanup
@patch("paho.mqtt.client.Client")
def test_terminate_cleans_up_sockets(mock_client, mqtt_config):
    logger = DummyLogger()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()
    sock1 = MagicMock()
    sock2 = MagicMock()
    thread.fileno_to_socket = {1: sock1, 2: sock2}
    thread.poller = MagicMock()
    thread.terminate()
    assert thread.fileno_to_socket == {}
    assert thread.terminated.is_set()
    assert thread.active.is_set()
