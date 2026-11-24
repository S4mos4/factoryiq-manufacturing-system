"""Enforce one reserve and one terminal movement per reservation."""

from alembic import op

revision = "002"
down_revision = "001"


def upgrade():
    op.execute("""CREATE UNIQUE INDEX reservation_open_movement_unique
                  ON inventory_movements(reservation_id) WHERE kind='reserve'""")
    op.execute("""CREATE UNIQUE INDEX reservation_close_movement_unique
                  ON inventory_movements(reservation_id) WHERE kind IN ('release','consume')""")


def downgrade():
    op.drop_index("reservation_close_movement_unique",table_name="inventory_movements")
    op.drop_index("reservation_open_movement_unique",table_name="inventory_movements")
