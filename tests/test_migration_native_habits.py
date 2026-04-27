"""Migration test: c4e2a1f9b3d7 — canonical habits table backfill.

Spins up a temp SQLite DB, applies migrations through the previous head,
seeds old-format daily_habits rows, then upgrades to the new head and
verifies:
  - habits table is populated with correct types per habit name
  - daily_habits rows are converted to integer values + habit_id FK
"""
import os
import subprocess
import sys
import tempfile
from datetime import date

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PRIOR_HEAD = "9f4c2bd5d7ae"
NEW_HEAD = "c4e2a1f9b3d7"


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


def test_migration_backfills_habits_and_converts_values(temp_db_path):
    # Apply migrations through the prior head only.
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO daily_habits (date, habit_name, habit_value, habit_type) VALUES
                  ('2026-01-01', 'pm_slump', 'true', 'boolean'),
                  ('2026-01-02', 'pm_slump', 'false', 'boolean'),
                  ('2026-01-03', 'pm_slump', '1', 'counter'),
                  ('2026-01-01', 'coffee', '3', 'counter'),
                  ('2026-01-02', 'coffee', '2', 'counter'),
                  ('2026-01-03', 'coffee', '0', 'counter')
                """
            )
        )

    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    with engine.begin() as conn:
        habits = conn.execute(
            sa.text("SELECT name, habit_type FROM habits ORDER BY name")
        ).fetchall()
        assert [(row[0], row[1]) for row in habits] == [
            ("coffee", "counter"),
            ("pm_slump", "binary"),
        ]

        rows = conn.execute(
            sa.text(
                """
                SELECT dh.date, h.name, dh.habit_value
                FROM daily_habits dh
                JOIN habits h ON h.id = dh.habit_id
                ORDER BY dh.date, h.name
                """
            )
        ).fetchall()

    assert [(str(r[0]), r[1], r[2]) for r in rows] == [
        ("2026-01-01", "coffee", 3),
        ("2026-01-01", "pm_slump", 1),
        ("2026-01-02", "coffee", 2),
        ("2026-01-02", "pm_slump", 0),
        ("2026-01-03", "coffee", 0),
        ("2026-01-03", "pm_slump", 1),
    ]


def test_migration_no_data_to_backfill(temp_db_path):
    """Migration handles an empty daily_habits table cleanly."""
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)
    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        habit_count = conn.execute(sa.text("SELECT COUNT(*) FROM habits")).scalar_one()
        daily_count = conn.execute(sa.text("SELECT COUNT(*) FROM daily_habits")).scalar_one()
    assert habit_count == 0
    assert daily_count == 0


def test_migration_downgrade_reverses_changes(temp_db_path):
    """Downgrade reconstructs the old schema; data round-trips through binary→string."""
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO daily_habits (date, habit_name, habit_value, habit_type) VALUES
                  ('2026-02-10', 'pm_slump', 'true', 'boolean'),
                  ('2026-02-10', 'coffee', '2', 'counter')
                """
            )
        )

    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)
    _run_alembic(["downgrade", PRIOR_HEAD], temp_db_path)

    with engine.begin() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT habit_name, habit_value, habit_type FROM daily_habits ORDER BY habit_name"
            )
        ).fetchall()

    # After downgrade the integer-encoded value comes back as its string form;
    # type comes from the habit row that was inferred during upgrade.
    assert rows == [
        ("coffee", "2", "counter"),
        ("pm_slump", "1", "binary"),
    ]
