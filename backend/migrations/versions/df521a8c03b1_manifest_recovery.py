"""Persist manifest versions, loading checks, and shortfall ownership."""

from alembic import op
import sqlalchemy as sa


revision = "df521a8c03b1"
down_revision = "c27d1e8a4b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manifest_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CURRENT"),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_by_id", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["acknowledged_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "version_number"),
    )
    op.create_index("ix_manifest_versions_trip_id", "manifest_versions", ["trip_id"])
    with op.batch_alter_table("manifest_checks") as batch:
        batch.add_column(sa.Column("manifest_version_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("load_sequence", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("checked_by_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_manifest_checks_manifest_version", "manifest_versions", ["manifest_version_id"], ["id"])
        batch.create_foreign_key("fk_manifest_checks_checked_by", "users", ["checked_by_id"], ["id"])
        batch.create_index("ix_manifest_checks_manifest_version_id", ["manifest_version_id"])
        batch.create_index("ix_manifest_checks_trip_id", ["trip_id"])
    with op.batch_alter_table("shortfalls") as batch:
        batch.add_column(sa.Column("manifest_check_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("created_by_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        batch.create_foreign_key("fk_shortfalls_manifest_check", "manifest_checks", ["manifest_check_id"], ["id"])
        batch.create_foreign_key("fk_shortfalls_created_by", "users", ["created_by_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("shortfalls") as batch:
        batch.drop_constraint("fk_shortfalls_created_by", type_="foreignkey")
        batch.drop_constraint("fk_shortfalls_manifest_check", type_="foreignkey")
        batch.drop_column("created_at")
        batch.drop_column("created_by_id")
        batch.drop_column("manifest_check_id")
    with op.batch_alter_table("manifest_checks") as batch:
        batch.drop_index("ix_manifest_checks_trip_id")
        batch.drop_index("ix_manifest_checks_manifest_version_id")
        batch.drop_constraint("fk_manifest_checks_checked_by", type_="foreignkey")
        batch.drop_constraint("fk_manifest_checks_manifest_version", type_="foreignkey")
        batch.drop_column("checked_at")
        batch.drop_column("checked_by_id")
        batch.drop_column("notes")
        batch.drop_column("load_sequence")
        batch.drop_column("manifest_version_id")
    op.drop_index("ix_manifest_versions_trip_id", table_name="manifest_versions")
    op.drop_table("manifest_versions")
