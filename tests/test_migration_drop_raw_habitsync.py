"""Migration test: d8a13b6f5042 — drop raw_habitsync_responses with backup.

Verifies that the upgrade path:
  1. Writes a JSON backup next to the SQLite DB before dropping the table
  2. Removes the table cleanly
  3. Is a no-op on a database where the table is already absent
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PRIOR_HEAD = "c4e2a1f9b3d7"
NEW_HEAD = "d8a13b6f5042"


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
    backup = Path(path).parent / "raw_habitsync_responses_backup.json"
    try:
        backup.unlink()
    except FileNotFoundError:
        pass


def test_drop_writes_backup_and_removes_table(temp_db_path):
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO raw_habitsync_responses (date, response, fetched_at)
                VALUES ('2026-04-01', '{"habits":["coffee"]}', '2026-04-01T08:00:00')
                """
            )
        )

    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    inspector = sa.inspect(engine)
    assert "raw_habitsync_responses" not in inspector.get_table_names()

    backup_path = Path(temp_db_path).parent / "raw_habitsync_responses_backup.json"
    assert backup_path.exists(), f"backup not written: {backup_path}"
    payload = json.loads(backup_path.read_text())
    assert len(payload) == 1
    assert payload[0]["date"] == "2026-04-01"


def test_drop_with_no_rows_skips_backup(temp_db_path):
    _run_alembic(["upgrade", PRIOR_HEAD], temp_db_path)
    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    inspector = sa.inspect(engine)
    assert "raw_habitsync_responses" not in inspector.get_table_names()

    backup_path = Path(temp_db_path).parent / "raw_habitsync_responses_backup.json"
    assert not backup_path.exists()
