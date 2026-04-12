"""add habit_display_config table

Revision ID: 8b0f3f1a6c2d
Revises: 2f297e1ff2b9
Create Date: 2026-04-12 17:36:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b0f3f1a6c2d"
down_revision: Union[str, Sequence[str], None] = "2f297e1ff2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_unique_habit_name_index(inspector: sa.Inspector) -> bool:
    indexes = inspector.get_indexes("habit_display_config")
    return any(
        idx.get("unique") and idx.get("column_names") == ["habit_name"]
        for idx in indexes
    )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "habit_display_config" not in tables:
        op.create_table(
            "habit_display_config",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("habit_name", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("emoji", sa.String(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_habit_display_config_habit_name",
            "habit_display_config",
            ["habit_name"],
            unique=True,
        )
        return

    # Existing table path: make migration idempotent for environments where the
    # table was created previously via SQLAlchemy metadata.
    columns = {col["name"] for col in inspector.get_columns("habit_display_config")}
    if "id" not in columns or "habit_name" not in columns:
        raise RuntimeError("habit_display_config exists but is missing required columns")

    if "display_name" not in columns:
        with op.batch_alter_table("habit_display_config") as batch_op:
            batch_op.add_column(sa.Column("display_name", sa.String(), nullable=True))

    if "emoji" not in columns:
        with op.batch_alter_table("habit_display_config") as batch_op:
            batch_op.add_column(sa.Column("emoji", sa.String(), nullable=True))

    if "sort_order" not in columns:
        with op.batch_alter_table("habit_display_config") as batch_op:
            batch_op.add_column(
                sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False)
            )

    if not _has_unique_habit_name_index(inspector):
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_habit_display_config_habit_name "
                "ON habit_display_config (habit_name)"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    inspector = sa.inspect(op.get_bind())
    if "habit_display_config" in set(inspector.get_table_names()):
        op.drop_table("habit_display_config")
