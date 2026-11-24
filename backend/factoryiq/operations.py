from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, model_validator

from .common import Description, Input, Label, Notes, PositiveId, Quantity, audit, conflict, required
from .db import engine, one, query, rows
from .security import read_access, write_access

router = APIRouter(prefix="/api", dependencies=[Depends(read_access)])
Actor = Annotated[int, Depends(write_access)]

EQUIPMENT_LIST = """
 SELECT e.*, t.name AS type, l.name AS location FROM equipment e
 JOIN equipment_types t ON t.id=e.type_id JOIN facility_locations l ON l.id=e.location_id
"""
INSPECTION_LIST = """
 SELECT i.*, p.sku, b.code AS batch, e.code AS equipment
 FROM quality_inspections i JOIN parts p ON p.id=i.part_id
 JOIN production_batches b ON b.id=i.batch_id JOIN equipment e ON e.id=b.equipment_id
"""


class Equipment(Input):
    code: Label
    name: Label
    type_id: PositiveId
    location_id: PositiveId
    status: Literal["operational", "maintenance", "offline"]
    commissioned_on: date


class StockChange(Input):
    quantity: Quantity
    notes: Notes = ""


class Rejection(StockChange):
    notes: Description


class Reservation(Input):
    batch_id: PositiveId
    quantity: Quantity
    request_id: UUID


MeasurementValue = Annotated[Decimal, Field(max_digits=14, decimal_places=4, allow_inf_nan=False)]


class Measurement(Input):
    characteristic: Label
    unit: Label
    value: MeasurementValue
    lower_limit: MeasurementValue
    upper_limit: MeasurementValue

    @model_validator(mode="after")
    def check_bounds(self):
        if self.lower_limit > self.upper_limit:
            raise ValueError("Lower limit must be at or below upper limit.")
        return self

    @property
    def passed(self):
        return self.lower_limit <= self.value <= self.upper_limit


class Inspection(Input):
    part_id: PositiveId
    batch_id: PositiveId
    inspected_at: AwareDatetime
    rejection_reason: Description | None = None
    measurements: Annotated[list[Measurement], Field(min_length=1, max_length=25)]

    @model_validator(mode="after")
    def check_result(self):
        if len({m.characteristic.strip().casefold() for m in self.measurements}) != len(self.measurements):
            raise ValueError("Use a distinct characteristic for each measurement.")
        if any(not m.passed for m in self.measurements) and not self.rejection_reason:
            raise ValueError("A rejection reason is required for out-of-tolerance measurements.")
        if self.inspected_at > datetime.now(UTC) + timedelta(minutes=1):
            raise ValueError("Inspection timestamp cannot be in the future.")
        return self


@router.get("/lookups")
def lookups():
    with engine().connect() as conn:
        return {
            "types": rows(conn, "SELECT id,name FROM equipment_types ORDER BY name"),
            "locations": rows(conn, "SELECT id,name FROM facility_locations ORDER BY name"),
            "equipment": rows(conn, "SELECT id,code,name FROM equipment ORDER BY code"),
            "parts": rows(conn, "SELECT id,sku,name FROM parts ORDER BY sku"),
            "suppliers": rows(conn, "SELECT id,code,name FROM suppliers ORDER BY code"),
            "batches": rows(conn, "SELECT id,code,part_id,equipment_id FROM production_batches ORDER BY code"),
            "users": rows(conn, "SELECT id,username FROM users WHERE role='operator' ORDER BY username"),
        }


@router.get("/equipment")
def equipment_list():
    with engine().connect() as conn:
        return rows(conn, EQUIPMENT_LIST + " ORDER BY e.code")


@router.get("/equipment/{equipment_id}")
def equipment_detail(equipment_id: PositiveId):
    with engine().connect() as conn:
        equipment = dict(required(one(conn,EQUIPMENT_LIST + " WHERE e.id=:id",id=equipment_id),"Equipment"))
        return {
            "equipment": equipment,
            "maintenance": rows(conn,"SELECT * FROM maintenance_queue WHERE equipment_id=:id ORDER BY due_on DESC",id=equipment_id),
            "calibration": rows(conn,"SELECT * FROM calibration_records WHERE equipment_id=:id ORDER BY calibrated_on DESC",id=equipment_id),
        }


