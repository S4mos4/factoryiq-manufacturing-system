"""Measure MQTT decode-to-commit and a native history query on a disposable database."""

import json
import platform
from datetime import UTC, datetime, timedelta
from statistics import median
from time import perf_counter
from uuid import uuid4

from .db import engine, query, sql_file
from .iot.mqtt import ingest
from .iot.protocol import TOPIC_PREFIX
from .iot.store import provision_simulation


def run():
    provision_simulation()
    device = "sim-conveyor"
    count = 500
    end = datetime.now(UTC)-timedelta(hours=1)
    start = end-timedelta(seconds=count*3)
    payloads = [
        json.dumps(dict(schema_version=1,device_id=device,observed_at=(start+timedelta(seconds=(i+1)*3)).isoformat(),
                        message_id=str(uuid4()),interval_seconds=3,run_seconds=3,status="running",
                        temperature_c=45,vibration_g=0.3,rpm=850,current_a=5,voltage_v=24,power_w=120,
                        produced=3,good=3)).encode()
        for i in range(count)
    ]
    before = perf_counter()
    accepted = sum(ingest(f"{TOPIC_PREFIX}/{device}/telemetry",payload)=="accepted" for payload in payloads)
    elapsed = perf_counter()-before
    if accepted != count:
        raise RuntimeError("Use a fresh seeded database without existing telemetry.")
    result = {
        "platform":platform.machine()+" "+platform.system(),
        "ingestion":{"accepted":accepted,"elapsed_s":round(elapsed,4),"readings_per_s":round(accepted/elapsed,2)},
    }
    with engine().connect() as conn:
        with conn.begin() as transaction:
            query(conn,"""INSERT INTO iot_readings(device_id,observed_at,message_id,interval_seconds,run_seconds,
                           status,temperature_c,vibration_g,rpm,current_a,voltage_v,power_w,produced,good)
                         SELECT (ARRAY['sim-conveyor','sim-sorter','sim-robot','sim-hydraulic','sim-line','sim-motor'])[1+i%6],
                                :end-(i*interval '3 sec'),gen_random_uuid(),3,3,'running',
                                42+(i%13)*0.1,0.24,950,5,24,120,2,2
                         FROM generate_series(1,200000) n(i)""",end=start-timedelta(hours=1))
            query(conn,"ANALYZE iot_readings")
            result["postgres"] = query(conn,"SHOW server_version").scalar_one()
            result["rows"] = query(conn,"SELECT count(*) FROM iot_readings").scalar_one()
            upper = start-timedelta(hours=2)
            explain = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "+sql_file("iot_history")
            params = dict(device=device,start=upper-timedelta(hours=1),end=upper,bucket=5)

            def plans():
                runs = [query(conn,explain,**params).scalar_one()[0] for _ in range(6)]
                return {"median_execution_ms":median(p["Execution Time"] for p in runs[1:]),
                        "execution_ms":[p["Execution Time"] for p in runs[1:]],"plan":runs[-1]}

            result["planner_default"] = plans()
            query(conn,"SET LOCAL enable_indexscan=off")
            query(conn,"SET LOCAL enable_bitmapscan=off")
            query(conn,"SET LOCAL enable_indexonlyscan=off")
            result["diagnostic_sequential_scan"] = plans()
            transaction.rollback()
    return result


if __name__=="__main__":
    print(json.dumps(run(),indent=2))
