import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, text


@lru_cache
def engine():
    return create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True, hide_parameters=True)


def query(conn, sql, **params):
    return conn.execute(text(sql), params)


def rows(conn, sql, **params):
    return [dict(row) for row in query(conn, sql, **params).mappings()]


def one(conn, sql, **params):
    return query(conn, sql, **params).mappings().one_or_none()


@lru_cache
def sql_file(name):
    return (Path(__file__).parent / "sql" / f"{name}.sql").read_text()
