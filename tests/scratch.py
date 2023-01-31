import multiprocessing
import queue
import time

from riaps.ctrl.ctrl import Controller
import riaps.log.handlers.factory as handler_factory
import riaps.log.server
from riaps.log.server import AppLogServer

from riaps.utils.config import Config


test_manager = multiprocessing.Manager()
test_data = test_manager.dict()


theConfig = Config()
c = Controller(port=8888, script="-")

servers = {}
test_q = queue.Queue()
q = queue.Queue()
# view = visualizer.View(session_name="app")
server_log_handler = handler_factory.get_handler(handler_type="testing", test_data=test_data)
app_log_server = AppLogServer(server_address=("172.21.20.70", 12345),
                              RequestHandlerClass=riaps.log.server.AppLogHandler,
                              server_log_handler=server_log_handler,
                              q=q)
p = multiprocessing.Process(target=app_log_server.serve_until_stopped)
servers["app"] = {"server": app_log_server,
                  "process": p,
                  "server_log_handler": server_log_handler}
p.start()

if True:
    required_clients = ['172.21.20.40', '172.21.20.41', '172.21.20.50']
    appFolder = "/home/riaps/projects/RIAPS/example.mqnr/svg_riaps"
    c.setAppFolder(appFolder)
    appName = c.compileApplication("mqnr.riaps", appFolder)
    deplFile = "mqnr.depl"
    also_appName = c.compileDeployment(deplFile)

    # start
    c.startRedis()
    c.startService()

    # wait for clients to be discovered
    known_clients = []
    while not set(known_clients) == set(required_clients):
        known_clients = c.getClients()
        print(f"known clients: {known_clients}")
        time.sleep(1)

    # launch application
    print("launch app")
    is_app_launched = c.launchByName(appName)
    # downloadApp (line 512). Does the 'I' mean 'installed'?
    # launchByName (line 746)
    print(f"app launched? {is_app_launched}")

    for i in range(10):
        print(f"App is running: {i}")
        time.sleep(1)

    # Halt application
    print("Halt app")
    is_app_halted = c.haltByName(appName)
    # haltByName (line 799).
    print(f"app halted? {is_app_halted}")

    for node in test_data:
        timeout = 10
        t = 0
        while not test_data[node]["has_ended"]:
            if t >= timeout:
                print("Either it didn't halt, or the message was lost")
                break
            print(f"Has it really halted though?: {test_data[node]['has_ended']}")
            time.sleep(1)
            t += 1

        assert test_data[node]["has_started"], f"App on {node} failed to start"
        assert test_data[node]["has_ended"], f"App on {node} failed to end"

    # Remove application
    print("remove app")
    c.removeAppByName(appName)  # has no return value.
    # removeAppByName (line 914).
    print("app removed")

    # Stop controller
    print("Stop controller")
    c.stop()
    print("controller stopped")

    print("Stop log server")
    p.terminate()
    print("log server stopped")




