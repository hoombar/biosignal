"""Migration test: e2f3a4b5c6d7 — app settings table."""
import os
import subprocess
import sys
import tempfile

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
NEW_HEAD = "e2f3a4b5c6d7"


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


def test_app_settings_table_created_with_unique_key(temp_db_path):
    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    with engine.begin() as conn:
        columns = conn.execute(sa.text("PRAGMA table_info('app_settings')")).fetchall()
        indexes = conn.execute(sa.text("PRAGMA index_list('app_settings')")).fetchall()

    column_names = {column[1] for column in columns}
    assert {"id", "key", "value", "created_at", "updated_at"}.issubset(column_names)
    assert any(index[2] for index in indexes)
