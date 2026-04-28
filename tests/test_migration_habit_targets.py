"""Migration test: e6f1c0a82bd5 — habits gets is_negative, target_value, period.

Verifies the additive migration:
  1. Old rows on the prior head are backfilled with sensible defaults
     (is_negative=False, target_value=NULL, period='day').
  2. The migration is idempotent enough to apply against a freshly
     created DB at the new head.
"""
import os
import subprocess
import sys
import tempfile

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PRIOR_HEAD = "d8a13b6f5042"
NEW_HEAD = "e6f1c0a82bd5"


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


def test_existing_habits_get_defaults(temp_db_path):
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO habits (name, habit_type, created_at)
                VALUES ('coffee', 'counter', '2026-01-01T00:00:00'),
                       ('pm_slump', 'binary', '2026-01-01T00:00:00')
                """
            )
        )

    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    with engine.begin() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT name, is_negative, target_value, period FROM habits ORDER BY name"
            )
        ).fetchall()
    assert [(r[0], bool(r[1]), r[2], r[3]) for r in rows] == [
        ("coffee", False, None, "day"),
        ("pm_slump", False, None, "day"),
    ]


def test_no_drift_after_upgrade(temp_db_path):
    _run_alembic(["upgrade", "head"], temp_db_path)
    # alembic check should succeed (model and DB agree)
    env = {**os.environ, "DB_PATH": temp_db_path}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic check failed:\n{result.stdout}\n{result.stderr}"
