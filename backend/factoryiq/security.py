import os
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import engine, one

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="OperatorToken")


def enabled(name):
    return os.getenv(name, "").lower() == "true"


def is_operator(credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]):
    expected = os.getenv("FACTORYIQ_OPERATOR_TOKEN", "")
    return bool(credentials and len(expected) >= 24 and
                compare_digest(credentials.credentials.encode(), expected.encode()))


Operator = Annotated[bool, Depends(is_operator)]


def unauthorized(message):
    raise HTTPException(401, message, headers={"WWW-Authenticate":"Bearer"})


def read_access(operator: Operator):
    if not (enabled("FACTORYIQ_DEMO_READS") or operator):
        unauthorized("Viewer access requires an operator token on this instance.")


def write_access(operator: Operator):
    if enabled("FACTORYIQ_READ_ONLY"):
        raise HTTPException(403, "This instance is read-only.")
    if not operator:
        unauthorized("A valid operator token is required.")
    with engine().connect() as conn:
        actor = one(conn, "SELECT id FROM users WHERE username='Demo operator' AND role='operator'")
    if not actor:
        raise HTTPException(503, "Operator has not been provisioned.")
    return actor["id"]
