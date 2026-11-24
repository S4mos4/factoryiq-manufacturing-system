import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from factoryiq.db import engine
from factoryiq.main import app
from factoryiq.seed import seed

TEST_TOKEN = "test-operator-token-only-for-ci"


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture(scope="session")
def database():
    url = os.getenv("FACTORYIQ_TEST_DATABASE_URL")
    if not url:
        pytest.exit("Set FACTORYIQ_TEST_DATABASE_URL to a disposable PostgreSQL database.",returncode=2)
    schema = "test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = make_url(url).update_query_dict({"options":f"-csearch_path={schema} -ctimezone=UTC"})
    with pytest.MonkeyPatch.context() as env:
        env.setenv("DATABASE_URL",scoped.render_as_string(hide_password=False))
        engine.cache_clear()
        try:
            command.upgrade(Config(str(Path(__file__).resolve().parents[1]/"alembic.ini")),"head")
            assert seed(date(2026,9,24))
            assert not seed(date(2026,9,24))
            yield engine()
        finally:
            engine().dispose()
            engine.cache_clear()
            with admin.begin() as conn:
                conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            admin.dispose()


@pytest.fixture
def client(database,monkeypatch):
    monkeypatch.setenv("FACTORYIQ_DEMO_READS","true")
    monkeypatch.setenv("FACTORYIQ_READ_ONLY","false")
    monkeypatch.setenv("FACTORYIQ_OPERATOR_TOKEN",TEST_TOKEN)
    with TestClient(app) as client:
        yield client
