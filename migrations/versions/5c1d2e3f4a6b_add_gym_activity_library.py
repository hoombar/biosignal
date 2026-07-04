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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "gym_activities" not in table_names:
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

    _ensure_activity_reference(inspector, "gym_template_activities")
    inspector = sa.inspect(bind)
    _ensure_activity_reference(inspector, "gym_session_activity_logs")


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


def _ensure_activity_reference(inspector, table_name: str) -> None:
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    has_fk = any(
        fk.get("referred_table") == "gym_activities"
        and fk.get("constrained_columns") == ["activity_id"]
        for fk in inspector.get_foreign_keys(table_name)
    )

    with op.batch_alter_table(table_name) as batch_op:
        if "activity_id" not in columns:
            batch_op.add_column(sa.Column("activity_id", sa.Integer(), nullable=True))
        index_name = batch_op.f(f"ix_{table_name}_activity_id")
        if index_name not in indexes:
            batch_op.create_index(index_name, ["activity_id"], unique=False)
        if not has_fk:
            batch_op.create_foreign_key(
                f"fk_{table_name}_activity_id_gym_activities",
                "gym_activities",
                ["activity_id"],
                ["id"],
            )
