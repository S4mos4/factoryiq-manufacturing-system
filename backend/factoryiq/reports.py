import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from .db import engine, query
from .operations import EQUIPMENT_LIST, INSPECTION_LIST
from .security import read_access

router = APIRouter(prefix="/api/reports", dependencies=[Depends(read_access)])
REPORTS = {
    "equipment": EQUIPMENT_LIST+" ORDER BY e.code",
    "inventory": "SELECT * FROM inventory_availability ORDER BY sku",
    "inspections": INSPECTION_LIST+" ORDER BY i.inspected_at DESC,i.id DESC",
    "downtime": """SELECT d.id,e.code AS equipment,d.started_at,d.ended_at,d.reason,
                    round(extract(epoch FROM d.ended_at-d.started_at)/60,2) AS minutes
                    FROM downtime_events d JOIN equipment e ON e.id=d.equipment_id
                    ORDER BY d.started_at DESC,d.id DESC""",
    "maintenance": "SELECT * FROM maintenance_queue ORDER BY due_on,id",
}


def csv_cell(value):
    if isinstance(value,str) and (value.startswith(("\t","\r","\n")) or value.lstrip().startswith(("=","+","-","@"))):
        return "'"+value
    return value


@router.get("/{kind}.csv")
def report(kind: Literal["equipment","inventory","inspections","downtime","maintenance"]):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    with engine().connect() as conn:
        result = query(conn,REPORTS[kind])
        writer.writerow(result.keys())
        writer.writerows([csv_cell(value) for value in row] for row in result)
    return Response(out.getvalue(),media_type="text/csv",
                    headers={"Content-Disposition":f'attachment; filename="factoryiq-{kind}.csv"'})
