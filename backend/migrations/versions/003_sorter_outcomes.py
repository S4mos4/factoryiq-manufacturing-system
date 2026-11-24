"""Report package outcomes and transit time for observed sorter exits."""

from alembic import op

revision = "003"
down_revision = "002"


def upgrade():
    op.execute("""ALTER TABLE sorter_fault_events
        ADD COLUMN processing_outcome text,
        ADD COLUMN processing_ms integer,
        ADD CONSTRAINT sorter_exit_outcome_valid CHECK (
            (processing_outcome IS NULL AND processing_ms IS NULL) OR
            (kind='exit' AND processing_outcome IS NOT NULL AND processing_ms IS NOT NULL
             AND processing_outcome IN ('sorted','jam_recovered','fault_recovered') AND processing_ms >= 0)
        )""")


def downgrade():
    op.drop_constraint("sorter_exit_outcome_valid","sorter_fault_events",type_="check")
    op.drop_column("sorter_fault_events","processing_ms")
    op.drop_column("sorter_fault_events","processing_outcome")
