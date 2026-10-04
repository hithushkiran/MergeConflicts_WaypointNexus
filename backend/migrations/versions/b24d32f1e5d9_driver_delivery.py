"""Add driver assignments, stop progress, and delivery actor records."""

from alembic import op
import sqlalchemy as sa


revision = "b24d32f1e5d9"
down_revision = "a817c4f092e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trips") as batch:
        batch.add_column(sa.Column("assigned_driver_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_trips_assigned_driver", "users", ["assigned_driver_id"], ["id"])
        batch.create_index("ix_trips_assigned_driver_id", ["assigned_driver_id"])
    with op.batch_alter_table("trip_stops") as batch:
        batch.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"))
        batch.add_column(sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("delivery_events") as batch:
        batch.add_column(sa.Column("actor_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_delivery_events_actor", "users", ["actor_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("delivery_events") as batch:
        batch.drop_constraint("fk_delivery_events_actor", type_="foreignkey")
        batch.drop_column("actor_id")
    with op.batch_alter_table("trip_stops") as batch:
        batch.drop_column("completed_at")
        batch.drop_column("arrived_at")
        batch.drop_column("status")
    with op.batch_alter_table("trips") as batch:
        batch.drop_index("ix_trips_assigned_driver_id")
        batch.drop_constraint("fk_trips_assigned_driver", type_="foreignkey")
        batch.drop_column("completed_at")
        batch.drop_column("started_at")
        batch.drop_column("assigned_driver_id")
