# FactoryIQ interview guide

Use the project as a technical discussion of a fictional manufacturing system. Reproduce the behaviour locally, inspect the code, and keep a record of changes and tests you personally complete.

## System walkthrough

1. In Overview, change the equipment filter and inspect the dashboard network request. React fetches a snapshot and time series from FastAPI. The API returns numbers from SQL executed against PostgreSQL.
2. Open inventory, receive a unit, reserve it for a batch, then consume it. Watch available, reserved, usable and the ledger change.
3. Enter an inspection with a reading on its upper limit. Add a second reading above its limit, supply a rejection reason, and inspect the saved measurements.
4. Import the synthetic sorter CSV twice with the same machine and timestamp. Explain why history records both attempts while telemetry is written once.
5. Run Pytest and inspect the measured index plans.

## Questions to practise

| Question | Explanation to work through |
| --- | --- |
| What problem does FactoryIQ solve? | Plant staff use equipment, parts, measurements, maintenance jobs and fault data together. A shared relational schema supports transactional workflows and trend analysis. |
| Why normalize the schema? | Supplier, part, machine type, location and batch have distinct identities. The inspection parent captures one decision, while its child rows store an arbitrary number of measurements. A balance table deliberately materializes state for cheap concurrent checks. |
| What do the keys enforce? | A primary key identifies a row. Foreign keys enforce references. The composite batch and part foreign key rejects use of a different part on the same batch. |
| Why does the last-unit race occur? | Two callers can both see one available unit before either reserves it. Each write locks the part, then reads stock while holding that lock. The other caller waits and subsequently sees zero available. |
| Why use both a transaction and a constraint? | The transaction keeps the reservation, balance, movement and audit event together. The check prevents an invalid balance even if an isolated SQL update bypasses the API. |
| How are duplicates handled? | Reservation retries reuse a UUID. Sorter replay uses the machine, normalized run anchor and file hash. Release and consume are terminal states, with a unique terminal ledger entry. |
| What happens when the import fails late? | An event insert and a downtime insert live inside a savepoint. A failed constraint rolls them back, then the outer transaction records the failed attempt. |
| How does a time window handle overlapping stops? | Clip each stop to the UTC window and merge ranges by machine before summing. Availability uses elapsed calendar capacity since commissioning. Shift-level OEE would require schedule and speed data. |
| What does the defect trend window calculate? | It sums both defects and inspected units across the previous six daily rows and the current day. Dividing those sums weights days by sample size. |
| Why did the partial index help? | Machine and time keys restrict the scan; the predicate limits it to rows that contain a fault code. Compare candidate rows, buffer hits and median execution, then explain when writes and size make an index less attractive. |
| Does the failure gap equal MTBF? | It estimates calendar time between recorded stop starts. Operating-hours MTBF needs machine run-time exposure and a defined failure classification. |
| How does validation work? | FastAPI validates request shape and bounds. The service checks cross-row rules and uses Decimal before saving. PostgreSQL enforces identities, types, constraints, and the generated per-measurement pass flag. |
| Why Docker Compose? | It describes the database, application, health dependencies and volume in one file. The Docker build compiles React, then the Python runtime serves the UI and API together. |
| How did you test it? | Pytest runs against real PostgreSQL schemas. Two concurrent requests exercise locking. Playwright drives the built UI against a seeded application. The benchmark runs the same SQL under two index configurations. |
| How does access work? | Anonymous access is opt-in for the synthetic demo. Mutations require a token and are blocked independently by read-only mode. A shared token identifies a demo actor, so individual accountability would need separate identities. |
| What would you change for an actual plant? | Model lots and traceability, shift calendars, identity, ingestion pagination, monitoring, backups and protected audit retention. Evaluate requirements before adding each. |

## Code to review and modify

- [Reservation and inventory ledger](backend/factoryiq/operations.py). Trace a receive, reserve and consume from request through the lock to the four writes. Add a test for a concurrent consume/release race.
- [Database DDL](backend/migrations/versions/001_foundation.sql). Draw the reservation and inspection foreign keys by hand. Try an invalid batch/part pair in a disposable database.
- [Sorter FIFO and savepoint](backend/factoryiq/sorter.py). Explain offsets, lane queues and jam detection. Add a test for an exit at exactly 1,000 ms.
- [Dashboard SQL](backend/factoryiq/sql/dashboard.sql) and [rolling window](backend/factoryiq/sql/defect_trend.sql). Predict results for a one-machine day with overlapping downtime and a day without inspections.
- [Reliability SQL](backend/factoryiq/sql/reliability.sql) and [benchmark runner](backend/factoryiq/benchmark.py). Run the benchmark with another time window and compare the plans.
- [Backend tests](backend/tests/test_factoryiq.py) and [browser tests](frontend/tests/operations.spec.ts). Reproduce the checks and add one scenario you can demonstrate.
- [Client auth](frontend/src/main.tsx) and [server authorization](backend/factoryiq/security.py). Trace the token and confirm the read-only server rejects an authenticated write.

## Résumé wording

Use these as starting points after personal review. Keep the AI-assisted attribution and replace any review or verification verbs with work you actually completed.

- Scoped FactoryIQ, an AI-assisted manufacturing quality system integrating equipment, inventory, inspections and maintenance in a PostgreSQL-backed React and FastAPI application.
- Reviewed and reproduced a PostgreSQL row-locking workflow that prevented concurrent callers from reserving the same last unit and blocked quarantined stock from production.
- Verified a VHDL sorter trace adapter against a warehouse-sorter simulation and explained duplicate detection, FIFO jam recovery and atomic rollback.
- Reproduced an EXPLAIN ANALYZE comparison on 205,000 synthetic events and explained how a partial index reduced a machine-filtered fault query’s median execution from 1.260 ms to 0.045 ms.

The last three bullets describe work to do personally before claiming it.
