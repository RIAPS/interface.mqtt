import paho.mqtt.client as mqtt
import pytest
import socket
import time
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


# 4. Keepalive (PINGREQ and the PINGRESP deadline) runs when no data arrives (issue #4)
@patch("paho.mqtt.client.Client")
def test_poll_runs_keepalive_when_no_socket_events(mock_client, mqtt_config):
    logger = DummyLogger()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()
    thread.broker = MagicMock()
    thread.active.set()
    thread.poller = MagicMock()
    quiet_polls = 3

    def poll(timeout):
        if thread.poller.poll.call_count >= quiet_polls:
            thread.terminated.set()
        return []

    thread.poller.poll.side_effect = poll
    thread._poll()
    assert thread.client.loop_misc.call_count == quiet_polls


# 5. A disconnect reported by paho puts the loop back on the reconnect path (issue #4)
@patch("paho.mqtt.client.Client")
def test_disconnect_callback_triggers_reconnect(mock_client, mqtt_config):
    logger = DummyLogger()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()
    sock = MagicMock()
    sock.fileno.return_value = 42
    thread.broker = sock
    thread.broker_fileno = 42
    thread.fileno_to_socket = {42: sock}
    thread.poller = MagicMock()
    thread.active.set()

    thread.client.on_disconnect(thread.client, thread, mqtt.MQTT_ERR_CONN_LOST)

    # paho may run the callback on the thread that called send(), so it must
    # leave the poller to the MQThread.
    thread.poller.unregister.assert_not_called()

    def connect(**kwargs):
        thread.terminated.set()
        return 0

    thread.client.connect.side_effect = connect
    thread._poll()
    thread.poller.unregister.assert_called_once_with(sock)
    assert thread.fileno_to_socket == {}
    thread.client.connect.assert_called_once()


# 6. Test clean shutdown and resource cleanup
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


# 7. A refused connection is logged, not a silent thread exit
@patch("paho.mqtt.client.Client")
def test_refused_connection_logs_error_instead_of_exiting(mock_client, mqtt_config):
    logger = MagicMock()
    thread = MQThread(logger, mqtt_config)
    thread._mqtt_client()

    thread.client.on_connect(
        thread.client, thread, {}, mqtt.CONNACK_REFUSED_NOT_AUTHORIZED
    )

    logger.error.assert_called_once()
    assert "not authorised" in logger.error.call_args.args[0]
    thread.client.subscribe.assert_not_called()


# 8. Repeated refusals are retried with growing backoff, not in a tight loop
@patch("paho.mqtt.client.Client")
def test_refused_connection_is_retried_with_backoff(mock_client, mqtt_config):
    thread = MQThread(DummyLogger(), mqtt_config)
    thread._mqtt_client()
    thread.poller = MagicMock()
    thread.poller.poll.return_value = []
    thread.active.set()
    sock = MagicMock()
    sock.fileno.return_value = 42
    attempts = []

    def refused_connect(**kwargs):
        # What paho does for a refused CONNACK: socket opens, on_connect gets
        # the refusal code, then paho closes the socket and calls on_disconnect.
        attempts.append(time.monotonic())
        client = thread.client
        thread.on_socket_open(client, thread, sock)
        thread.on_connect(client, thread, {}, mqtt.CONNACK_REFUSED_NOT_AUTHORIZED)
        thread.on_disconnect(client, thread, mqtt.MQTT_ERR_CONN_REFUSED)
        if len(attempts) == 4:
            thread.terminated.set()
        return 0

    thread.client.connect.side_effect = refused_connect
    thread._poll()

    gaps = [b - a for a, b in zip(attempts, attempts[1:])]
    assert gaps[0] >= 0.1
    assert gaps[1] > gaps[0]
    assert gaps[2] > gaps[1]


# 9. The thread never ends silently, even on SystemExit
@patch("paho.mqtt.client.Client")
def test_run_logs_system_exit_instead_of_ending_silently(mock_client, mqtt_config):
    logger = MagicMock()
    thread = MQThread(logger, mqtt_config)

    with patch.object(MQThread, "_poll", side_effect=SystemExit(5)):
        thread.run()

    logger.error.assert_called_once()
    assert "SystemExit" in logger.error.call_args.args[0]
