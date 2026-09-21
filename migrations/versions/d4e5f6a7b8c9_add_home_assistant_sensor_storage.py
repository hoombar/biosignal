"""Add Home Assistant connections, entities, and observations."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "home_assistant_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("ha_timezone", sa.String(), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "home_assistant_entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("device_class", sa.String(), nullable=True),
        sa.Column("source_unit", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["home_assistant_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id", "entity_id", name="uix_home_assistant_connection_entity"
        ),
    )
    op.create_index(
        "ix_home_assistant_entities_role", "home_assistant_entities", ["role"], unique=False
    )
    op.create_table(
        "home_assistant_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("source_unit", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["home_assistant_entities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id", "observed_at", name="uix_home_assistant_entity_observed_at"
        ),
    )
    op.create_index(
        "ix_home_assistant_observation_entity_time",
        "home_assistant_observations",
        ["entity_id", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_home_assistant_observation_entity_time",
        table_name="home_assistant_observations",
    )
    op.drop_table("home_assistant_observations")
    op.drop_index("ix_home_assistant_entities_role", table_name="home_assistant_entities")
    op.drop_table("home_assistant_entities")
    op.drop_table("home_assistant_connections")
