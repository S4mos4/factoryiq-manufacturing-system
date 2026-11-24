"""Initialize normalized FactoryIQ schema."""

from pathlib import Path

from alembic import op

revision = "001"
down_revision = None

TABLES = (
    "equipment_types facility_locations suppliers users equipment parts production_batches "
    "inventory_balances inventory_reservations inventory_movements quality_inspections "
    "inspection_measurements non_conformance_reports corrective_actions maintenance_work_orders "
    "calibration_records downtime_events import_history sorter_fault_events audit_logs demo_seed"
).split()


def upgrade():
    path = Path(__file__).with_suffix(".sql")
    for statement in path.read_text().split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    op.execute("DROP VIEW maintenance_queue, inventory_availability")
    for table in reversed(TABLES):
        op.drop_table(table)
