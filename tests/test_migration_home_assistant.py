"""Migration test: Home Assistant connections, entities, and observations."""

import os
import subprocess
import sys
import tempfile

import pytest
import sqlalchemy as sa


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
NEW_HEAD = "d4e5f6a7b8c9"


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


def test_home_assistant_tables_and_constraints(temp_db_path):
    _run_alembic(["upgrade", NEW_HEAD], temp_db_path)

    engine = sa.create_engine(f"sqlite:///{temp_db_path}")
    inspector = sa.inspect(engine)

    assert {
        "home_assistant_connections",
        "home_assistant_entities",
        "home_assistant_observations",
    }.issubset(inspector.get_table_names())

    connection_columns = {
        column["name"] for column in inspector.get_columns("home_assistant_connections")
    }
    assert {
        "name",
        "base_url",
        "encrypted_token",
        "enabled",
        "ha_timezone",
        "last_successful_sync_at",
    }.issubset(connection_columns)

    entity_unique = inspector.get_unique_constraints("home_assistant_entities")
    observation_unique = inspector.get_unique_constraints("home_assistant_observations")
    assert any(set(item["column_names"]) == {"connection_id", "entity_id"} for item in entity_unique)
    assert any(set(item["column_names"]) == {"entity_id", "observed_at"} for item in observation_unique)
