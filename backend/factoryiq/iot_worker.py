"""Run the MQTT bridge and optional synthetic equipment publishers."""

import logging
import os
import signal
from threading import Event

from sqlalchemy.exc import OperationalError

from .iot.mqtt import subscriber
from .iot.simulator import Simulator
from .iot.store import expire_connections, provision_simulation
from .security import enabled

log = logging.getLogger(__name__)


def run():
    if enabled("FACTORYIQ_READ_ONLY"):
        raise RuntimeError("Run telemetry ingestion only in the private writable environment.")
    password = os.environ["FACTORYIQ_MQTT_BRIDGE_PASSWORD"]
    if len(password)<32:
        raise ValueError("Set a high-entropy MQTT bridge password.")
    stopping, retry = Event(), Event()
    for signum in (signal.SIGINT,signal.SIGTERM):
        signal.signal(signum,lambda *_: stopping.set())

    simulation = Simulator() if enabled("FACTORYIQ_SIMULATE") else None
    if simulation:
        provision_simulation()
        simulation.start()
    bridge = subscriber(password,retry)
    bridge.loop_start()
    try:
        while not stopping.wait(1):
            if retry.is_set():
                bridge.disconnect()
                bridge.loop_stop()
                retry.clear()
                if stopping.wait(3):
                    break
                bridge = subscriber(password,retry)
                bridge.loop_start()
            try:
                expire_connections()
                if simulation:
                    simulation.tick()
            except OperationalError:
                log.warning("Telemetry worker waiting for PostgreSQL.")
    finally:
        bridge.disconnect()
        bridge.loop_stop()
        if simulation:
            simulation.stop()


if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    run()
