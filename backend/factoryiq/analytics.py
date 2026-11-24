from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from .common import PositiveId, required
from .db import engine, one, rows, sql_file
from .security import read_access

router = APIRouter(prefix="/api", dependencies=[Depends(read_access)])
Analysis = Literal["supplier_defects","batch_rejections","maintenance_due","low_stock",
                   "reliability","fault_frequency","downtime_by_machine","defect_trend"]


def date_bounds(start, end):
    end = end or datetime.now(UTC).date()
    earliest, latest = date(1900,1,1), date(2199,12,31)
    if not earliest <= end <= latest:
        raise HTTPException(422,"Choose a date range of 1 to 366 days between 1900 and 2199.")
    start = start or max(earliest,end-timedelta(days=29))
    if start<earliest or not 0 <= (end-start).days < 366:
        raise HTTPException(422,"Choose a date range of 1 to 366 days between 1900 and 2199.")
    return datetime.combine(start,time.min,UTC),datetime.combine(end+timedelta(days=1),time.min,UTC)


@router.get("/dashboard")
def dashboard(start: date | None = None, end: date | None = None, machine: PositiveId | None = None):
    start_at,end_at = date_bounds(start,end)
    params = dict(start=start_at,end=end_at,machine=machine)
    with engine().connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        if machine:
            required(one(conn,"SELECT id FROM equipment WHERE id=:id",id=machine),"Equipment")
        metrics = rows(conn,sql_file("dashboard"),previous=start_at-(end_at-start_at),**params)
        return {
            "period": {"start":start_at.date(),"end":(end_at-timedelta(days=1)).date()},
            **{row["period"]:row for row in metrics},
            "trend":rows(conn,sql_file("defect_trend"),**params),
            "downtime":rows(conn,sql_file("downtime_by_machine"),**params)[:8],
            "faults":rows(conn,sql_file("fault_frequency"),**params)[:8],
        }


@router.get("/analytics/{analysis}")
def analytics(analysis: Analysis, start: date | None = None, end: date | None = None, machine: PositiveId | None = None):
    start_at,end_at=date_bounds(start,end)
    with engine().connect() as conn:
        return rows(conn,sql_file(analysis),start=start_at,end=end_at,machine=machine)
