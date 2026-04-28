"""habits: add is_negative, target_value, period

Revision ID: e6f1c0a82bd5
Revises: d8a13b6f5042
Create Date: 2026-04-28 16:00:00.000000

Adds the three columns that turn the binary/counter habits table into a
generic habit tracker:

- ``is_negative`` (Boolean, default False) — flips hit-state evaluation
  from "≥ target" to "≤ target".
- ``target_value`` (Integer, nullable) — None means "any activity counts"
  for positive habits and "avoid completely" for negative habits.
- ``period`` (String, default 'day') — granularity of hit-state evaluation
  (day / week / month).

Server-side defaults are required because the new NOT NULL columns are
added to an existing table; SQLite needs a default to backfill old rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f1c0a82bd5"
down_revision: Union[str, Sequence[str], None] = "d8a13b6f5042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("habits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_negative",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("target_value", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "period",
                sa.String(),
                nullable=False,
                server_default=sa.text("'day'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("habits") as batch_op:
        batch_op.drop_column("period")
        batch_op.drop_column("target_value")
        batch_op.drop_column("is_negative")
