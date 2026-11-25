import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from ..common import Input, PositiveId, audit, required
from ..db import engine, one, query, rows, sql_file
from ..operations import Actor
from ..security import enabled, read_access
from .protocol import DeviceId, Metric, SimFault
from .store import record_alarm_history

router = APIRouter(prefix="/api/iot",dependencies=[Depends(read_access)],tags=["Equipment monitoring"])
Window = Annotated[int, Query(ge=1,le=1440)]
DEVICE = """SELECT d.id,d.equipment_id,d.station_name,d.station_order,d.simulated,d.ideal_cycle_seconds,
                   d.last_heartbeat_at,d.last_reading_at,
                   d.connected AND d.last_heartbeat_at>now()-interval '12 seconds' AS connected,
                   e.code AS equipment_code,e.status AS maintenance_status
            FROM iot_devices d JOIN equipment e ON e.id=d.equipment_id
            WHERE (NOT :synthetic OR d.simulated)"""


class Threshold(Input):
    warning: Annotated[float, Field(ge=0,lt=1000000,allow_inf_nan=False)]
    critical: Annotated[float, Field(gt=0,lt=1000000,allow_inf_nan=False)]

    @model_validator(mode="after")
    def ordered(self):
        if self.warning>=self.critical:
            raise ValueError("The critical threshold must exceed the warning threshold.")
        return self


class Simulation(Input):
    fault: SimFault
    duration_seconds: Annotated[int, Field(strict=True,ge=15,le=180)] = 45


def synthetic_only():
    return enabled("FACTORYIQ_DEMO_READS")


def get_device(conn, device):
    return required(one(conn,DEVICE+" AND d.id=:device",synthetic=synthetic_only(),device=device),"Device")


def snapshot():
    with engine().connect() as conn:
        return {
            "devices":rows(conn,DEVICE+""" ORDER BY d.station_order,d.id""",synthetic=synthetic_only()),
            "readings":rows(conn,"""SELECT r.* FROM iot_devices d
                         JOIN iot_readings r ON r.device_id=d.id AND r.observed_at=d.last_reading_at
                         WHERE NOT :synthetic OR d.simulated""",synthetic=synthetic_only()),
            "alarms": rows(conn,"""SELECT a.* FROM iot_alarms a JOIN iot_devices d ON d.id=a.device_id
                     WHERE a.resolved_at IS NULL AND (NOT :synthetic OR d.simulated)
                     ORDER BY (a.severity='critical') DESC,a.first_at DESC LIMIT 100""",synthetic=synthetic_only()),
        }


@router.get("/snapshot")
def initial_snapshot():
    return snapshot()


@router.get("/stream")
async def stream(request: Request):
    async def events():
        # Stream bounded lifetimes so every reconnect goes through authorization.
        previous = None
        for _ in range(60):
            if await request.is_disconnected():
                break
            body = json.dumps(jsonable_encoder(await run_in_threadpool(snapshot)),separators=(",",":"))
            if body!=previous:
                yield f"data:{body}\n\n"
                previous = body
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(events(),media_type="text/event-stream",
                             headers={"X-Accel-Buffering":"no","Cache-Control":"no-cache, no-transform"})


@router.get("/devices/{device}")
def detail(device: DeviceId, minutes: Window = 30):
    end = datetime.now(UTC)
    start = end-timedelta(minutes=minutes)
    params = dict(device=device,start=start,end=end)
    with engine().connect() as conn:
        mapping = get_device(conn,device)
        return {
            "device":dict(mapping),
            "history":rows(conn,sql_file("iot_history"),bucket=5 if minutes<=60 else 120,**params),
            "performance":dict(one(conn,sql_file("iot_performance"),**params)),
            "condition":rows(conn,sql_file("iot_condition"),device=device),
            "alarms":rows(conn,"SELECT * FROM iot_alarms WHERE device_id=:device ORDER BY first_at DESC,id DESC LIMIT 30",device=device),
            "connections":rows(conn,"SELECT online,changed_at FROM iot_connections WHERE device_id=:device ORDER BY id DESC LIMIT 15",device=device),
            "thresholds":rows(conn,"SELECT * FROM iot_thresholds WHERE device_id=:device ORDER BY metric",device=device),
            "maintenance":rows(conn,"SELECT id,title,due_on,status,overdue FROM maintenance_queue WHERE equipment_id=:equipment ORDER BY due_on DESC,id DESC LIMIT 15",
                               equipment=mapping["equipment_id"]),
        }


@router.get("/devices/{device}/alarms/{alarm_id}/history")
def alarm_history(device: DeviceId,alarm_id: PositiveId):
    with engine().connect() as conn:
        get_device(conn,device)
        required(one(conn,"SELECT id FROM iot_alarms WHERE device_id=:device AND id=:id",device=device,id=alarm_id),"Alarm")
        return rows(conn,"SELECT action,at,actor_id FROM iot_alarm_history WHERE alarm_id=:id ORDER BY id",id=alarm_id)


@router.put("/devices/{device}/thresholds/{metric}")
def set_threshold(device: DeviceId,metric: Metric,data: Threshold,actor: Actor):
    with engine().begin() as conn:
        target = get_device(conn,device)
        query(conn,"""INSERT INTO iot_thresholds(device_id,metric,warning,critical) VALUES (:device,:metric,:warning,:critical)
              ON CONFLICT(device_id,metric) DO UPDATE SET warning=excluded.warning,critical=excluded.critical""",
              device=device,metric=metric,**data.model_dump())
        audit(conn,actor,"iot_threshold","equipment",target["equipment_id"],device=device,metric=metric,**data.model_dump())
    return {"ok":True}


@router.post("/devices/{device}/simulation")
def simulate(device: DeviceId,data: Simulation,actor: Actor):
    if not enabled("FACTORYIQ_SIMULATE"):
        raise HTTPException(409,"Simulation controls are disabled on this instance.")
    with engine().begin() as conn:
        target = get_device(conn,device)
        if not target["simulated"]:
            raise HTTPException(409,"Fault injection is only available on simulated equipment.")
        expires = datetime.now(UTC)+timedelta(seconds=data.duration_seconds)
        query(conn,"""INSERT INTO iot_simulation_controls(device_id,fault,expires_at) VALUES (:device,:fault,:expires)
            ON CONFLICT (device_id) DO UPDATE SET fault=excluded.fault,expires_at=excluded.expires_at""",
              device=device,fault=data.fault,expires=expires)
        audit(conn,actor,"iot_simulation","equipment",target["equipment_id"],device=device,fault=data.fault)
    return {"fault":data.fault,"expires_at":expires}


@router.post("/devices/{device}/alarms/{alarm_id}/acknowledge")
def acknowledge(device: DeviceId,alarm_id: PositiveId,actor: Actor):
    with engine().begin() as conn:
        get_device(conn,device)
        alarm = required(one(conn,"SELECT * FROM iot_alarms WHERE device_id=:device AND id=:id FOR UPDATE",
                             device=device,id=alarm_id),"Alarm")
        if not alarm["acknowledged_at"]:
            query(conn,"UPDATE iot_alarms SET acknowledged_at=now(),acknowledged_by=:actor WHERE id=:id",
                  id=alarm_id,actor=actor)
            record_alarm_history(conn,alarm_id,"acknowledged",actor)
    return {"ok":True}
