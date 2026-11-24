# FactoryIQ development

- Keep PostgreSQL constraints and versioned Alembic migrations in sync. Treat applied migrations as immutable.
- Bind SQL parameters. Keep reusable analytical SQL in backend/factoryiq/sql.
- Serialize inventory writes by locking the part before reading or changing its balance.
- Run integration tests against a dedicated PostgreSQL database. Preserve atomicity and audit history.
- Keep public demos synthetic and read-only. Never commit credentials or upstream academic files.
