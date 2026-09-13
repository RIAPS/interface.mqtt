"""End-to-end checks for issue #4: an idle subscriber must stay connected, a
client must reconnect on its own if the broker drops it, and a busy publisher
must notice a half-open link (no FIN or RST ever arrives) and reconnect.

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
def mosquitto(tmp_path):
    exe = _mosquitto_path()
    if exe is None:
        pytest.skip("mosquitto is not installed")
    conf = tmp_path / "mosquitto.conf"
    conf.write_text(f"listener {PORT} 127.0.0.1\nallow_anonymous true\n")
    broker = Mosquitto(exe, conf)
    broker.start()
    yield broker
    broker.stop()


class DummyLogger:
    def __init__(self):
        self.errors = []

    def info(self, msg, **kwargs):
        pass

    def error(self, msg, **kwargs):
        self.errors.append(msg)

    def debug(self, msg, **kwargs):
        pass

    def warning(self, msg, **kwargs):
        pass


class RecordingThread(MQThread):
    def __init__(self, logger, config):
        super().__init__(logger, config)
        self.received = []

    def handle_broker_message(self, msg):
        self.received.append(msg)


@pytest.fixture
def mqthread(mosquitto):
    config = {
        "broker_connect_config": {
            "host": "127.0.0.1",
            "port": PORT,
            "keepalive": KEEPALIVE,
        },
        "topics": {"subscriptions": [COMMAND_TOPIC]},
    }
    thread = RecordingThread(DummyLogger(), config)
    thread.start()
    thread.activate()
    time.sleep(1)
    assert thread.broker is not None, "MQThread never connected"
    yield thread
    thread.terminate()
    thread.join(timeout=5)


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
    assert _wait_for(lambda: mqthread.broker is None, timeout=KEEPALIVE * 3)

    mosquitto.start()
    assert _wait_for(lambda: mqthread.broker is not None, timeout=10)
    time.sleep(0.5)  # let the SUBSCRIBE reach the broker

    _operator_sends_command('{"cmd": "resume"}')

    assert _wait_for(lambda: mqthread.received, timeout=3)
    assert mqthread.received == [{"cmd": "resume"}]


def test_busy_publisher_notices_half_open_link_and_reconnects(mosquitto, mqthread):
    # The field failure: the app publishes at 1 Hz, the path stops carrying
    # packets, and writes keep succeeding into the local send buffer. Only the
    # unanswered PINGREQ from loop_misc() can reveal that the peer is gone.
    mosquitto.freeze()
    frozen_at = time.time()
    deadline = frozen_at + KEEPALIVE * 3 + 2
    noticed_at = None
    while time.time() < deadline:
        mqthread.send("test/telemetry", "tick", qos=0)
        if any("disconnected from broker" in e for e in mqthread.logger.errors):
            noticed_at = time.time()
            break
        time.sleep(1)
    mosquitto.thaw()

    assert noticed_at is not None, "client never noticed the half-open link"
    assert noticed_at - frozen_at <= KEEPALIVE * 3 + 1

    # Once the broker answers again, the client is back and receives commands.
    time.sleep(KEEPALIVE * 2)
    _operator_sends_command('{"cmd": "resume"}')

    assert _wait_for(lambda: mqthread.received, timeout=KEEPALIVE * 4)
    assert mqthread.received == [{"cmd": "resume"}]
