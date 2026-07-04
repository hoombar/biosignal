"""add gym activity library

Revision ID: 5c1d2e3f4a6b
Revises: 4a6b8c2d9e10
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5c1d2e3f4a6b"
down_revision: Union[str, None] = "4a6b8c2d9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gym_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("target_sets", sa.Integer(), nullable=True),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("target_weight_unit", sa.String(), nullable=True),
        sa.Column("target_duration_minutes", sa.Float(), nullable=True),
        sa.Column("target_intensity", sa.String(), nullable=True),
        sa.Column("target_speed", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gym_activities_name"), "gym_activities", ["name"], unique=True)
    with op.batch_alter_table("gym_template_activities") as batch_op:
        batch_op.add_column(sa.Column("activity_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_gym_template_activities_activity_id"), ["activity_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_gym_template_activities_activity_id_gym_activities",
            "gym_activities",
            ["activity_id"],
            ["id"],
        )
    with op.batch_alter_table("gym_session_activity_logs") as batch_op:
        batch_op.add_column(sa.Column("activity_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_gym_session_activity_logs_activity_id"), ["activity_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_gym_session_activity_logs_activity_id_gym_activities",
            "gym_activities",
            ["activity_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("gym_session_activity_logs") as batch_op:
        batch_op.drop_constraint("fk_gym_session_activity_logs_activity_id_gym_activities", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_gym_session_activity_logs_activity_id"))
        batch_op.drop_column("activity_id")
    with op.batch_alter_table("gym_template_activities") as batch_op:
        batch_op.drop_constraint("fk_gym_template_activities_activity_id_gym_activities", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_gym_template_activities_activity_id"))
        batch_op.drop_column("activity_id")
    op.drop_index(op.f("ix_gym_activities_name"), table_name="gym_activities")
    op.drop_table("gym_activities")
