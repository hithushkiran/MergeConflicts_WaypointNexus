"""Preserve receiving quantities and case resolution; legacy facts remain unknown."""
from alembic import op
import sqlalchemy as sa

revision = "c38e72f104a6"
down_revision = "b24d32f1e5d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.add_column(sa.Column("receiver_name", sa.String(120), nullable=True))
        for name in ("ordered_quantity", "dispatched_quantity", "received_quantity"):
            batch.add_column(sa.Column(name, sa.Integer(), nullable=True))
        batch.add_column(sa.Column("manifest_version_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_receipts_manifest", "manifest_versions", ["manifest_version_id"], ["id"])
        batch.create_check_constraint("ck_receipts_received_nonnegative", "received_quantity >= 0")
        batch.create_check_constraint("ck_receipts_received_dispatched", "received_quantity <= dispatched_quantity")
    with op.batch_alter_table("delivery_issues") as batch:
        batch.add_column(sa.Column("affected_quantity", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("resolution_notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("resolved_by_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_delivery_issues_resolver", "users", ["resolved_by_id"], ["id"])
        batch.create_check_constraint("ck_delivery_issues_positive_quantity", "affected_quantity > 0")


def downgrade() -> None:
    with op.batch_alter_table("delivery_issues") as batch:
        batch.drop_constraint("ck_delivery_issues_positive_quantity", type_="check")
        batch.drop_constraint("fk_delivery_issues_resolver", type_="foreignkey")
        for name in ("resolved_at", "resolved_by_id", "resolution_notes", "affected_quantity"):
            batch.drop_column(name)
    with op.batch_alter_table("receipts") as batch:
        batch.drop_constraint("ck_receipts_received_dispatched", type_="check")
        batch.drop_constraint("ck_receipts_received_nonnegative", type_="check")
        batch.drop_constraint("fk_receipts_manifest", type_="foreignkey")
        for name in ("manifest_version_id", "received_quantity", "dispatched_quantity", "ordered_quantity", "receiver_name"):
            batch.drop_column(name)