@router.post("/equipment", status_code=201)
def register_equipment(data: Equipment, actor: Actor):
    with engine().begin() as conn:
        row = one(conn, """INSERT INTO equipment(code,name,type_id,location_id,status,commissioned_on)
                           VALUES (:code,:name,:type_id,:location_id,:status,:commissioned_on) RETURNING *""",
                  **data.model_dump())
        audit(conn,actor,"registered","equipment",row["id"],status=data.status)
        return dict(row)


@router.put("/equipment/{equipment_id}")
def edit_equipment(equipment_id: PositiveId, data: Equipment, actor: Actor):
    with engine().begin() as conn:
        before = required(one(conn,"SELECT * FROM equipment WHERE id=:id FOR UPDATE",id=equipment_id),"Equipment")
        row = one(conn, """UPDATE equipment SET code=:code,name=:name,type_id=:type_id,location_id=:location_id,
                           status=:status,commissioned_on=:commissioned_on WHERE id=:id RETURNING *""",
                  id=equipment_id,**data.model_dump())
        changes = {key: {"from":before[key],"to":row[key]} for key in data.model_fields_set if before[key] != row[key]}
        if changes:
            audit(conn,actor,"edited","equipment",equipment_id,changes=changes)
        return dict(row)


@router.get("/inventory")
def inventory_list():
    with engine().connect() as conn:
        return rows(conn,"SELECT * FROM inventory_availability ORDER BY sku")


@router.get("/inventory/{part_id}")
def inventory_detail(part_id: PositiveId):
    with engine().connect() as conn:
        part = required(one(conn,"SELECT * FROM inventory_availability WHERE id=:id",id=part_id),"Part")
        return {
            "part": dict(part),
            "movements": rows(conn,"SELECT * FROM inventory_movements WHERE part_id=:id ORDER BY occurred_at DESC,id DESC",id=part_id),
            "reservations": rows(conn,"""SELECT r.*,b.code AS batch FROM inventory_reservations r
                                         JOIN production_batches b ON b.id=r.batch_id
                                         WHERE r.part_id=:id ORDER BY r.created_at DESC,r.id DESC""",id=part_id),
        }


def lock_stock(conn, part_id):
    required(one(conn,"SELECT id FROM parts WHERE id=:id FOR UPDATE",id=part_id),"Part")
    query(conn,"INSERT INTO inventory_balances(part_id) VALUES (:id) ON CONFLICT DO NOTHING",id=part_id)
    return one(conn,"SELECT * FROM inventory_balances WHERE part_id=:id",id=part_id)


def movement(conn, actor, part_id, kind, quantity, notes="", reservation_id=None):
    row = one(conn,"""INSERT INTO inventory_movements(part_id,reservation_id,kind,quantity,notes)
                      VALUES (:p,:r,:k,:q,:n) RETURNING *""",p=part_id,r=reservation_id,k=kind,q=quantity,n=notes)
    audit(conn,actor,kind,"inventory_movement",row["id"],part_id=part_id,quantity=quantity)
    return dict(row)


@router.post("/inventory/{part_id}/receive", status_code=201)
def receive(part_id: PositiveId, data: StockChange, actor: Actor):
    with engine().begin() as conn:
        lock_stock(conn,part_id)
        query(conn,"UPDATE inventory_balances SET usable=usable+:q WHERE part_id=:p",q=data.quantity,p=part_id)
        return movement(conn,actor,part_id,"receive",data.quantity,data.notes)


@router.post("/inventory/{part_id}/reject", status_code=201)
def reject(part_id: PositiveId, data: Rejection, actor: Actor):
    with engine().begin() as conn:
        stock = lock_stock(conn,part_id)
        if data.quantity > stock["usable"] - stock["reserved"]:
            conflict("Only unreserved usable stock can be rejected.")
        query(conn,"UPDATE inventory_balances SET usable=usable-:q,rejected=rejected+:q WHERE part_id=:p",
              q=data.quantity,p=part_id)
        return movement(conn,actor,part_id,"reject",data.quantity,data.notes)


