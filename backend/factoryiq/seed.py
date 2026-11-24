"""Seed a fictional plant once. Run with python -m factoryiq.seed."""

import argparse
import random
from datetime import UTC, date, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5

from .db import engine, query


def seed(anchor):
    rng = random.Random(4281)
    today = datetime.combine(anchor, time.min, UTC)

    with engine().begin() as conn:
        def run(sql, **params):
            return query(conn, sql, **params)

        def add(sql, **params):
            return run(sql + " RETURNING id", **params).scalar_one()

        marker = run(
            "INSERT INTO demo_seed VALUES (1,:anchor) ON CONFLICT DO NOTHING RETURNING id",
            anchor=anchor,
        ).scalar()
        if marker is None:
            return False

        run("INSERT INTO users(username,role) VALUES ('Demo operator','operator'),('Demo viewer','viewer')")
        operator = run("SELECT id FROM users WHERE role='operator'").scalar_one()
        names = ["Linear axis", "Vision cell", "Conveyor", "Servo press", "Sorter"]
        types = [add("INSERT INTO equipment_types(name) VALUES (:name)", name=n) for n in names]
        areas = [add("INSERT INTO facility_locations(name) VALUES (:name)", name=n) for n in
                 ("Assembly East", "Assembly West", "Finishing", "Outbound")]
        machines = []
        for i in range(20):
            kind = i % len(names)
            position = i // len(names) + 1
            machines.append(add(
                """INSERT INTO equipment(code,name,type_id,location_id,status,commissioned_on)
                   VALUES (:code,:name,:type,:location,:status,:day)""",
                code=f"EQ-{101+i}", name=f"{names[kind]} {position:02d}", type=types[kind],
                location=areas[position-1], status="maintenance" if i in (2, 8, 14) else
                "offline" if i == 17 else "operational", day=anchor - timedelta(days=800-i*23),
            ))
        supplier_names = ("Alder Precision", "Blue Ridge Drives", "Cobalt Optics", "Delta Fasteners",
                          "Elm Motion", "Ferro Industrial", "Granite Seals", "Harbour Bearings",
                          "Juniper Metals", "Keystone Logistics")
        suppliers = [add("INSERT INTO suppliers(code,name) VALUES (:code,:name)",
                         code=f"SUP-{i+1:02}", name=n) for i, n in enumerate(supplier_names)]
        for i in range(50):
            part = add(
                "INSERT INTO parts(sku,name,supplier_id,reorder_point) VALUES (:sku,:name,:supplier,:point)",
                sku=f"PT-{1000+i}", name=f"{('Bearing','Guide rail','Optical bracket','Coupling','Seal')[i%5]} {i//5+1:02}",
                supplier=suppliers[i%10], point=48 if i%6 == 0 else 12,
            )
            batch_start = today - timedelta(days=70)
            machine = machines[i%20]
            batch = add(
                "INSERT INTO production_batches(code,part_id,equipment_id,started_at) VALUES (:code,:p,:e,:t)",
                code=f"LOT-{2400+i}", p=part, e=machine, t=batch_start,
            )
            usable = 0
            for j in range(7):
                qty = rng.randint(5, 11) if i%6 == 0 else rng.randint(8, 30)
                usable += qty
                run("""INSERT INTO inventory_movements(part_id,kind,quantity,occurred_at)
                       VALUES (:p,'receive',:q,:t)""",
                    p=part, q=qty, t=batch_start + timedelta(days=j*4))
            for j in range(4):
                qty = rng.randint(4, 8)
                t = batch_start + timedelta(days=32+j*7)
                status = "released" if j == 2 else "consumed"
                k = "release" if j == 2 else "consume"
                reservation = add(
                    """INSERT INTO inventory_reservations(part_id,batch_id,quantity,status,request_id,created_at,closed_at)
                       VALUES (:p,:b,:q,:s,:key,:t,:end)""",
                    p=part,b=batch,q=qty,s=status,key=uuid5(NAMESPACE_URL,f"factoryiq/{i}/{j}"),
                    t=t,end=t+timedelta(hours=1),
                )
                for kind, stamp in (("reserve",t), (k,t+timedelta(hours=1))):
                    run("""INSERT INTO inventory_movements(part_id,reservation_id,kind,quantity,occurred_at)
                           VALUES (:p,:r,:k,:q,:t)""", p=part,r=reservation,k=kind,q=qty,t=stamp)
                if k == "consume":
                    usable -= qty
            rejected = 2 + i%3
            run("""INSERT INTO inventory_movements(part_id,kind,quantity,occurred_at,notes)
                   VALUES (:p,'reject',:q,:t,'Incoming surface damage')""",
                p=part,q=rejected,t=today-timedelta(days=3))
            run("INSERT INTO inventory_balances(part_id,usable,rejected) VALUES (:p,:u,:r)",
                p=part,u=usable-rejected,r=rejected)

            first_failed = None
            for j in range(10):
                age = rng.randrange(1,60)
                inspected_at = today - timedelta(days=age) + timedelta(hours=rng.randrange(6,18))
                failed = j == 0 or rng.random() < (0.04 + (age >= 30)*0.08 + (i%10 in (1,4))*0.08)
                inspection = add(
                    """INSERT INTO quality_inspections(batch_id,part_id,inspected_at,passed,rejection_reason)
                       VALUES (:b,:p,:t,:ok,:reason)""",
                    b=batch,p=part,t=inspected_at,ok=not failed,reason="Bore diameter above tolerance" if failed else None,
                )
                run("""INSERT INTO inspection_measurements(inspection_id,characteristic,unit,value,lower_limit,upper_limit)
                       VALUES (:id,'Bore diameter','mm',:value,9.90,10.10),
                              (:id,'Overall length','mm',:length,49.75,50.25)""",
                    id=inspection,value=10.16 if failed else rng.randint(991,1009)/100,
                    length=rng.randint(4980,5020)/100)
                if first_failed is None:
                    first_failed = (inspection, inspected_at)
            inspection, opened = first_failed
            status = ("closed","closed","investigating","open","open")[i%5]
            report = add(
                """INSERT INTO non_conformance_reports(equipment_id,inspection_id,title,description,severity,status,opened_at,closed_at)
                   VALUES (:e,:insp,:title,:d,:severity,:s,:t,:end)""",
                e=machine,insp=inspection,title=f"Bore drift · LOT-{2400+i}",
                d="Dimensional inspection found an oversize bore. Isolate affected units and inspect tooling.",
                severity=("minor","major","critical")[i%3],s=status,t=opened,
                end=min(opened+timedelta(days=3),today) if status=="closed" else None,
            )
            if i%5 != 4:
                run("""INSERT INTO corrective_actions(report_id,title,owner_id,due_on,status,completed_at)
                       VALUES (:r,'Check tool offset and verify first article',:u,:day,:s,:end)""",
                    r=report,u=operator,day=opened.date()+timedelta(days=7),
                    s="done" if status=="closed" else "open",
                    end=min(opened+timedelta(days=2),today) if status=="closed" else None)
        for i in range(50):
            scheduled = anchor + timedelta(days=(i-32)*2)
            completed = i < 26
            run("""INSERT INTO maintenance_work_orders(equipment_id,title,kind,scheduled_on,due_on,status,completed_at)
                   VALUES (:e,:title,:kind,:schedule,:due,:status,:complete)""",
                e=machines[i%20],title=("Lubrication and inspection","Verify drive tension","Replace worn guide")[i%3],
                kind="corrective" if i%3==2 else "preventive",schedule=scheduled,due=scheduled+timedelta(days=7),
                status="complete" if completed else "in_progress" if i%4==0 else "scheduled",
                complete=datetime.combine(scheduled+timedelta(days=3),time(12),UTC) if completed else None)
        for i, equipment in enumerate(machines):
            calibrated = anchor - timedelta(days=35+i*3)
            run("""INSERT INTO calibration_records(equipment_id,calibrated_on,next_due_on,result,reference)
                   VALUES (:e,:cal,:due,:result,:ref)""",e=equipment,cal=calibrated,due=calibrated+timedelta(days=90),
                result="fail" if i==8 else "pass",ref=f"CAL-{1020+i}")
        offsets = [1, 5, 10, 13, 18, 23, 28, 34, 42, 51, 60]
        for i, equipment in enumerate(machines):
            for day in offsets[:4+i%8]:
                start = today - timedelta(days=day) + timedelta(hours=rng.randrange(7,20))
                run("""INSERT INTO downtime_events(equipment_id,started_at,ended_at,reason,source_key)
                       VALUES (:e,:start,:end,:reason,:key)""",
                    e=equipment,start=start,end=start+timedelta(minutes=rng.randint(12,175)*(2 if i%6==0 else 1)),
                    reason=("Drive alarm","Feed jam","Unplanned stop")[i%3],key=f"demo-stop-{i}-{day}")
        sorter = [e for i,e in enumerate(machines) if i%5 == 4]
        events = []
        for i in range(5000):
            equipment = sorter[i%4]
            stamp = today - timedelta(days=59) + timedelta(minutes=i*16)
            fault = rng.choices([None,"LANE_JAM","SENSOR_TIMEOUT","DRIVE_ALARM"],[96,2,1,1])[0]
            lane = "A" if i%3 else "B"
            events.append(dict(e=equipment,key=f"synthetic-{i}",t=stamp,k="jam" if fault=="LANE_JAM" else
                               "fault" if fault else "entry" if (i//4)%2==0 else "exit",lane=lane,f=fault))
        from sqlalchemy import text
        conn.execute(text("""INSERT INTO sorter_fault_events(equipment_id,event_key,occurred_at,kind,lane,fault_code)
                             VALUES (:e,:key,:t,:k,:lane,:f)"""),events)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor", type=date.fromisoformat, default=datetime.now(UTC).date())
    print("Seeded synthetic plant." if seed(parser.parse_args().anchor) else "Synthetic plant already seeded.")
