"""Allow trip numbers to repeat for different vehicles in a plan."""

from alembic import op


revision = "c27d1e8a4b90"
down_revision = "a114c9f02e31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trips") as batch:
        batch.drop_constraint("trips_plan_version_id_trip_number_key", type_="unique")
        batch.create_unique_constraint(
            "uq_trips_plan_version_vehicle_trip",
            ["plan_version_id", "vehicle_id", "trip_number"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trips") as batch:
        batch.drop_constraint("uq_trips_plan_version_vehicle_trip", type_="unique")
        batch.create_unique_constraint(
            "trips_plan_version_id_trip_number_key",
            ["plan_version_id", "trip_number"],
        )
