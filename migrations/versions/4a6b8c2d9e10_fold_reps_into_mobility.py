"""fold reps into mobility

Revision ID: 4a6b8c2d9e10
Revises: 7b6a5c4d3e2f
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a6b8c2d9e10"
down_revision: Union[str, None] = "7b6a5c4d3e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE gym_template_activities
        SET activity_type = 'mobility',
            target_weight = NULL,
            target_weight_unit = NULL,
            target_duration_minutes = NULL,
            target_intensity = NULL,
            target_speed = NULL,
            notes = NULL
        WHERE activity_type IN ('reps', 'mobility')
    """))
    bind.execute(sa.text("""
        UPDATE gym_session_activity_logs
        SET activity_type = 'mobility',
            planned_weight = NULL,
            planned_weight_unit = NULL,
            planned_duration_minutes = NULL,
            planned_intensity = NULL,
            planned_speed = NULL,
            planned_notes = NULL,
            actual_weight = NULL,
            actual_weight_unit = NULL,
            actual_duration_minutes = NULL,
            actual_intensity = NULL,
            actual_speed = NULL,
            notes = NULL
        WHERE activity_type IN ('reps', 'mobility')
    """))


def downgrade() -> None:
    pass
