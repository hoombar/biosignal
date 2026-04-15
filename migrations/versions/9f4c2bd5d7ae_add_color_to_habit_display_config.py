"""add color column to habit_display_config

Revision ID: 9f4c2bd5d7ae
Revises: 8b0f3f1a6c2d
Create Date: 2026-04-15 18:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f4c2bd5d7ae"
down_revision: Union[str, Sequence[str], None] = "8b0f3f1a6c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "habit_display_config" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("habit_display_config")}
    if "color" not in columns:
        with op.batch_alter_table("habit_display_config") as batch_op:
            batch_op.add_column(sa.Column("color", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "habit_display_config" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("habit_display_config")}
    if "color" in columns:
        with op.batch_alter_table("habit_display_config") as batch_op:
            batch_op.drop_column("color")
