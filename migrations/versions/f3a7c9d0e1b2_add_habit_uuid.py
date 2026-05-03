"""add stable UUIDs to habits

Revision ID: f3a7c9d0e1b2
Revises: e6f1c0a82bd5
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "f3a7c9d0e1b2"
down_revision: Union[str, None] = "e6f1c0a82bd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("habits", sa.Column("uuid", sa.String(length=36), nullable=True))

    conn = op.get_bind()
    habit_ids = conn.execute(sa.text("SELECT id FROM habits")).scalars().all()
    for habit_id in habit_ids:
        conn.execute(
            sa.text("UPDATE habits SET uuid = :uuid WHERE id = :id"),
            {"uuid": str(uuid4()), "id": habit_id},
        )

    with op.batch_alter_table("habits") as batch_op:
        batch_op.alter_column(
            "uuid",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.create_index("ix_habits_uuid", ["uuid"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("habits") as batch_op:
        batch_op.drop_index("ix_habits_uuid")
        batch_op.drop_column("uuid")
