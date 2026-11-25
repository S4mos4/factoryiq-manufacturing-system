import asyncio
import json
import os
import shutil
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest

from factoryiq.db import query
from factoryiq.iot.api import stream
from factoryiq.iot.mqtt import derived_password, ingest, mqtt_client, subscriber
from factoryiq.iot.protocol import Reading, TOPIC_PREFIX
from factoryiq.iot.simulator import MODELS, sample
from factoryiq.iot.store import expire_connections, provision_simulation, save_reading


def payload(device,stamp,**changes):
    return {"schema_version":1,"device_id":device,"observed_at":stamp.isoformat(),"message_id":str(uuid4()),
            "interval_seconds":10,"run_seconds":8,"status":"running","temperature_c":43,
            "vibration_g":0.25,"power_w":240,"produced":6,"good":5,**changes}


def send(device,stamp,**changes):
    return ingest(f"{TOPIC_PREFIX}/{device}/telemetry",json.dumps(payload(device,stamp,**changes)).encode())


@pytest.fixture
def stations(database):
    provision_simulation()
    return database


def test_validation_idempotency_and_overlap(stations):
    device="sim-conveyor"
    now=datetime.now(UTC)-timedelta(minutes=5)
    topic=f"{TOPIC_PREFIX}/{device}/telemetry"
    body=payload(device,now)
    encoded=json.dumps(body).encode()
    assert ingest(topic,encoded)=="accepted"
    assert ingest(topic,encoded)=="duplicate"
    assert ingest(topic,encoded,retained=True)=="invalid"
    assert ingest(topic,b"{}")=="invalid"
    assert ingest(topic,b"x"*4097)=="invalid"
    assert ingest(topic,json.dumps({**body,"power_w":float("inf")}).encode())=="invalid"
    assert ingest(topic,json.dumps({**body,"device_id":"sim-motor"}).encode())=="identity_mismatch"
    assert send(device,now+timedelta(seconds=5))=="overlap"
    assert send(device,now+timedelta(seconds=10),good=30)=="invalid"
    assert send(device,now+timedelta(seconds=10))=="accepted"


def test_oee_and_missing_measurements(client,stations):
    now=datetime.now(UTC)-timedelta(seconds=30)
    device="sim-sorter"
    assert send(device,now,interval_seconds=10,run_seconds=8,produced=6,good=5)=="accepted"
    assert send(device,now+timedelta(seconds=10),interval_seconds=10,run_seconds=8,produced=6,good=4)=="accepted"
    report=client.get(f"/api/iot/devices/{device}?minutes=15").json()
    p=report["performance"]
    assert (p["availability_percent"],p["performance_percent"],p["quality_percent"])==(80,75,75)
    assert p["oee_percent"]==pytest.approx(45)
    assert p["energy_kwh"]==pytest.approx(4800/3600000)
    assert p["downtime_seconds"]==4
    assert len(report["history"])==2
    assert client.get("/api/iot/devices/sim-motor").json()["performance"]["oee_percent"] is None


def test_threshold_deduplication_acknowledgement_and_recovery(client,stations,headers):
    device="sim-robot"
    root=f"/api/iot/devices/{device}"
    assert client.put(root+"/thresholds/temperature_c",headers=headers,json={"warning":50,"critical":70}).status_code==200
    assert client.put(root+"/thresholds/current_a",headers=headers,json={"warning":60,"critical":20}).status_code==422
    now=datetime.now(UTC)-timedelta(minutes=2)
    for offset,temp in enumerate((55,75,78,43,43)):
        assert send(device,now+timedelta(seconds=10*offset),temperature_c=temp)=="accepted"
    report=client.get(root).json()
    alarm,=report["alarms"]
    assert alarm["severity"]=="critical" and alarm["resolved_at"]
    ack=root+f"/alarms/{alarm['id']}/acknowledge"
    assert client.post(ack).status_code==401
    assert client.post(ack,headers=headers).status_code==200
    assert client.post(ack,headers=headers).status_code==200
    logs=client.get(root+f"/alarms/{alarm['id']}/history").json()
    assert [action["action"] for action in logs]==["opened","escalated","resolved","acknowledged"]


