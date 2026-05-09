"""Migration test for supplement group tracking schema."""

import os
import subprocess
import sys
import tempfile

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PRIOR_HEAD = "a1d2e3f4b5c6"
NEW_HEAD = "b1c2d3e4f5a6"


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


def test_supplement_schema_and_habit_source_defaults(temp_db_path):
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO habits (uuid, name, habit_type, created_at)
                VALUES ('00000000-0000-0000-0000-000000000001', 'coffee', 'counter', '2026-01-01T00:00:00')
                """
            )
        )

    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    with engine.begin() as conn:
        habit = conn.execute(sa.text("SELECT name, source FROM habits")).one()
        assert habit == ("coffee", "manual")

        tables = {
            row[0]
            for row in conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        assert "supplement_plan_versions" in tables
        assert "supplement_logs" in tables

        conn.execute(
            sa.text(
                """
                INSERT INTO supplement_plan_versions (slot, version, items, created_at)
                VALUES ('morning', 1, '[]', '2026-05-09T00:00:00')
                """
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO supplement_plan_versions (slot, version, items, created_at)
                    VALUES ('morning', 1, '[]', '2026-05-09T00:00:00')
                    """
                )
            )


def test_no_drift_after_upgrade(temp_db_path):
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
