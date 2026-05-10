"""Database migration helpers."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    return Config(str(repo_root / "alembic.ini"))


def _upgrade_to_head() -> None:
    command.upgrade(_alembic_config(), "head")


async def run_startup_migrations() -> None:
    """Upgrade the configured application database to the latest schema."""
    await asyncio.to_thread(_upgrade_to_head)
