"""add gym sessions

Revision ID: 7b6a5c4d3e2f
Revises: e2f3a4b5c6d7
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b6a5c4d3e2f"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gym_session_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gym_session_templates_name"), "gym_session_templates", ["name"], unique=True)

    op.create_table(
        "gym_template_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_sets", sa.Integer(), nullable=True),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("target_weight_unit", sa.String(), nullable=True),
        sa.Column("target_duration_minutes", sa.Float(), nullable=True),
        sa.Column("target_intensity", sa.String(), nullable=True),
        sa.Column("target_speed", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["gym_session_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "sort_order", name="uix_gym_template_activity_order"),
    )
    op.create_index(op.f("ix_gym_template_activities_template_id"), "gym_template_activities", ["template_id"], unique=False)

    op.create_table(
        "gym_session_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_name_snapshot", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["gym_session_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uix_gym_session_date"),
    )
    op.create_index(op.f("ix_gym_session_logs_date"), "gym_session_logs", ["date"], unique=False)
    op.create_index(op.f("ix_gym_session_logs_template_id"), "gym_session_logs", ["template_id"], unique=False)

    op.create_table(
        "gym_session_activity_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_log_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("name_snapshot", sa.String(), nullable=False),
        sa.Column("planned_sets", sa.Integer(), nullable=True),
        sa.Column("planned_reps", sa.Integer(), nullable=True),
        sa.Column("planned_weight", sa.Float(), nullable=True),
        sa.Column("planned_weight_unit", sa.String(), nullable=True),
        sa.Column("planned_duration_minutes", sa.Float(), nullable=True),
        sa.Column("planned_intensity", sa.String(), nullable=True),
        sa.Column("planned_speed", sa.Float(), nullable=True),
        sa.Column("planned_notes", sa.Text(), nullable=True),
        sa.Column("actual_sets", sa.Integer(), nullable=True),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
        sa.Column("actual_weight", sa.Float(), nullable=True),
        sa.Column("actual_weight_unit", sa.String(), nullable=True),
        sa.Column("actual_duration_minutes", sa.Float(), nullable=True),
        sa.Column("actual_intensity", sa.String(), nullable=True),
        sa.Column("actual_speed", sa.Float(), nullable=True),
        sa.Column("completed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("rating", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_log_id"], ["gym_session_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_log_id", "sort_order", name="uix_gym_session_activity_order"),
    )
    op.create_index(op.f("ix_gym_session_activity_logs_session_log_id"), "gym_session_activity_logs", ["session_log_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gym_session_activity_logs_session_log_id"), table_name="gym_session_activity_logs")
    op.drop_table("gym_session_activity_logs")
    op.drop_index(op.f("ix_gym_session_logs_template_id"), table_name="gym_session_logs")
    op.drop_index(op.f("ix_gym_session_logs_date"), table_name="gym_session_logs")
    op.drop_table("gym_session_logs")
    op.drop_index(op.f("ix_gym_template_activities_template_id"), table_name="gym_template_activities")
    op.drop_table("gym_template_activities")
    op.drop_index(op.f("ix_gym_session_templates_name"), table_name="gym_session_templates")
    op.drop_table("gym_session_templates")
