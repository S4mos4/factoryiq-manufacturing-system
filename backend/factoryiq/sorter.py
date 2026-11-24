import csv
import hashlib
import io
import re
from collections import deque
from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from starlette.concurrency import run_in_threadpool

from .common import PositiveId, audit, required
from .db import engine, one, query, rows
from .operations import Actor
from .security import read_access

router = APIRouter(prefix="/api/sorter", dependencies=[Depends(read_access)])
MAX_BYTES = 512 * 1024
LANE_CAPACITY = 16
JAM_MS = 1000


def parse_trace(raw, anchor):
    source = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
    if next(source, None) != ["time_ms","event","lane"]:
        raise ValueError("Expected the header time_ms,event,lane.")
    events, stops = [], []
    lanes = {"A":deque(), "B":deque()}
    previous = 0
    for line, record in enumerate(source, start=2):
        if line > 10001 or len(record) != 3:
            raise ValueError(f"Line {line}: expected three columns and at most 10,000 records.")
        offset, kind, lane = record
        if not re.fullmatch(r"[0-9]{1,9}",offset):
            raise ValueError(f"Line {line}: invalid millisecond offset.")
        elapsed = int(offset)
        if elapsed < previous:
            raise ValueError(f"Line {line}: timestamps must be in chronological order.")
        previous = elapsed
        if kind not in {"ENTRY","EXIT","TICK"} or (lane not in lanes if kind != "TICK" else lane != ""):
            raise ValueError(f"Line {line}: use ENTRY or EXIT with A/B, or TICK with an empty lane.")
        if kind == "ENTRY" and len(lanes[lane]) == LANE_CAPACITY:
            raise ValueError(f"Line {line}: lane queue capacity exceeded.")
        if kind == "EXIT" and not lanes[lane]:
            raise ValueError(f"Line {line}: EXIT has no matching ENTRY.")
        stamp = anchor + timedelta(milliseconds=elapsed)
        for lane_name, packages in lanes.items():
            for package in packages:
                if elapsed - package["entered"] < JAM_MS:
                    break
                if package["jam"] is None:
                    package["jam"] = stamp
                    events.append(dict(key=f"jam-{package['line']}",time=stamp,kind="jam",lane=lane_name,fault="LANE_JAM"))
        event = dict(key=f"row-{line}",time=stamp,kind=kind.lower(),lane=lane or None,fault=None)
        events.append(event)
        if kind == "ENTRY":
            lanes[lane].append(dict(entered=elapsed,line=line,jam=None))
        elif kind == "EXIT":
            package = lanes[lane].popleft()
            event["processing_ms"] = elapsed-package["entered"]
            event["outcome"] = "jam_recovered" if package["jam"] is not None else "sorted"
            if package["jam"] is not None and package["jam"] < stamp:
                stops.append(dict(key=f"jam-{package['line']}",start=package["jam"],end=stamp))
    if not events:
        raise ValueError("The trace contains no event rows.")
    return events, stops, line-1


def save_import(raw, equipment_id, anchor, filename, actor):
    anchor = anchor.astimezone(UTC)
    checksum = hashlib.sha256(raw).hexdigest()
    run_key = f"{checksum}/{anchor.isoformat()}"
    with engine().begin() as conn:
        required(one(conn,"SELECT id FROM equipment WHERE id=:id FOR UPDATE",id=equipment_id),"Equipment")

        def history(outcome, count=0, error=None):
            result = one(conn,"""INSERT INTO import_history(equipment_id,user_id,filename,checksum,run_key,anchor_at,outcome,row_count,error)
                      VALUES (:e,:u,:n,:c,:k,:a,:o,:r,:err) RETURNING id,outcome,row_count,error""",
                      e=equipment_id,u=actor,n=filename,c=checksum,k=run_key,a=anchor,o=outcome,r=count,err=error)
            audit(conn,actor,outcome,"sorter_import",result["id"],equipment_id=equipment_id,row_count=count)
            return dict(result)

        prior = one(conn,"""SELECT row_count FROM import_history WHERE equipment_id=:e
                            AND run_key=:k AND outcome='imported'""",e=equipment_id,k=run_key)
        if prior:
            return history("duplicate",prior["row_count"])
        try:
            events, stops, count = parse_trace(raw,anchor)
        except (ValueError, csv.Error, OverflowError) as err:
            message = "Expected UTF-8 CSV." if isinstance(err,UnicodeError) else str(err)
            return history("failed",error=message)
        try:
            with conn.begin_nested():
                result = history("imported",count)
                conn.execute(text("""INSERT INTO sorter_fault_events(equipment_id,import_id,event_key,occurred_at,kind,lane,fault_code,
                                                                  processing_outcome,processing_ms)
                                     VALUES (:e,:i,:key,:time,:kind,:lane,:fault,:outcome,:processing_ms)"""),
                             [{"outcome":None,"processing_ms":None,**row,"e":equipment_id,"i":result["id"],
                               "key":f"{run_key}/{row['key']}"} for row in events])
                if stops:
                    conn.execute(text("""INSERT INTO downtime_events(equipment_id,started_at,ended_at,reason,source_key)
                                         VALUES (:e,:start,:end,'Sorter lane jam',:key)"""),
                                 [dict(row,e=equipment_id,key=f"{equipment_id}/{run_key}/{row['key']}") for row in stops])
        except (IntegrityError,DataError):
            return history("failed",error="The database rejected the trace. All event writes were rolled back.")
        return result


@router.post("/imports")
async def import_trace(request: Request, equipment_id: PositiveId, anchor: AwareDatetime,
                       filename: Annotated[str, Query(min_length=1,max_length=120)], actor: Actor):
    if request.headers.get("content-type","").split(";")[0].strip().lower() != "text/csv":
        raise HTTPException(415,"Upload a text/csv request body.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BYTES:
            raise HTTPException(413,"The trace exceeds 512 KiB.")
        raw.extend(chunk)
    result = await run_in_threadpool(save_import,bytes(raw),equipment_id,anchor,filename,actor)
    if result["outcome"] == "failed":
        raise HTTPException(422,result["error"])
    return result


@router.get("/imports")
def imports():
    with engine().connect() as conn:
        return rows(conn,"""SELECT i.id,i.filename,i.started_at,i.anchor_at,i.outcome,i.row_count,i.error,e.code AS equipment
                            FROM import_history i JOIN equipment e ON e.id=i.equipment_id ORDER BY i.id DESC LIMIT 250""")


@router.get("/events")
def events(equipment_id: PositiveId | None = None, faults_only: bool = False):
    with engine().connect() as conn:
        return rows(conn,"""SELECT s.id,s.occurred_at,s.kind,s.lane,s.fault_code,s.processing_outcome,s.processing_ms,e.code AS equipment,
                            s.import_id IS NULL AS synthetic FROM sorter_fault_events s JOIN equipment e ON e.id=s.equipment_id
                            WHERE (CAST(:e AS integer) IS NULL OR s.equipment_id=:e)
                              AND (NOT :only OR s.fault_code IS NOT NULL)
                            ORDER BY s.occurred_at DESC,s.id DESC LIMIT 250""",e=equipment_id,only=faults_only)
