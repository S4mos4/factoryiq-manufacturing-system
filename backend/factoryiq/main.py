import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .analytics import router as analytics
from .db import engine, query
from .middleware import LimitApiBody
from .operations import router as operations
from .reports import router as reports
from .security import Operator, enabled
from .sorter import router as sorter
from .workflows import router as workflows

docs = not enabled("FACTORYIQ_DISABLE_DOCS")
app = FastAPI(title="FactoryIQ API", version="1.0.0",
              docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
              openapi_url="/openapi.json" if docs else None)
app.add_middleware(LimitApiBody)
allowed_hosts = os.getenv("FACTORYIQ_ALLOWED_HOSTS")
if allowed_hosts:
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=[host.strip() for host in allowed_hosts.split(",")])
for router in (operations,workflows,analytics,sorter,reports):
    app.include_router(router)


@app.exception_handler(IntegrityError)
@app.exception_handler(DataError)
async def database_constraint_error(_request: Request, _error: Exception):
    return JSONResponse({"detail":"The operation conflicts with a database constraint or an existing record."},status_code=409)


@app.exception_handler(OperationalError)
async def db_unavailable(_request: Request, _error: OperationalError):
    return JSONResponse({"detail":"The database is temporarily unavailable."},status_code=503)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError):
    return JSONResponse({"detail":[{"loc":item["loc"],"msg":item["msg"]} for item in error.errors()]},status_code=422)


@app.middleware("http")
async def security_headers(request, call_next):
    path = request.url.path
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    if path in {"/","/index.html"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
    return response


@app.get("/health")
def health():
    with engine().connect() as conn:
        query(conn,"SELECT 1")
    return {"status":"ok"}


@app.get("/api/session")
def session(operator: Operator):
    return {"operator_authenticated":operator,"can_read":operator or enabled("FACTORYIQ_DEMO_READS"),
            "can_write":operator and not enabled("FACTORYIQ_READ_ONLY"),
            "read_only":enabled("FACTORYIQ_READ_ONLY"),"synthetic":enabled("FACTORYIQ_DEMO_READS")}


static_directory = os.getenv("FACTORYIQ_STATIC_DIR")
if static_directory:
    app.mount("/",StaticFiles(directory=Path(static_directory),html=True),name="frontend")
