import json
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .db import query


Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
PositiveId = Annotated[int, Field(gt=0, le=2147483647)]
Quantity = Annotated[int, Field(gt=0, le=1000000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


def required(row, label):
    if row is None:
        raise HTTPException(404, f"{label} not found.")
    return row


def conflict(message):
    raise HTTPException(409, message)


def audit(conn, actor, action, entity, entity_id, **details):
    query(conn, """
        INSERT INTO audit_logs(user_id,action,entity,entity_id,details)
        VALUES (:u,:a,:e,:id,CAST(:d AS jsonb))
    """, u=actor,a=action,e=entity,id=entity_id,d=json.dumps(details,default=str))
