CREATE TABLE equipment_types (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name text NOT NULL UNIQUE
);
CREATE TABLE facility_locations (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name text NOT NULL UNIQUE
);
CREATE TABLE suppliers (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, code text NOT NULL UNIQUE, name text NOT NULL
);
CREATE TABLE users (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, username text NOT NULL UNIQUE,
 role text NOT NULL CHECK (role IN ('operator','viewer'))
);
CREATE TABLE equipment (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, code text NOT NULL UNIQUE,
 name text NOT NULL, type_id integer NOT NULL REFERENCES equipment_types,
 location_id integer NOT NULL REFERENCES facility_locations,
 status text NOT NULL CHECK (status IN ('operational','maintenance','offline')),
 commissioned_on date NOT NULL
);
CREATE INDEX equipment_location_idx ON equipment(location_id);
CREATE TABLE parts (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, sku text NOT NULL UNIQUE, name text NOT NULL,
 supplier_id integer NOT NULL REFERENCES suppliers, reorder_point integer NOT NULL CHECK (reorder_point >= 0)
);
CREATE TABLE production_batches (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, code text NOT NULL UNIQUE,
 part_id integer NOT NULL REFERENCES parts, equipment_id integer NOT NULL REFERENCES equipment,
 started_at timestamptz NOT NULL, UNIQUE(id, part_id)
);
CREATE TABLE inventory_balances (
 part_id integer PRIMARY KEY REFERENCES parts, usable integer NOT NULL DEFAULT 0,
 reserved integer NOT NULL DEFAULT 0, rejected integer NOT NULL DEFAULT 0,
 CHECK (usable >= reserved AND reserved >= 0 AND rejected >= 0)
);
CREATE TABLE inventory_reservations (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, part_id integer NOT NULL REFERENCES parts,
 batch_id integer NOT NULL, quantity integer NOT NULL CHECK (quantity > 0),
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','released','consumed')),
 request_id uuid NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now(),
 closed_at timestamptz,
 FOREIGN KEY (batch_id, part_id) REFERENCES production_batches(id, part_id),
 UNIQUE(id, part_id),
 CHECK ((status = 'active') = (closed_at IS NULL)),
 CHECK (closed_at >= created_at)
);
CREATE INDEX active_reservations_idx ON inventory_reservations(part_id) WHERE status = 'active';
CREATE TABLE inventory_movements (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, part_id integer NOT NULL REFERENCES parts,
 reservation_id integer, kind text NOT NULL CHECK (kind IN ('receive','reserve','release','consume','reject')),
 quantity integer NOT NULL CHECK (quantity > 0), notes text NOT NULL DEFAULT '',
 occurred_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (reservation_id, part_id) REFERENCES inventory_reservations(id, part_id),
 CHECK ((kind IN ('reserve','release','consume')) = (reservation_id IS NOT NULL))
);
CREATE INDEX movements_part_time_idx ON inventory_movements(part_id, occurred_at DESC);
CREATE TABLE quality_inspections (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, batch_id integer NOT NULL,
 part_id integer NOT NULL REFERENCES parts, inspected_at timestamptz NOT NULL, passed boolean NOT NULL,
 rejection_reason text,
 FOREIGN KEY (batch_id, part_id) REFERENCES production_batches(id, part_id),
 CHECK ((passed AND rejection_reason IS NULL) OR (NOT passed AND length(trim(coalesce(rejection_reason,''))) > 0))
);
CREATE INDEX inspections_time_idx ON quality_inspections(inspected_at);
CREATE INDEX inspections_batch_idx ON quality_inspections(batch_id);
CREATE TABLE inspection_measurements (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 inspection_id integer NOT NULL REFERENCES quality_inspections ON DELETE CASCADE,
 characteristic text NOT NULL, unit text NOT NULL, value numeric(14,4) NOT NULL,
 lower_limit numeric(14,4) NOT NULL, upper_limit numeric(14,4) NOT NULL,
 passed boolean GENERATED ALWAYS AS (value BETWEEN lower_limit AND upper_limit) STORED,
 UNIQUE(inspection_id, characteristic), CHECK (lower_limit <= upper_limit),
 CHECK (value <> 'NaN' AND lower_limit <> 'NaN' AND upper_limit <> 'NaN')
);
CREATE TABLE non_conformance_reports (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, equipment_id integer NOT NULL REFERENCES equipment,
 inspection_id integer REFERENCES quality_inspections, title text NOT NULL, description text NOT NULL,
 severity text NOT NULL CHECK (severity IN ('minor','major','critical')),
 status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','investigating','closed')),
 opened_at timestamptz NOT NULL DEFAULT now(), closed_at timestamptz,
 CHECK ((status = 'closed') = (closed_at IS NOT NULL)), CHECK (closed_at >= opened_at)
);
CREATE TABLE corrective_actions (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 report_id integer NOT NULL REFERENCES non_conformance_reports, title text NOT NULL,
 owner_id integer NOT NULL REFERENCES users, due_on date NOT NULL,
 status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done')),
 completed_at timestamptz, CHECK ((status = 'done') = (completed_at IS NOT NULL))
);
CREATE INDEX corrective_report_idx ON corrective_actions(report_id);
CREATE TABLE maintenance_work_orders (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, equipment_id integer NOT NULL REFERENCES equipment,
 title text NOT NULL, kind text NOT NULL CHECK (kind IN ('preventive','corrective')),
 scheduled_on date NOT NULL, due_on date NOT NULL CHECK (due_on >= scheduled_on),
 status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','in_progress','complete')),
 completed_at timestamptz, notes text NOT NULL DEFAULT '',
 CHECK ((status = 'complete') = (completed_at IS NOT NULL))
);
CREATE INDEX maintenance_equipment_idx ON maintenance_work_orders(equipment_id,due_on);
CREATE INDEX maintenance_due_idx ON maintenance_work_orders(due_on) WHERE status <> 'complete';
CREATE TABLE calibration_records (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, equipment_id integer NOT NULL REFERENCES equipment,
 calibrated_on date NOT NULL, next_due_on date NOT NULL CHECK (next_due_on > calibrated_on),
 result text NOT NULL CHECK (result IN ('pass','fail')), reference text NOT NULL,
 UNIQUE(equipment_id, calibrated_on, reference)
);
CREATE TABLE downtime_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, equipment_id integer NOT NULL REFERENCES equipment,
 started_at timestamptz NOT NULL, ended_at timestamptz NOT NULL CHECK (ended_at > started_at),
 reason text NOT NULL, source_key text UNIQUE
);
CREATE INDEX downtime_equipment_time_idx ON downtime_events(equipment_id,started_at);
CREATE TABLE import_history (
 id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, equipment_id integer NOT NULL REFERENCES equipment,
 user_id integer NOT NULL REFERENCES users, filename text NOT NULL, checksum text NOT NULL,
 run_key text, started_at timestamptz NOT NULL DEFAULT now(), anchor_at timestamptz NOT NULL,
 outcome text NOT NULL CHECK (outcome IN ('imported','duplicate','failed')),
 row_count integer NOT NULL DEFAULT 0 CHECK (row_count >= 0), error text
);
CREATE UNIQUE INDEX import_run_unique ON import_history(equipment_id, run_key) WHERE outcome = 'imported';
CREATE TABLE sorter_fault_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, equipment_id integer NOT NULL REFERENCES equipment,
 import_id integer REFERENCES import_history, event_key text NOT NULL,
 occurred_at timestamptz NOT NULL, kind text NOT NULL CHECK (kind IN ('entry','exit','tick','jam','fault')),
 lane text CHECK (lane IN ('A','B')), fault_code text,
 UNIQUE(equipment_id,event_key), CHECK ((kind IN ('jam','fault')) = (fault_code IS NOT NULL))
);
CREATE INDEX sorter_time_idx ON sorter_fault_events(occurred_at);
CREATE INDEX sorter_fault_equipment_time_idx ON sorter_fault_events(equipment_id,occurred_at)
 WHERE fault_code IS NOT NULL;
CREATE TABLE audit_logs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id integer NOT NULL REFERENCES users,
 action text NOT NULL, entity text NOT NULL, entity_id bigint NOT NULL,
 details jsonb NOT NULL DEFAULT '{}', occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_entity_idx ON audit_logs(entity,entity_id,occurred_at DESC);
CREATE TABLE demo_seed (id integer PRIMARY KEY CHECK (id = 1), anchor_date date NOT NULL);
CREATE VIEW inventory_availability AS
 SELECT p.id, p.sku, p.name, s.name AS supplier, p.reorder_point,
 coalesce(b.usable,0) AS usable, coalesce(b.reserved,0) AS reserved,
 coalesce(b.rejected,0) AS rejected, coalesce(b.usable-b.reserved,0) AS available,
 coalesce(b.usable-b.reserved,0) < p.reorder_point AS low_stock
 FROM parts p JOIN suppliers s ON s.id=p.supplier_id LEFT JOIN inventory_balances b ON b.part_id=p.id;
CREATE VIEW maintenance_queue AS
 SELECT w.*, e.code AS equipment, w.status <> 'complete' AND w.due_on < CURRENT_DATE AS overdue
 FROM maintenance_work_orders w JOIN equipment e ON e.id=w.equipment_id;
