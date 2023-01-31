import multiprocessing
import pytest
import queue
import time

from riaps.ctrl.ctrl import Controller
import riaps.logger.drivers.factory as driver_factory
from riaps.logger.server import AppLogServer
import riaps.logger.server
from riaps.utils.config import Config


@pytest.mark.skip
def test_sanity():
    assert True


@pytest.mark.skip
def test_mqtt():
    from MQTT import MQThread
    import logging
    logging.basicConfig()
    logger = logging.getLogger()
    thread = MQThread(logger, "cfg/mqtt.yaml")
    assert thread.topics
    thread.mqtt_client()
    thread.mqtt_connect()
    logger.warning(thread.broker)
    assert thread.broker


def test_cli():
    the_config = Config()
    c = Controller(port=8888, script="-")

    # servers = {}
    # q = queue.Queue()
    # server_log_handler = handler_factory.get_handler(handler_type="testing", session_name="app")
    # app_log_server = AppLogServer(server_address=("172.21.20.70", 9021),
    #                               RequestHandlerClass=riaps.log.server.AppLogHandler,
    #                               server_log_handler=server_log_handler,
    #                               q=q)
    # p = multiprocessing.Process(target=app_log_server.serve_until_stopped)
    # servers["app"] = {"server": app_log_server,
    #                   "process": p,
    #                   "server_log_handler": server_log_handler}
    # p.start()

    if True:
        required_clients = ['172.21.20.40', '172.21.20.41', '172.21.20.50']
        app_folder = "/home/riaps/projects/RIAPS/example.mqnr/svg_riaps"
        c.setAppFolder(app_folder)
        app_name = c.compileApplication("mqnr.riaps", app_folder)
        depl_file = "mqnr.depl"
        also_app_name = c.compileDeployment(depl_file)

        # start
        # c.startRedis()
        c.startDht()
        c.startService()

        # wait for clients to be discovered
        known_clients = []
        while not set(known_clients) == set(required_clients):
            known_clients = c.getClients()
            print(f"known clients: {known_clients}")
            time.sleep(1)

        # launch application
        print("launch app")
        is_app_launched = c.launchByName(app_name)
        # downloadApp (line 512). Does the 'I' mean 'installed'?
        # launchByName (line 746)
        print(f"app launched? {is_app_launched}")

        manual_run = True
        timed_run = False

        if manual_run:
            done = input("Provide input when ready to stop")
        elif timed_run:
            for i in range(10):
                print(f"App is running: {i}")
                time.sleep(1)

        # Halt application
        print("Halt app")
        is_app_halted = c.haltByName(app_name)
        # haltByName (line 799).
        print(f"app halted? {is_app_halted}")

        # assert app_log_server.server_log_handler.app_properties.has_started, "Failed to start"
        # assert server_log_handler.app_properties.has_started, "Failed to start"
        # assert server_log_handler.app_properties.has_ended, "Failed to stop"

        # Remove application
        print("remove app")
        c.removeAppByName(app_name)  # has no return value.
        # removeAppByName (line 914).
        print("app removed")

        # Stop controller
        print("Stop controller")
        c.stop()
        print("controller stopped")
