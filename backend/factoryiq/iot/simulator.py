from datetime import UTC, datetime
from random import Random
from time import monotonic
from uuid import uuid4

from ..db import engine, rows
from .mqtt import derived_password, mqtt_client
from .protocol import SIMULATED_STATIONS, TOPIC_PREFIX
import json

SAMPLE_SECONDS = 3
MODELS = {
    # Nominal RPM, load current, idle cabinet temperature and vibration RMS.
    "sim-conveyor": (850, 5.1, 37, 0.21),
    "sim-sorter": (1050, 7.1, 42, 0.28),
    "sim-robot": (1420, 8.7, 40, 0.31),
    "sim-hydraulic": (1170, 10.2, 48, 0.38),
    "sim-line": (780, 4.6, 34, 0.19),
    "sim-motor": (1760, 11.2, 45, 0.35),
}


class Simulator:
    def __init__(self):
        self.clock = 0.0
        self.rng = Random(53)
        self.clients = {device:mqtt_client(device,derived_password(device))
                        for device,*_ in SIMULATED_STATIONS}

    def start(self):
        for client in self.clients.values():
            client.loop_start()

    def stop(self):
        for client in self.clients.values():
            client.disconnect()
            client.loop_stop()

    def tick(self):
        if monotonic()-self.clock < SAMPLE_SECONDS:
            return
        self.clock = monotonic()
        now = datetime.now(UTC).replace(microsecond=0)
        with engine().connect() as conn:
            controls = {r["device_id"]:r["fault"] for r in rows(conn,"""SELECT device_id,fault
                           FROM iot_simulation_controls WHERE expires_at>now()""")}
        for device,_,_,_,cycle in SIMULATED_STATIONS:
            client = self.clients[device]
            fault = controls.get(device,"normal")
            if fault=="communication_failure" or not client.is_connected():
                continue
            common = {"schema_version":1,"device_id":device,"observed_at":now.isoformat()}
            client.publish(f"{TOPIC_PREFIX}/{device}/heartbeat",json.dumps(common),qos=1)
            payload = sample(device,cycle,fault,self.rng)
            client.publish(f"{TOPIC_PREFIX}/{device}/telemetry",json.dumps({**common,**payload}),qos=1)


def sample(device, cycle, fault, rng):
    rpm,amps,temp,vibration = MODELS[device]
    is_stopped = fault in {"jam","shutdown"}
    status = "stopped" if fault=="shutdown" else "fault" if fault!="normal" else "running"
    run = 0 if is_stopped else SAMPLE_SECONDS
    count = min(100000,int(run/cycle)) if cycle else None
    if count and rng.random()<0.06:
        count -= 1
    good = max(0,count-(1 if count and (fault!="normal" or rng.random()<0.035) else 0)) if count is not None else None
    voltage = rng.uniform(23.4,24.6)
    current = rng.uniform(amps*0.90,amps*1.10)
    if fault in {"jam","overcurrent"}:
        current = rng.uniform(20,23)
    if fault=="shutdown":
        current = 0
    return {
        "message_id":str(uuid4()),"interval_seconds":SAMPLE_SECONDS,"run_seconds":run,"status":status,
        "temperature_c":round(rng.uniform(83,90) if fault=="overheat" else temp+rng.uniform(-1.8,1.8),3),
        "vibration_g":None if fault=="sensor_disconnected" else round(rng.uniform(3.8,5.2)
                      if fault=="vibration" else 0 if is_stopped else vibration+rng.uniform(-0.04,0.04),4),
        "rpm":0 if is_stopped else round(rpm*rng.uniform(0.96,1.04),1),
        "current_a":round(current,3),"voltage_v":round(voltage,3),"power_w":round(current*voltage,2),
        "produced":count,"good":good,"fault":None if fault=="normal" else fault,
    }
