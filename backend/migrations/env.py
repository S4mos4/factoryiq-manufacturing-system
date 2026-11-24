import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


def migrate():
    url = os.environ["DATABASE_URL"]
    if context.is_offline_mode():
        context.configure(url=url, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    with create_engine(url, poolclass=NullPool).connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


migrate()
