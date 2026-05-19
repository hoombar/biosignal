"""add context events

Revision ID: c7a9d1e2f3b4
Revises: b1c2d3e4f5a6
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7a9d1e2f3b4"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "context_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("intensity", sa.String(), nullable=True),
        sa.Column(
            "exclude_from_baseline",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_events_start_date", "context_events", ["start_date"])
    op.create_index("ix_context_events_end_date", "context_events", ["end_date"])
    op.create_index("ix_context_events_category", "context_events", ["category"])


def downgrade() -> None:
    op.drop_index("ix_context_events_category", table_name="context_events")
    op.drop_index("ix_context_events_end_date", table_name="context_events")
    op.drop_index("ix_context_events_start_date", table_name="context_events")
    op.drop_table("context_events")
