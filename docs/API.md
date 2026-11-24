# API reference

The built app exposes Swagger UI at `/docs`, ReDoc at `/redoc`, and the OpenAPI schema at `/openapi.json` when documentation is enabled.

| Paths under `/api` | Methods and purpose |
| --- | --- |
| `/session`, `/lookups` | GET access mode and resource choices |
| `/dashboard` | GET KPI snapshot, previous period, trend, top downtime and fault frequency |
| `/equipment`, `/equipment/{id}` | GET list and detail, POST register, PUT edit |
| `/inventory`, `/inventory/{part}` | GET balances, reservations and movement history |
| `/inventory/{part}/{receive, reserve, reject}` | POST stock change or idempotent reservation |
| `/inventory/{part}/reservations/{id}/{release, consume}` | POST atomic state transition |
| `/inspections`, `/inspections/{id}` | GET history and detail, POST inspection with readings |
| `/nonconformances`, `/nonconformances/{id}` | GET report and action history, POST open, PATCH transition |
| `/nonconformances/{id}/actions`, `/nonconformances/{id}/actions/{action}` | POST assign, PATCH complete |
| `/maintenance`, `/maintenance/{id}`, `/calibrations` | GET history, POST work or calibration, PATCH work status |
| `/sorter/imports`, `/sorter/events` | GET attempts and events, POST a raw CSV trace |
| `/analytics/{analysis}` | GET a named query result |
| `/reports/{kind}.csv` | GET equipment, inventory, inspections, downtime or maintenance CSV |

Operator writes use `Authorization: Bearer <local token>`. The demo-read flag allows anonymous reads from a synthetic instance. Read-only mode blocks mutations even with a valid token. Typical error codes include 401 for unauthorized access, 403 for read-only, 404 for unknown records, 409 for conflicting constraints or states, and 422 for invalid inputs.

## Sorter upload

POST `/api/sorter/imports?equipment_id=5&anchor=2026-11-24T14%3A00%3A00Z&filename=synthetic-trace.csv` with an operator token, content type `text/csv`, and the file as the request body. The anchor is the UTC instant corresponding to simulation offset zero. Limits are 512 KiB and 10,000 source rows. The importer queues each lane independently with capacity 16. It checks for a wait of at least 1,000 ms before applying each event and logs one jam per package. An observed later exit closes the simulated stop. An unresolved jam is counted as a fault and has no measured repair time.

The existing [Warehouse Sorter and Fault Logger](https://github.com/S4mos4/warehouse-sorter) example trace was accepted in a real PostgreSQL smoke test. Valid retries deduplicate by equipment, UTC anchor and exact content hash. A different anchor represents a separate run, and differently encoded files have different hashes.

## Metric semantics

- Dashboard date filters are inclusive UTC days. API SQL uses a half-open window. Previous period is the same length immediately before it.
- Machine availability is 100 × (eligible calendar minutes − merged downtime) / eligible calendar minutes. Eligible minutes begin at commissioning. Downtime is clipped to the window and overlapping intervals are counted once per machine.
- Defect and pass rates use recorded inspections as the denominator. A zero denominator yields null. Rolling trend is the ratio of seven-day sums.
- Operational status, stock availability, open reports and overdue maintenance are current snapshots. Stock metrics are plant-wide.
- Failure interval is average stop start-to-start time. Average repair duration uses merged recorded stop episodes.
- `fault_frequency`, `defect_trend`, and `downtime_by_machine` accept period and machine filters. Supplier defects, batch rejects and reliability use all recorded history. Low stock and maintenance use the latest snapshot.