def test_simulation_authentication_and_model(client,stations,headers,monkeypatch):
    from random import Random
    root="/api/iot/devices/sim-hydraulic/simulation"
    data={"fault":"jam","duration_seconds":25}
    monkeypatch.setenv("FACTORYIQ_SIMULATE","false")
    assert client.post(root,headers=headers,json=data).status_code==409
    monkeypatch.setenv("FACTORYIQ_SIMULATE","true")
    assert client.post(root,json=data).status_code==401
    assert client.post(root,headers=headers,json=data).status_code==200
    with stations.connect() as conn:
        assert query(conn,"SELECT fault FROM iot_simulation_controls WHERE device_id='sim-hydraulic'").scalar()=="jam"
    assert set(MODELS)=={"sim-robot","sim-conveyor","sim-sorter","sim-hydraulic","sim-line","sim-motor"}
    jam=sample("sim-hydraulic",1.25,"jam",Random(17))
    assert jam["rpm"]==jam["run_seconds"]==jam["produced"]==0
    monkeypatch.setenv("FACTORYIQ_READ_ONLY","true")
    assert client.post(root,headers=headers,json=data).status_code==403


def test_private_telemetry_excluded_from_demo(client,stations,headers,monkeypatch):
    with stations.begin() as conn:
        query(conn,"""INSERT INTO iot_devices(id,equipment_id,station_name,station_order,simulated)
                      VALUES ('esp32-test',1,'Private fixture',8,false)""")
    assert client.get("/api/iot/devices/esp32-test").status_code==404
    assert "esp32-test" not in client.get("/api/iot/snapshot").text
    monkeypatch.setenv("FACTORYIQ_DEMO_READS","false")
    assert client.get("/api/iot/snapshot").status_code==401
    assert client.get("/api/iot/stream").status_code==401
    assert client.get("/api/iot/devices/esp32-test",headers=headers).status_code==200


def test_stream_snapshot(stations):
    class LiveRequest:
        async def is_disconnected(self):
            return False

    async def first_event():
        response=await stream(LiveRequest())
        assert response.media_type=="text/event-stream"
        event=await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return json.loads(event.removeprefix("data:"))

    assert any(d["id"]=="sim-robot" for d in asyncio.run(first_event())["devices"])


def wait_until(predicate,seconds=8):
    deadline=monotonic()+seconds
    while monotonic()<deadline:
        if predicate():
            return
        sleep(0.05)
    pytest.fail("MQTT integration condition did not converge.")


@pytest.fixture
def broker(tmp_path):
    docker = os.getenv("FACTORYIQ_TEST_MQTT_DOCKER")=="true"
    if not docker and (not shutil.which("mosquitto") or not shutil.which("mosquitto_passwd")):
        pytest.skip("Install Mosquitto or enable the Docker test broker.")
    with socket.socket() as local:
        local.bind(("127.0.0.1",0))
        port=local.getsockname()[1]
    password,secret=token_hex(24),token_hex(24)
    env={**os.environ,"FACTORYIQ_MQTT_PORT":str(port),"FACTORYIQ_MQTT_BIND":"127.0.0.1","TMPDIR":str(tmp_path),
         "FACTORYIQ_MQTT_BRIDGE_PASSWORD":password,"FACTORYIQ_MQTT_DEVICE_SECRET":secret}
    script=Path(__file__).resolve().parents[2]/"mqtt"/"start.sh"
    log_path=tmp_path/"broker.log"
    name=f"factoryiq-mqtt-test-{uuid4().hex}"
    if docker:
        command=["docker","run","--rm","--name",name,"--publish",f"127.0.0.1:{port}:1883",
                 "--volume",f"{script}:/factoryiq/start.sh:ro",
                 "--env","FACTORYIQ_MQTT_BRIDGE_PASSWORD","--env","FACTORYIQ_MQTT_DEVICE_SECRET",
                 "--entrypoint","sh","eclipse-mosquitto:2.0.22","/factoryiq/start.sh"]
    else:
        command=["sh",str(script)]
    with log_path.open("w") as log:
        proc=subprocess.Popen(command,env=env,stdout=log,stderr=log)
        try:
            def accessible():
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=0.1):
                        return True
                except OSError:
                    if proc.poll() is not None:
                        pytest.fail("Test broker failed to start: "+log_path.read_text()[-1600:])
                    return False
            wait_until(accessible,60 if docker else 8)
            yield port,password,secret
        finally:
            if docker:
                subprocess.run(["docker","stop","--time","3",name],check=False,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)


