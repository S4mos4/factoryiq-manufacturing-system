"""Add equipment telemetry, alarms and bounded simulator controls."""

from pathlib import Path

from alembic import op

revision = "004"
down_revision = "003"


def upgrade():
    for statement in Path(__file__).with_suffix(".sql").read_text().split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for table in ("iot_simulation_controls","iot_alarm_history","iot_alarms","iot_thresholds",
                  "iot_readings","iot_connections","iot_devices"):
        op.drop_table(table)
