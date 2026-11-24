from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import model_validator

from .common import Description, Input, Label, Notes, PositiveId, audit, conflict, required
from .db import engine, one, rows
from .operations import Actor
from .security import read_access

router = APIRouter(prefix="/api", dependencies=[Depends(read_access)])
REPORTS = """
 SELECT n.*, e.code AS equipment, (SELECT count(*) FROM corrective_actions a
 WHERE a.report_id=n.id AND a.status='open') AS open_actions
 FROM non_conformance_reports n JOIN equipment e ON e.id=n.equipment_id
"""
ACTIONS = """
 SELECT a.*,u.username AS owner,a.status='open' AND a.due_on<CURRENT_DATE AS overdue
 FROM corrective_actions a JOIN users u ON u.id=a.owner_id WHERE report_id=:id ORDER BY due_on,a.id
"""


class WorkOrder(Input):
    equipment_id: PositiveId
    title: Label
    kind: Literal["preventive","corrective"]
    scheduled_on: date
    due_on: date
    notes: Notes = ""

    @model_validator(mode="after")
    def check_dates(self):
        if self.due_on < self.scheduled_on:
            raise ValueError("Due date must be on or after the scheduled date.")
        return self


class WorkStatus(Input):
    status: Literal["scheduled","in_progress","complete"]


class Calibration(Input):
    equipment_id: PositiveId
    calibrated_on: date
    next_due_on: date
    result: Literal["pass","fail"]
    reference: Label

    @model_validator(mode="after")
    def check_dates(self):
        if self.next_due_on <= self.calibrated_on or self.calibrated_on > datetime.now(UTC).date():
            raise ValueError("Calibration must have occurred and the next due date must follow it.")
        return self


class NonConformance(Input):
    equipment_id: PositiveId
    inspection_id: PositiveId | None = None
    title: Label
    description: Description
    severity: Literal["minor","major","critical"]


class ReportStatus(Input):
    status: Literal["open","investigating","closed"]


class CorrectiveAction(Input):
    title: Label
    owner_id: PositiveId
    due_on: date


class ActionStatus(Input):
    status: Literal["open","done"]


@router.get("/maintenance")
def maintenance():
    with engine().connect() as conn:
        return rows(conn,"SELECT * FROM maintenance_queue ORDER BY overdue DESC,due_on,id")


@router.post("/maintenance", status_code=201)
def create_work_order(data: WorkOrder, actor: Actor):
    with engine().begin() as conn:
        row = one(conn,"""INSERT INTO maintenance_work_orders(equipment_id,title,kind,scheduled_on,due_on,notes)
                          VALUES (:equipment_id,:title,:kind,:scheduled_on,:due_on,:notes) RETURNING *""",
                  **data.model_dump())
        audit(conn,actor,"scheduled","work_order",row["id"],due_on=data.due_on)
        return dict(row)


@router.patch("/maintenance/{work_id}")
def update_work_order(work_id: PositiveId, data: WorkStatus, actor: Actor):
    with engine().begin() as conn:
        prior = required(one(conn,"SELECT * FROM maintenance_work_orders WHERE id=:id FOR UPDATE",id=work_id),"Work order")
        if prior["status"] == data.status:
            return dict(prior)
        if prior["status"] == "complete" or data.status == "scheduled":
            conflict("Work orders cannot move back to a previous state.")
        row = one(conn,"""UPDATE maintenance_work_orders SET status=:s,
                          completed_at=CASE WHEN :s='complete' THEN now() END WHERE id=:id RETURNING *""",
                  s=data.status,id=work_id)
        audit(conn,actor,"status_changed","work_order",work_id,before=prior["status"],after=data.status)
        return dict(row)


@router.get("/calibrations")
def calibration_history():
    with engine().connect() as conn:
        return rows(conn,"""SELECT c.*,e.code AS equipment,
                            c.next_due_on<CURRENT_DATE AND NOT EXISTS
                            (SELECT 1 FROM calibration_records newer WHERE newer.equipment_id=c.equipment_id
                             AND (newer.calibrated_on,newer.id) > (c.calibrated_on,c.id)) AS overdue
                            FROM calibration_records c JOIN equipment e ON e.id=c.equipment_id
                            ORDER BY c.calibrated_on DESC,c.id DESC""")


@router.post("/calibrations", status_code=201)
def record_calibration(data: Calibration, actor: Actor):
    with engine().begin() as conn:
        row = one(conn,"""INSERT INTO calibration_records(equipment_id,calibrated_on,next_due_on,result,reference)
                          VALUES (:equipment_id,:calibrated_on,:next_due_on,:result,:reference) RETURNING *""",
                  **data.model_dump())
        audit(conn,actor,"recorded","calibration",row["id"],result=data.result)
        return dict(row)


