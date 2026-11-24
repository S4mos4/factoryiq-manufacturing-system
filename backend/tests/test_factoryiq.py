import csv
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from factoryiq.db import query

TRACE = b"time_ms,event,lane\n0,ENTRY,A\n100,TICK,\n1000,TICK,\n3000,EXIT,A\n"
ANCHOR = "2026-09-22T08:00:00+00:00"


def new_part(database, units):
    key = uuid4().hex
    with database.begin() as conn:
        part = query(conn,"""INSERT INTO parts(sku,name,supplier_id,reorder_point)
                              VALUES (:sku,'Test stock',1,1) RETURNING id""",sku=key).scalar_one()
        batch = query(conn,"""INSERT INTO production_batches(code,part_id,equipment_id,started_at)
                              VALUES (:code,:p,1,'2026-08-01') RETURNING id""",code=key,p=part).scalar_one()
        query(conn,"INSERT INTO inventory_balances(part_id,usable) VALUES (:p,:u)",p=part,u=units)
    return part,batch


def stock(client, part):
    return client.get(f"/api/inventory/{part}").json()


def reserve(client, part, batch, headers, request_id=None):
    return client.post(f"/api/inventory/{part}/reserve",headers=headers,
                       json={"batch_id":batch,"quantity":1,"request_id":request_id or str(uuid4())})


def import_csv(client, headers, content=TRACE, equipment=5, anchor=ANCHOR):
    return client.post("/api/sorter/imports",params={"equipment_id":equipment,"anchor":anchor,"filename":"test.csv"},
                       content=content,headers={**headers,"Content-Type":"text/csv"})


def test_last_unit_concurrent_reservations(client,database,headers):
    part,batch = new_part(database,1)
    barrier = Barrier(2,timeout=10)

    def attempt():
        barrier.wait()
        return reserve(client,part,batch,headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(attempt) for _ in range(2)]
        assert sorted(future.result().status_code for future in requests)==[201,409]
    result=stock(client,part)
    assert result["part"]["available"]==0
    assert [m["kind"] for m in result["movements"]]==["reserve"]
    assert len(result["reservations"])==1


def test_reservation_retries_and_unavailable_consumption(client,database,headers):
    part,batch = new_part(database,1)
    request_id=str(uuid4())
    first=reserve(client,part,batch,headers,request_id).json()
    assert reserve(client,part,batch,headers,request_id).json()["id"]==first["id"]
    root=f"/api/inventory/{part}/reservations/{first['id']}"
    assert client.post(root+"/release",headers=headers).status_code==200
    assert client.post(root+"/consume",headers=headers).status_code==409
    assert client.post(root+"/release",headers=headers).status_code==200
    second=reserve(client,part,batch,headers).json()
    url=f"/api/inventory/{part}/reservations/{second['id']}/consume"
    assert client.post(url,headers=headers).status_code==200
    assert client.post(url,headers=headers).status_code==200
    assert reserve(client,part,batch,headers).status_code==409
    assert stock(client,part)["part"]["usable"]==0


def test_rejected_units_are_unavailable(client,database,headers):
    part,batch=new_part(database,1)
    assert client.post(f"/api/inventory/{part}/reject",headers=headers,json={"quantity":1,"notes":"Damage"}).status_code==201
    assert reserve(client,part,batch,headers).status_code==409
    assert stock(client,part)["part"]["rejected"]==1


def test_import_duplicate_and_jam_reconstruction(client,database,headers):
    assert import_csv(client,headers).json()["outcome"]=="imported"
    assert import_csv(client,headers).json()["outcome"]=="duplicate"
    with database.connect() as conn:
        assert query(conn,"SELECT count(*) FROM sorter_fault_events WHERE import_id IS NOT NULL AND equipment_id=5").scalar()==5
        outcome = query(conn,"""SELECT processing_outcome,processing_ms FROM sorter_fault_events
                                WHERE import_id IS NOT NULL AND equipment_id=5 AND kind='exit'""").one()
        assert tuple(outcome)==("jam_recovered",3000)
        assert query(conn,"SELECT extract(epoch FROM ended_at-started_at) FROM downtime_events WHERE reason='Sorter lane jam' AND equipment_id=5").scalar()==2


