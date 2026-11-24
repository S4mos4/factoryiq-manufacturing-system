"""Collect plans on a disposable seeded PostgreSQL database."""

import json
from datetime import UTC, datetime, timedelta
from statistics import median

from .db import engine, query, sql_file


def benchmark():
    end = datetime(2026,10,1,tzinfo=UTC)
    start = end-timedelta(days=10)
    with engine().connect() as conn:
        with conn.begin() as transaction:
            query(conn,"""INSERT INTO sorter_fault_events(equipment_id,event_key,occurred_at,kind,lane,fault_code)
                         SELECT 1+i%20,'benchmark-'||i,:end-(((i*7919)%200003)*interval '1 min'),
                                CASE WHEN i%7=0 THEN 'fault' ELSE 'tick' END,NULL,
                                CASE WHEN i%7=0 THEN 'SENSOR_TIMEOUT' END
                         FROM generate_series(1,200000) n(i)""",end=end)
            query(conn,"ANALYZE sorter_fault_events")
            sample = {"postgres":query(conn,"SHOW server_version").scalar_one(),
                      "rows":query(conn,"SELECT count(*) FROM sorter_fault_events").scalar_one()}

            def measure():
                sql = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql_file("fault_frequency")
                plans = [query(conn,sql,start=start,end=end,machine=5).scalar_one()[0] for _ in range(6)]
                return {"median_execution_ms":median(p["Execution Time"] for p in plans[1:]),"last_plan":plans[-1]}

            sample["with_fault_index"] = measure()
            query(conn,"DROP INDEX sorter_fault_equipment_time_idx")
            sample["without_fault_index"] = measure()
            transaction.rollback()
    return sample


if __name__ == "__main__":
    print(json.dumps(benchmark(),indent=2))