@router.post("/inventory/{part_id}/reserve", status_code=201)
def reserve(part_id: PositiveId, data: Reservation, actor: Actor):
    with engine().begin() as conn:
        stock = lock_stock(conn,part_id)
        prior = one(conn,"SELECT * FROM inventory_reservations WHERE request_id=:key",key=data.request_id)
        if prior:
            if (prior["part_id"],prior["batch_id"],prior["quantity"]) != (part_id,data.batch_id,data.quantity):
                conflict("The reservation request ID belongs to different inputs.")
            return dict(prior)
        batch = required(one(conn,"SELECT part_id,started_at FROM production_batches WHERE id=:id",id=data.batch_id),"Batch")
        if batch["part_id"] != part_id or batch["started_at"] > datetime.now(UTC):
            conflict("The batch must be started and assigned to this part.")
        if data.quantity > stock["usable"] - stock["reserved"]:
            conflict("Insufficient unreserved usable stock.")
        row = one(conn,"""INSERT INTO inventory_reservations(part_id,batch_id,quantity,request_id)
                          VALUES (:p,:b,:q,:key) RETURNING *""",
                  p=part_id,b=data.batch_id,q=data.quantity,key=data.request_id)
        query(conn,"UPDATE inventory_balances SET reserved=reserved+:q WHERE part_id=:p",q=data.quantity,p=part_id)
        movement(conn,actor,part_id,"reserve",data.quantity,reservation_id=row["id"])
        return dict(row)


@router.post("/inventory/{part_id}/reservations/{reservation_id}/{operation}")
def close_reservation(part_id: PositiveId, reservation_id: PositiveId,
                      operation: Literal["release","consume"], actor: Actor):
    with engine().begin() as conn:
        lock_stock(conn,part_id)
        row = required(one(conn,"SELECT * FROM inventory_reservations WHERE id=:r AND part_id=:p",
                           r=reservation_id,p=part_id),"Reservation")
        status = "consumed" if operation == "consume" else "released"
        if row["status"] == status:
            return dict(row)
        if row["status"] != "active":
            conflict("The reservation has already been closed.")
        quantity = row["quantity"]
        query(conn,"UPDATE inventory_balances SET reserved=reserved-:q,usable=usable-:used WHERE part_id=:p",
              q=quantity,used=quantity if operation=="consume" else 0,p=part_id)
        closed = one(conn,"UPDATE inventory_reservations SET status=:s,closed_at=now() WHERE id=:id RETURNING *",
                     s=status,id=reservation_id)
        movement(conn,actor,part_id,operation,quantity,reservation_id=reservation_id)
        return dict(closed)


@router.get("/inspections")
def inspections():
    with engine().connect() as conn:
        return rows(conn,INSPECTION_LIST + " ORDER BY i.inspected_at DESC,i.id DESC")


@router.get("/inspections/{inspection_id}")
def inspection_detail(inspection_id: PositiveId):
    with engine().connect() as conn:
        row = dict(required(one(conn,INSPECTION_LIST+" WHERE i.id=:id",id=inspection_id),"Inspection"))
        row["measurements"] = rows(conn,"SELECT * FROM inspection_measurements WHERE inspection_id=:id ORDER BY id",id=inspection_id)
        return row


@router.post("/inspections", status_code=201)
def record_inspection(data: Inspection, actor: Actor):
    with engine().begin() as conn:
        batch = required(one(conn,"SELECT part_id,started_at FROM production_batches WHERE id=:id",id=data.batch_id),"Batch")
        if batch["part_id"] != data.part_id or data.inspected_at < batch["started_at"]:
            raise HTTPException(422,"Inspection must follow batch start and use its assigned part.")
        passed = all(m.passed for m in data.measurements)
        row = one(conn,"""INSERT INTO quality_inspections(batch_id,part_id,inspected_at,passed,rejection_reason)
                          VALUES (:b,:p,:t,:ok,:reason) RETURNING *""",
                  b=data.batch_id,p=data.part_id,t=data.inspected_at,ok=passed,
                  reason=None if passed else data.rejection_reason)
        for reading in data.measurements:
            query(conn,"""INSERT INTO inspection_measurements(inspection_id,characteristic,unit,value,lower_limit,upper_limit)
                          VALUES (:id,:characteristic,:unit,:value,:lower_limit,:upper_limit)""",
                  id=row["id"],**reading.model_dump())
        audit(conn,actor,"recorded","inspection",row["id"],passed=passed,batch_id=data.batch_id)
        return dict(row)