@pytest.mark.parametrize("content",[b"wrong,header\n1,A",b"time_ms,event,lane\n100,EXIT,A\n",
                                     b"time_ms,event,lane\n100,TICK,\n50,TICK,\n", b"\xff"])
def test_malformed_import_recorded_without_events(client,database,headers,content):
    count=lambda conn:query(conn,"SELECT count(*) FROM sorter_fault_events WHERE equipment_id=5").scalar()
    with database.connect() as conn:
        before=count(conn)
    assert import_csv(client,headers,content).status_code==422
    with database.connect() as conn:
        assert count(conn)==before
        assert query(conn,"SELECT outcome FROM import_history ORDER BY id DESC LIMIT 1").scalar()=="failed"


def test_import_rolls_back_inserted_events_if_downtime_write_fails(client,database,headers):
    equipment=10
    checksum=hashlib.sha256(TRACE).hexdigest()
    source_key=f"{equipment}/{checksum}/{ANCHOR}/jam-2"
    with database.begin() as conn:
        query(conn,"""INSERT INTO downtime_events(equipment_id,started_at,ended_at,reason,source_key)
                      VALUES (:e,'2026-09-22','2026-09-23','Test collision',:key)""",e=equipment,key=source_key)
    result=import_csv(client,headers,equipment=equipment)
    assert result.status_code==422
    assert "rolled back" in result.json()["detail"]
    with database.connect() as conn:
        assert query(conn,"SELECT count(*) FROM sorter_fault_events WHERE import_id IS NOT NULL AND equipment_id=:e",e=equipment).scalar()==0
        assert query(conn,"SELECT outcome FROM import_history WHERE equipment_id=:e",e=equipment).scalar()=="failed"
        assert query(conn,"""SELECT count(*) FROM audit_logs WHERE entity='sorter_import'
                             AND action='imported' AND details->>'equipment_id'='10'""").scalar()==0


def inspection_data(**overrides):
    return {"part_id":1,"batch_id":1,"inspected_at":"2026-09-20T12:00:00Z","measurements":[
        {"characteristic":"Width","unit":"mm","value":"10.1000","lower_limit":"9.9","upper_limit":"10.1"}],**overrides}


def test_measurement_limits_and_identity(client,headers):
    payload=inspection_data()
    result=client.post("/api/inspections",headers=headers,json=payload)
    assert result.status_code==201 and result.json()["passed"] is True
    reading=payload["measurements"][0]
    reading["lower_limit"]="11"
    assert client.post("/api/inspections",headers=headers,json=payload).status_code==422
    reading.update(lower_limit="9.9",value="100")
    assert client.post("/api/inspections",headers=headers,json=payload).status_code==422
    payload["rejection_reason"]="Over tolerance"
    result=client.post("/api/inspections",headers=headers,json=payload)
    assert result.status_code==201 and result.json()["passed"] is False
    payload["part_id"]=2
    assert client.post("/api/inspections",headers=headers,json=payload).status_code==422
    reading["value"]="NaN"
    assert client.post("/api/inspections",headers=headers,json=payload).status_code==422


def test_maintenance_deadlines_and_audit(client,headers):
    today=date.today()
    payload={"equipment_id":1,"title":"Deadline test","kind":"preventive",
             "scheduled_on":str(today),"due_on":str(today-timedelta(days=1))}
    assert client.post("/api/maintenance",headers=headers,json=payload).status_code==422
    payload["scheduled_on"]=str(today-timedelta(days=2))
    result=client.post("/api/maintenance",headers=headers,json=payload)
    work_id=result.json()["id"]
    assert next(r for r in client.get("/api/maintenance").json() if r["id"]==work_id)["overdue"]
    assert client.patch(f"/api/maintenance/{work_id}",headers=headers,json={"status":"complete"}).status_code==200
    assert not next(r for r in client.get("/api/maintenance").json() if r["id"]==work_id)["overdue"]


def test_corrective_workflow_audit(client,headers):
    report=client.post("/api/nonconformances",headers=headers,json={"equipment_id":1,"title":"Test CAPA",
            "description":"Sample","severity":"major"}).json()
    base=f"/api/nonconformances/{report['id']}"
    action=client.post(base+"/actions",headers=headers,json={"title":"Check setting","owner_id":1,
                       "due_on":str(datetime.now(UTC).date())}).json()
    assert client.patch(base,headers=headers,json={"status":"closed"}).status_code==409
    assert client.patch(base+f"/actions/{action['id']}",headers=headers,json={"status":"done"}).status_code==200
    assert client.patch(base,headers=headers,json={"status":"closed"}).status_code==200
    assert {r["action"] for r in client.get(base).json()["history"]}=={"opened","assigned","completed","status_changed"}


