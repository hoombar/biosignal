"""add environmental metrics table

Revision ID: a1d2e3f4b5c6
Revises: f3a7c9d0e1b2
Create Date: 2026-05-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1d2e3f4b5c6"
down_revision: Union[str, None] = "f3a7c9d0e1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "environmental_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("location_key", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "date",
            "source",
            "metric_key",
            "location_key",
            name="uix_environmental_date_source_metric_location",
        ),
    )
    op.create_index(op.f("ix_environmental_metrics_date"), "environmental_metrics", ["date"], unique=False)
    op.create_index(op.f("ix_environmental_metrics_source"), "environmental_metrics", ["source"], unique=False)
    op.create_index(op.f("ix_environmental_metrics_metric_key"), "environmental_metrics", ["metric_key"], unique=False)
    op.create_index(op.f("ix_environmental_metrics_location_key"), "environmental_metrics", ["location_key"], unique=False)
    op.create_index(
        "ix_environmental_metrics_date_metric",
        "environmental_metrics",
        ["date", "metric_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_environmental_metrics_date_metric", table_name="environmental_metrics")
    op.drop_index(op.f("ix_environmental_metrics_location_key"), table_name="environmental_metrics")
    op.drop_index(op.f("ix_environmental_metrics_metric_key"), table_name="environmental_metrics")
    op.drop_index(op.f("ix_environmental_metrics_source"), table_name="environmental_metrics")
    op.drop_index(op.f("ix_environmental_metrics_date"), table_name="environmental_metrics")
    op.drop_table("environmental_metrics")
