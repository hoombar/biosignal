"""Migration test: f3a7c9d0e1b2 — habits get stable UUIDs."""
import os
import subprocess
import sys
import tempfile
from uuid import UUID

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PRIOR_HEAD = "e6f1c0a82bd5"
NEW_HEAD = "f3a7c9d0e1b2"


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


def test_existing_habits_get_unique_uuids(temp_db_path):
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO habits (name, habit_type, created_at)
                VALUES ('coffee', 'counter', '2026-01-01T00:00:00'),
                       ('healthy_lunch', 'binary', '2026-01-01T00:00:00')
                """
            )
        )

    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    with engine.begin() as conn:
        rows = conn.execute(
            sa.text("SELECT name, uuid FROM habits ORDER BY name")
        ).fetchall()
        indexes = conn.execute(sa.text("PRAGMA index_list('habits')")).fetchall()

    assert [row[0] for row in rows] == ["coffee", "healthy_lunch"]
    uuids = [row[1] for row in rows]
    assert len(set(uuids)) == 2
    assert all(str(UUID(value)) == value for value in uuids)
    assert any(index[1] == "ix_habits_uuid" and index[2] for index in indexes)


def test_no_drift_after_uuid_upgrade(temp_db_path):
    _run_alembic(["upgrade", "head"], temp_db_path)
    env = {**os.environ, "DB_PATH": temp_db_path}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic check failed:\n{result.stdout}\n{result.stderr}"
