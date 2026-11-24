# Architecture decisions

- PostgreSQL owns constraints and analytical queries. SQLAlchemy Core provides connection pooling, typed bound parameters and transaction boundaries. Alembic owns schema history.
- Accepted units and quarantine are separate stock states. The movement ledger explains changes while the balance row supports cheap locked validation.
- An inspection is an immutable set of readings against inclusive tolerances. Batch and part identity are validated together.
- Demo fixtures are synthetic and use a fixed random seed plus a configurable UTC anchor date.

- Sorter imports deduplicate by machine, UTC run anchor and exact file hash. Failed event writes roll back to a savepoint before a failure record is committed.
- Dashboard windows use UTC dates and calendar minutes since commissioning. PostgreSQL multiranges merge overlapping stops before a duration is summed.
