# Database design

PostgreSQL 17 · [Foundation DDL](../backend/migrations/versions/001_foundation.sql) · [Alembic revisions](../backend/migrations/versions/)

```mermaid
erDiagram
    equipment_types ||--o{ equipment : classifies
    facility_locations ||--o{ equipment : houses
    suppliers ||--o{ parts : supplies
    equipment ||--o{ production_batches : makes
    parts ||--o{ production_batches : part
    parts ||--o| inventory_balances : tracks
    parts ||--o{ inventory_movements : records
    parts ||--o{ inventory_reservations : allocates
    production_batches ||--o{ inventory_reservations : requests
    inventory_reservations o|--o{ inventory_movements : explains
    production_batches ||--o{ quality_inspections : inspected
    parts ||--o{ quality_inspections : measured
    quality_inspections ||--|{ inspection_measurements : contains
    quality_inspections o|--o{ non_conformance_reports : originates
    equipment ||--o{ non_conformance_reports : affects
    non_conformance_reports ||--o{ corrective_actions : requires
    users ||--o{ corrective_actions : owns
    equipment ||--o{ maintenance_work_orders : serviced
    equipment ||--o{ calibration_records : calibrated
    equipment ||--o{ downtime_events : interrupted
    equipment ||--o{ import_history : machine
    equipment ||--o{ sorter_fault_events : emits
    import_history o|--o{ sorter_fault_events : groups
    users ||--o{ import_history : user
    users ||--o{ audit_logs : acts
```

- Catalog tables normalize facilities, machine types, users, suppliers and parts.
- Composite foreign keys tie reservation and inspection part IDs to the selected batch’s part. Measurement rows have one characteristic per inspection and a database-generated inclusive pass flag.
- `inventory_balances` stores three quantities. `usable - reserved` is available to promise. Qualifying writes lock the part, update the balance, append a ledger movement and create an audit row in one transaction.
- `inventory_availability` exposes balances, supplier and reorder alerts. `maintenance_queue` derives overdue status from due date and completion state.
- Unique reservation request keys and partial unique movement indexes prevent duplicate reserve or close entries. An active reservation can close once by consumption or release.
- Sorter events use a unique machine/event key. Imports have a unique successful run per machine, file checksum and anchor. Failed and duplicate attempts appear in history.
- Audit entity references are typed by the `entity` label and stored with an ID so one audit stream can represent different relations. `demo_seed` is a standalone initialization marker.
