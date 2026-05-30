"""Startup migration behavior."""

import os
import subprocess
import sys
import tempfile

import pytest
import sqlalchemy as sa

from app.core.config import get_settings


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PRIOR_HEAD = "a1d2e3f4b5c6"
CURRENT_HEAD = "e2f3a4b5c6d7"


def _run_alembic(args: list[str], db_path: str) -> None:
    env = {**os.environ, "DB_PATH": db_path}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {' '.join(args)} failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.mark.asyncio
async def test_startup_migrations_upgrade_database_to_head(monkeypatch, temp_db_path):
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    monkeypatch.setenv("DB_PATH", temp_db_path)
    get_settings.cache_clear()

    from app.core.migrations import run_startup_migrations

    await run_startup_migrations()

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        revision = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        habit_columns = {
            row[1]
            for row in conn.execute(sa.text("PRAGMA table_info('habits')")).fetchall()
        }
        tables = {
            row[0]
            for row in conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }

    assert revision == CURRENT_HEAD
    assert "source" in habit_columns
    assert "supplement_plan_versions" in tables
    assert "context_events" in tables
    assert "app_settings" in tables