def test_real_mqtt_ingestion_acl_and_reconnection(stations,broker):
    port,password,secret=broker
    ready,retry=Event(),Event()
    bridge=subscriber(password,retry,port=port)
    bridge.on_subscribe=lambda *_: ready.set()
    publisher=mqtt_client("sim-line",derived_password("sim-line",secret),port=port)
    rejected=Event()
    invalid=mqtt_client("sim-line",token_hex(24),port=port)
    invalid.on_connect=lambda _c,_u,_f,rc,_p: rejected.set() if rc.is_failure else None
    for connection in (bridge,publisher,invalid):
        connection.loop_start()
    try:
        assert ready.wait(8)
        assert rejected.wait(8)
        wait_until(publisher.is_connected)
        device="sim-line"
        now=datetime.now(UTC)
        line=payload(device,now)
        raw=json.dumps(line)
        prefix=f"{TOPIC_PREFIX}/{device}"

        def send_at(topic,body):
            publisher.publish(topic,body,qos=1).wait_for_publish(5)

        def scalar(sql,**params):
            with stations.connect() as conn:
                return query(conn,sql,**params).scalar()

        send_at(f"{TOPIC_PREFIX}/sim-motor/telemetry",json.dumps(payload("sim-motor",now)))
        send_at(prefix+"/telemetry","not-json")
        send_at(prefix+"/telemetry",raw)
        send_at(prefix+"/telemetry",raw)
        send_at(prefix+"/heartbeat",json.dumps({k:line[k] for k in ("schema_version","device_id","observed_at")}))
        wait_until(lambda:scalar("SELECT connected FROM iot_devices WHERE id='sim-line'"))
        assert scalar("SELECT count(*) FROM iot_readings WHERE device_id='sim-line'")==1
        assert scalar("SELECT count(*) FROM iot_readings WHERE device_id='sim-motor'")==0
        assert not retry.is_set()
        publisher.disconnect()
        publisher.loop_stop()
        with stations.begin() as conn:
            query(conn,"UPDATE iot_devices SET last_heartbeat_at=now()-interval '20 seconds' WHERE id='sim-line'")
        expire_connections()
        assert not scalar("SELECT connected FROM iot_devices WHERE id='sim-line'")
        publisher=mqtt_client(device,derived_password(device,secret),port=port)
        publisher.loop_start()
        wait_until(publisher.is_connected)
        send_at(prefix+"/heartbeat",json.dumps({"schema_version":1,"device_id":device,
                                                "observed_at":datetime.now(UTC).isoformat()}))
        wait_until(lambda:scalar("SELECT connected FROM iot_devices WHERE id='sim-line'"))
        with stations.connect() as conn:
            assert query(conn,"SELECT online FROM iot_connections WHERE device_id='sim-line' ORDER BY id").scalars().all()==[True,False,True]
    finally:
        for connection in (bridge,publisher,invalid):
            connection.disconnect()
            connection.loop_stop()


def test_explainable_condition_signal(client,stations):
    now=datetime.now(UTC)-timedelta(seconds=81)
    for i,value in enumerate((40,40.2,40.4,40.1,40.3,40,40.2,40.4,46)):
        assert send("sim-hydraulic",now+timedelta(seconds=i*10),temperature_c=value)=="accepted"
    report=client.get("/api/iot/devices/sim-hydraulic").json()
    temperature=next(row for row in report["condition"] if row["metric"]=="temperature_c")
    assert temperature["assessment"]=="statistical anomaly"
    assert temperature["points"]==8 and temperature["z_score"]>3.5
