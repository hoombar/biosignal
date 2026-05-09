"""add supplement groups

Revision ID: b1c2d3e4f5a6
Revises: a1d2e3f4b5c6
Create Date: 2026-05-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1d2e3f4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("habits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default=sa.text("'manual'"),
            )
        )

    op.create_table(
        "supplement_plan_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slot", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot", "version", name="uix_supplement_slot_version"),
    )
    op.create_index(
        "ix_supplement_plan_versions_slot",
        "supplement_plan_versions",
        ["slot"],
    )

    op.create_table(
        "supplement_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_version_id"], ["supplement_plan_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "slot", name="uix_supplement_log_date_slot"),
    )
    op.create_index("ix_supplement_logs_date", "supplement_logs", ["date"])
    op.create_index("ix_supplement_logs_slot", "supplement_logs", ["slot"])
    op.create_index(
        "ix_supplement_logs_plan_version_id",
        "supplement_logs",
        ["plan_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_supplement_logs_plan_version_id", table_name="supplement_logs")
    op.drop_index("ix_supplement_logs_slot", table_name="supplement_logs")
    op.drop_index("ix_supplement_logs_date", table_name="supplement_logs")
    op.drop_table("supplement_logs")

    op.drop_index(
        "ix_supplement_plan_versions_slot",
        table_name="supplement_plan_versions",
    )
    op.drop_table("supplement_plan_versions")

    with op.batch_alter_table("habits") as batch_op:
        batch_op.drop_column("source")
