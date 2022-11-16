from MQTT import MQThread


def test_sanity():
    assert True


def test_mqtt():
    import logging
    logging.basicConfig()
    logger = logging.getLogger()
    thread = MQThread(logger, "cfg/mqtt.yaml")
    assert thread.topics
    thread.mqtt_client()
    thread.mqtt_connect()
    logger.warning(thread.broker)
    assert thread.broker


