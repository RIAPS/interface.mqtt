"""End-to-end checks for issue #4.

The field failure was a busy publisher on a half-open link: the path stopped
carrying packets, writes kept succeeding into the local send buffer, and no
FIN or RST ever arrived. Only an unanswered PINGREQ reveals that. These tests
also cover an idle subscriber, and a broker that closes the connection.

amqtt never expires a client on keepalive, so this runs against mosquitto,
which drops a client that sends nothing for 1.5x its keepalive.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import paho.mqtt.client as paho
import pytest

from riaps.interfaces.mqtt.MQTT import MQThread

PORT = 18884
KEEPALIVE = 2  # s; mosquitto drops the client after 3 s of silence
COMMAND_TOPIC = "test/commands"
DISCONNECT_LOG = "disconnected from broker"
RECONNECT_LOG = "Reconnected to broker"


def _mosquitto_path():
    bundled = Path(sys.prefix) / "sbin" / "mosquitto"
    if bundled.exists():
        return str(bundled)
    return shutil.which("mosquitto")


class Mosquitto:
    def __init__(self, exe, conf):
        self.exe = exe
        self.conf = conf
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen(
            [self.exe, "-c", str(self.conf)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        self.stop()
        pytest.fail("mosquitto did not start")

    def freeze(self):
        """Stop the process without closing its sockets: the link goes half-open."""
        os.kill(self.proc.pid, signal.SIGSTOP)

    def thaw(self):
        os.kill(self.proc.pid, signal.SIGCONT)

    def stop(self):
        if self.proc is not None:
            self.thaw()  # a stopped process never handles SIGTERM
            self.proc.terminate()
            self.proc.wait(timeout=5)
            self.proc = None


@pytest.fixture
def mosquitto_exe():
    exe = _mosquitto_path()
    if exe is None:
        if os.environ.get("CI"):
            pytest.fail("mosquitto is missing from the pixi dev env")
        pytest.skip("mosquitto is not installed")
    return exe


def _start_mosquitto(exe, tmp_path, allow_anonymous):
    conf = tmp_path / "mosquitto.conf"
    conf.write_text(
        f"listener {PORT} 127.0.0.1\n"
        f"allow_anonymous {'true' if allow_anonymous else 'false'}\n"
    )
    broker = Mosquitto(exe, conf)
    broker.start()
    return broker


@pytest.fixture
def mosquitto(mosquitto_exe, tmp_path):
    broker = _start_mosquitto(mosquitto_exe, tmp_path, allow_anonymous=True)
    yield broker
    broker.stop()


def _mqthread_config():
    return {
        "broker_connect_config": {
            "host": "127.0.0.1",
            "port": PORT,
            "keepalive": KEEPALIVE,
        },
        "topics": {"subscriptions": [COMMAND_TOPIC]},
    }


class RecordingLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, msg, **kwargs):
        self.infos.append(msg)

    def error(self, msg, **kwargs):
        self.errors.append(msg)

    def debug(self, msg, **kwargs):
        pass

    def warning(self, msg, **kwargs):
        pass

    def logged_error(self, text):
        return any(text in msg for msg in self.errors)

    def logged_info(self, text):
        return any(text in msg for msg in self.infos)


class RecordingThread(MQThread):
    def __init__(self, logger, config):
        super().__init__(logger, config)
        self.received = []

    def handle_broker_message(self, msg):
        self.received.append(msg)


@pytest.fixture
def mqthread(mosquitto):
    thread = RecordingThread(RecordingLogger(), _mqthread_config())
    thread.start()
    thread.activate()
    # has_connected is set on CONNACK, not when the socket opens.
    assert _wait_for(lambda: thread.has_connected, timeout=5), "never connected"
    time.sleep(0.5)  # let the SUBSCRIBE reach the broker
    yield thread
    thread.terminate()
    thread.join(timeout=5)
    assert not thread.is_alive(), "MQThread did not stop"


def _operator_sends_command(payload):
    operator = paho.Client()
    operator.connect("127.0.0.1", PORT, 60)
    operator.loop_start()
    operator.publish(COMMAND_TOPIC, payload, qos=1).wait_for_publish(2)
    operator.loop_stop()
    operator.disconnect()


def _wait_for(predicate, timeout):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        time.sleep(0.1)
    return predicate()


def test_idle_subscriber_still_receives_commands_after_keepalive(mqthread):
    # Nothing is published here. A publish from send() reaches the broker and
    # counts as activity, which would hide the missing ping.
    time.sleep(KEEPALIVE * 4)

    _operator_sends_command('{"cmd": "go"}')

    assert _wait_for(lambda: mqthread.received, timeout=3)
    assert mqthread.received == [{"cmd": "go"}]


def test_subscriber_reconnects_after_broker_drops_it(mosquitto, mqthread):
    mosquitto.stop()
    assert _wait_for(
        lambda: mqthread.logger.logged_error(DISCONNECT_LOG), timeout=KEEPALIVE * 3
    )

    mosquitto.start()
    assert _wait_for(lambda: mqthread.logger.logged_info(RECONNECT_LOG), timeout=10)
    time.sleep(0.5)  # let the SUBSCRIBE reach the broker

    _operator_sends_command('{"cmd": "resume"}')

    assert _wait_for(lambda: mqthread.received, timeout=3)
    assert mqthread.received == [{"cmd": "resume"}]


def test_busy_publisher_notices_half_open_link_and_reconnects(mosquitto, mqthread):
    # paho sends a PINGREQ once nothing has arrived for one keepalive, then
    # gives up when that ping is unanswered for another keepalive. loop_misc()
    # runs about once a second, so detection takes 2-3 keepalives, not one.
    detection_bound = KEEPALIVE * 3 + 1

    mosquitto.freeze()
    frozen_at = time.time()
    next_send = frozen_at
    noticed_at = None
    while time.time() < frozen_at + detection_bound + 2:
        if time.time() >= next_send:
            mqthread.send("test/telemetry", "tick", qos=0)  # the 1 Hz app
            next_send += 1
        if mqthread.logger.logged_error(DISCONNECT_LOG):
            noticed_at = time.time()
            break
        time.sleep(0.05)
    mosquitto.thaw()

    assert noticed_at is not None, "client never noticed the half-open link"
    assert noticed_at - frozen_at <= detection_bound

    # Once the broker answers again, the client reconnects and gets commands.
    assert _wait_for(
        lambda: mqthread.logger.logged_info(RECONNECT_LOG), timeout=KEEPALIVE * 4
    )
    time.sleep(0.5)  # let the SUBSCRIBE reach the broker
    _operator_sends_command('{"cmd": "resume"}')

    assert _wait_for(lambda: mqthread.received, timeout=3)
    assert mqthread.received == [{"cmd": "resume"}]


def test_refused_client_logs_and_keeps_retrying(mosquitto_exe, tmp_path):
    # A broker that requires auth refuses the anonymous client with CONNACK 5.
    # The thread used to call exit() here and die without a word.
    broker = _start_mosquitto(mosquitto_exe, tmp_path, allow_anonymous=False)
    thread = RecordingThread(RecordingLogger(), _mqthread_config())
    try:
        thread.start()
        thread.activate()

        def refusals():
            return sum("refused connection" in e for e in thread.logger.errors)

        assert _wait_for(lambda: refusals() >= 3, timeout=5)
        assert thread.is_alive()
        assert not thread.has_connected
    finally:
        thread.terminate()
        thread.join(timeout=5)
        broker.stop()
