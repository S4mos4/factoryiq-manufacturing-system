import os
from secrets import compare_digest

from fastapi import HTTPException, Request

from .db import engine, one


def enabled(name):
    return os.getenv(name, "").lower() == "true"


def is_operator(request):
    scheme, _, provided = request.headers.get("authorization", "").partition(" ")
    expected = os.getenv("FACTORYIQ_OPERATOR_TOKEN", "")
    return (scheme.lower() == "bearer" and len(expected) >= 24
            and compare_digest(provided.encode(), expected.encode()))


def read_access(request: Request):
    if not (enabled("FACTORYIQ_DEMO_READS") or is_operator(request)):
        raise HTTPException(401, "Viewer access requires an operator token on this instance.")


def write_access(request: Request):
    if enabled("FACTORYIQ_READ_ONLY"):
        raise HTTPException(403, "This instance is read-only.")
    if not is_operator(request):
        raise HTTPException(401, "A valid operator token is required.")
    with engine().connect() as conn:
        actor = one(conn, "SELECT id FROM users WHERE username='Demo operator' AND role='operator'")
    if not actor:
        raise HTTPException(503, "Operator has not been provisioned.")
    return actor["id"]
