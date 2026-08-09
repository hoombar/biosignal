"""add gym activity substitutions

Revision ID: 6d7e8f9a0b1c
Revises: 5c1d2e3f4a6b
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6d7e8f9a0b1c"
down_revision: Union[str, None] = "5c1d2e3f4a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite can leave this work table behind if an earlier batch migration was
    # interrupted. It is never part of the application schema.
    op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_gym_session_activity_logs"))
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("gym_session_activity_logs")
    }
    if "substitution_activity_id" not in columns:
        with op.batch_alter_table("gym_session_activity_logs") as batch_op:
            batch_op.add_column(sa.Column("substitution_activity_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("substitution_name_snapshot", sa.String(), nullable=True))
            batch_op.add_column(sa.Column("substitution_activity_type", sa.String(), nullable=True))
            batch_op.create_index(
                batch_op.f("ix_gym_session_activity_logs_substitution_activity_id"),
                ["substitution_activity_id"],
                unique=False,
            )
            batch_op.create_foreign_key(
                "fk_gym_session_activity_logs_substitution_activity_id_gym_activities",
                "gym_activities",
                ["substitution_activity_id"],
                ["id"],
            )

    # Existing inline template activities should immediately be reusable.
    op.execute(sa.text("""
        INSERT INTO gym_activities (
            name, activity_type, target_sets, target_reps, target_weight,
            target_weight_unit, target_duration_minutes, target_intensity,
            target_speed, notes, created_at, updated_at
        )
        SELECT
            template.name, template.activity_type, template.target_sets,
            template.target_reps, template.target_weight,
            template.target_weight_unit, template.target_duration_minutes,
            template.target_intensity, template.target_speed, template.notes,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM gym_template_activities AS template
        WHERE NOT EXISTS (
            SELECT 1 FROM gym_activities AS library WHERE library.name = template.name
        )
        GROUP BY template.name
    """))
    op.execute(sa.text("""
        UPDATE gym_template_activities
        SET activity_id = (
            SELECT library.id FROM gym_activities AS library
            WHERE library.name = gym_template_activities.name
        )
        WHERE activity_id IS NULL
    """))


def downgrade() -> None:
    with op.batch_alter_table("gym_session_activity_logs") as batch_op:
        batch_op.drop_constraint(
            "fk_gym_session_activity_logs_substitution_activity_id_gym_activities",
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_gym_session_activity_logs_substitution_activity_id"))
        batch_op.drop_column("substitution_activity_type")
        batch_op.drop_column("substitution_name_snapshot")
        batch_op.drop_column("substitution_activity_id")