@router.get("/nonconformances")
def nonconformances():
    with engine().connect() as conn:
        return rows(conn,REPORTS+" ORDER BY n.opened_at DESC,n.id DESC")


@router.get("/nonconformances/{report_id}")
def nonconformance_detail(report_id: PositiveId):
    with engine().connect() as conn:
        report = dict(required(one(conn,REPORTS+" WHERE n.id=:id",id=report_id),"Non-conformance"))
        report["actions"] = rows(conn,ACTIONS,id=report_id)
        report["history"] = rows(conn,"""SELECT al.*,u.username FROM audit_logs al JOIN users u ON u.id=al.user_id
                           WHERE (al.entity='non_conformance' AND al.entity_id=:id)
                           OR (al.entity='corrective_action' AND al.entity_id IN
                               (SELECT id FROM corrective_actions WHERE report_id=:id))
                           ORDER BY al.occurred_at DESC,al.id DESC""",id=report_id)
        return report


@router.post("/nonconformances", status_code=201)
def create_nonconformance(data: NonConformance, actor: Actor):
    with engine().begin() as conn:
        if data.inspection_id:
            inspection = required(one(conn,"""SELECT i.passed,b.equipment_id FROM quality_inspections i
                              JOIN production_batches b ON b.id=i.batch_id WHERE i.id=:id""",id=data.inspection_id),"Inspection")
            if inspection["passed"] or inspection["equipment_id"] != data.equipment_id:
                raise HTTPException(422,"Choose a failed inspection from this machine.")
        row = one(conn,"""INSERT INTO non_conformance_reports(equipment_id,inspection_id,title,description,severity)
                          VALUES (:equipment_id,:inspection_id,:title,:description,:severity) RETURNING *""",
                  **data.model_dump())
        audit(conn,actor,"opened","non_conformance",row["id"],severity=data.severity)
        return dict(row)


def locked_report(conn, report_id):
    return required(one(conn,"SELECT * FROM non_conformance_reports WHERE id=:id FOR UPDATE",id=report_id),"Non-conformance")


@router.patch("/nonconformances/{report_id}")
def update_report(report_id: PositiveId, data: ReportStatus, actor: Actor):
    with engine().begin() as conn:
        prior = locked_report(conn,report_id)
        if prior["status"] == data.status:
            return dict(prior)
        if prior["status"] == "closed" or data.status == "open":
            conflict("Non-conformances cannot move back to a previous state.")
        if data.status == "closed" and one(conn,"SELECT id FROM corrective_actions WHERE report_id=:id AND status='open' LIMIT 1",id=report_id):
            conflict("Complete every corrective action before closing the report.")
        row = one(conn,"""UPDATE non_conformance_reports SET status=:s,
                          closed_at=CASE WHEN :s='closed' THEN now() END WHERE id=:id RETURNING *""",
                  s=data.status,id=report_id)
        audit(conn,actor,"status_changed","non_conformance",report_id,before=prior["status"],after=data.status)
        return dict(row)


@router.post("/nonconformances/{report_id}/actions", status_code=201)
def assign_corrective_action(report_id: PositiveId, data: CorrectiveAction, actor: Actor):
    with engine().begin() as conn:
        report = locked_report(conn,report_id)
        if report["status"] == "closed":
            conflict("A closed report cannot accept a corrective action.")
        if data.due_on < report["opened_at"].date():
            raise HTTPException(422,"Action deadline cannot precede the report date.")
        required(one(conn,"SELECT id FROM users WHERE id=:id AND role='operator'",id=data.owner_id),"Operator")
        row = one(conn,"""INSERT INTO corrective_actions(report_id,title,owner_id,due_on)
                          VALUES (:id,:title,:owner_id,:due_on) RETURNING *""",id=report_id,**data.model_dump())
        audit(conn,actor,"assigned","corrective_action",row["id"],report_id=report_id,owner_id=data.owner_id,due_on=data.due_on)
        return dict(row)


@router.patch("/nonconformances/{report_id}/actions/{action_id}")
def update_corrective_action(report_id: PositiveId, action_id: PositiveId, data: ActionStatus, actor: Actor):
    with engine().begin() as conn:
        report = locked_report(conn,report_id)
        prior = required(one(conn,"SELECT * FROM corrective_actions WHERE id=:id AND report_id=:r",id=action_id,r=report_id),"Action")
        if prior["status"] == data.status:
            return dict(prior)
        if report["status"] == "closed" or data.status == "open":
            conflict("Only an open action on an active report can be completed.")
        row = one(conn,"UPDATE corrective_actions SET status='done',completed_at=now() WHERE id=:id RETURNING *",id=action_id)
        audit(conn,actor,"completed","corrective_action",action_id,report_id=report_id)
        return dict(row)
