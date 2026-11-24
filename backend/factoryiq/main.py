from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError

from .analytics import router as analytics
from .db import engine, query
from .operations import router as operations
from .sorter import router as sorter
from .workflows import router as workflows

app = FastAPI(title="FactoryIQ API", version="1.0.0")
app.include_router(operations)
app.include_router(workflows)
app.include_router(analytics)
app.include_router(sorter)


@app.exception_handler(IntegrityError)
@app.exception_handler(DataError)
async def database_constraint_error(_request: Request, _error: Exception):
    return JSONResponse({"detail":"The operation conflicts with a database constraint or an existing record."},status_code=409)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError):
    return JSONResponse({"detail":[{"loc":item["loc"],"msg":item["msg"]} for item in error.errors()]},status_code=422)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    with engine().connect() as conn:
        query(conn,"SELECT 1")
    return {"status":"ok"}