def test_database_constraints_and_rollback(database):
    part,_=new_part(database,1)
    with pytest.raises(IntegrityError):
        with database.begin() as conn:
            query(conn,"UPDATE inventory_balances SET usable=2 WHERE part_id=:p",p=part)
            query(conn,"UPDATE inventory_balances SET reserved=3 WHERE part_id=:p",p=part)
    with database.connect() as conn:
        assert query(conn,"SELECT usable FROM inventory_balances WHERE part_id=:p",p=part).scalar()==1


def test_dashboard_uses_clipped_union_and_exact_quality_counts(client,database,headers):
    with database.begin() as conn:
        equipment=query(conn,"""INSERT INTO equipment(code,name,type_id,location_id,status,commissioned_on)
                                 VALUES ('TEST-KPI','Test KPI',1,1,'operational','2026-08-01') RETURNING id""").scalar_one()
        batch=query(conn,"""INSERT INTO production_batches(code,part_id,equipment_id,started_at)
                             VALUES ('TEST-KPI',1,:id,'2026-09-19') RETURNING id""",id=equipment).scalar_one()
        query(conn,"""INSERT INTO downtime_events(equipment_id,started_at,ended_at,reason)
                      VALUES (:id,'2026-09-19T23:30Z','2026-09-20T01:00Z','A'),
                             (:id,'2026-09-20T00:45Z','2026-09-20T02:00Z','B')""",id=equipment)
    assert client.post("/api/inspections",headers=headers,json=inspection_data(batch_id=batch)).status_code==201
    rejected=inspection_data(batch_id=batch,rejection_reason="Oversize")
    rejected["measurements"][0]["value"]="11"
    assert client.post("/api/inspections",headers=headers,json=rejected).status_code==201
    body=client.get("/api/dashboard",params={"start":"2026-09-20","end":"2026-09-20","machine":equipment}).json()
    actual=body["current"]
    assert (actual["equipment_total"],actual["downtime_minutes"],actual["availability"])==(1,120,91.67)
    assert (actual["inspections"],actual["rejected"],actual["defect_rate"],actual["pass_rate"])==(2,1,50,50)
    assert body["previous"]["downtime_minutes"]==30


def test_access_and_request_validation(client,headers,monkeypatch):
    route="/api/inventory/1/receive"
    assert client.post(route,json={"quantity":1}).status_code==401
    assert client.post(route,headers=headers,json={"quantity":-1}).status_code==422
    assert client.post(route,headers=headers,content=b"x"*100_000).status_code==413
    assert client.get("/api/dashboard",params={"end":"0001-01-01"}).status_code==422
    assert client.get("/api/analytics/missing").status_code==422
    assert not client.get("/api/session",headers={"Authorization":"Bearer wrong"}).json()["can_write"]
    monkeypatch.setenv("FACTORYIQ_READ_ONLY","true")
    assert client.post(route,headers=headers,json={"quantity":1}).status_code==403
    monkeypatch.setenv("FACTORYIQ_DEMO_READS","false")
    assert client.get("/api/inventory").status_code==401
    assert client.get("/api/inventory",headers=headers).status_code==200


def test_reports_are_downloadable_and_cells_are_safe(client,headers):
    fields={"code":"CSV-TEST","name":"=1+1","type_id":1,"location_id":1,"status":"operational","commissioned_on":"2026-01-01"}
    assert client.post("/api/equipment",headers=headers,json=fields).status_code==201
    for key in ("equipment","inventory","inspections","downtime","maintenance"):
        response=client.get(f"/api/reports/{key}.csv")
        assert response.status_code==200 and response.headers["content-type"].startswith("text/csv")
        result=list(csv.DictReader(io.StringIO(response.text)))
        assert len(result)>0
        if key=="equipment":
            assert next(r for r in result if r["code"]=="CSV-TEST")["name"]=="'=1+1"
