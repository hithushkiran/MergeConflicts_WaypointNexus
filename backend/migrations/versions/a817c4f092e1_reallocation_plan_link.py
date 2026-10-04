"""Link reallocation candidates to the published plan and shortfall."""

from alembic import op
import sqlalchemy as sa


revision = "a817c4f092e1"
down_revision = "df521a8c03b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plan_versions") as batch:
        batch.add_column(sa.Column("revises_plan_version_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_plan_versions_revises_plan", "plan_versions", ["revises_plan_version_id"], ["id"])
    with op.batch_alter_table("shortfalls") as batch:
        batch.add_column(sa.Column("resolution_plan_version_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_shortfalls_resolution_plan", "plan_versions", ["resolution_plan_version_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("shortfalls") as batch:
        batch.drop_constraint("fk_shortfalls_resolution_plan", type_="foreignkey")
        batch.drop_column("resolution_plan_version_id")
    with op.batch_alter_table("plan_versions") as batch:
        batch.drop_constraint("fk_plan_versions_revises_plan", type_="foreignkey")
        batch.drop_column("revises_plan_version_id")
