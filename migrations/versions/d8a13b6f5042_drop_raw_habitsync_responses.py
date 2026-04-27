"""drop raw_habitsync_responses (after one-shot history import)

Revision ID: d8a13b6f5042
Revises: c4e2a1f9b3d7
Create Date: 2026-04-27 13:00:00.000000

Removes the cache of raw HabitSync API payloads. Native habit logging
is now in biosignal, so the external HabitSync integration — and its
raw-response cache — are no longer needed.

Safety net: before dropping the table, the upgrade dumps every row to
``${data_dir}/raw_habitsync_responses_backup.json`` (one JSON object
per row, alongside the SQLite DB file). If the dump can't be written
(read-only filesystem, etc.) the migration logs a warning and proceeds
— the data is replaceable from the live HabitSync instance and the
canonical ``daily_habits`` rows already contain the parsed values that
matter.
"""
import json
import logging
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8a13b6f5042"
down_revision: Union[str, Sequence[str], None] = "c4e2a1f9b3d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")


def _dump_backup(rows: list) -> None:
    """Write rows to ``raw_habitsync_responses_backup.json`` next to the DB."""
    if not rows:
        logger.info("raw_habitsync_responses is empty; no backup written")
        return

    bind = op.get_bind()
    db_url = str(bind.engine.url)
    # Resolve a sibling path next to the DB file. URL form: sqlite:///abs/path.db
    if "://" in db_url and db_url.split("://", 1)[1]:
        db_path = Path(db_url.split("://", 1)[1].lstrip("/"))
        if not db_path.is_absolute():
            db_path = Path("/") / db_path
        target_dir = db_path.parent
    else:
        target_dir = Path.cwd()

    backup_path = target_dir / "raw_habitsync_responses_backup.json"
    payload = [
        {
            "id": row[0],
            "date": str(row[1]),
            "response": row[2],
            "fetched_at": str(row[3]) if row[3] is not None else None,
        }
        for row in rows
    ]
    try:
        backup_path.write_text(json.dumps(payload, indent=2))
        logger.info(
            "raw_habitsync_responses backup written: %s (%d rows)",
            backup_path,
            len(payload),
        )
    except OSError as exc:
        logger.warning(
            "could not write raw_habitsync_responses backup to %s: %s",
            backup_path,
            exc,
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "raw_habitsync_responses" not in set(inspector.get_table_names()):
        logger.info("raw_habitsync_responses already absent; nothing to drop")
        return

    rows = bind.execute(
        sa.text("SELECT id, date, response, fetched_at FROM raw_habitsync_responses")
    ).fetchall()
    _dump_backup(list(rows))

    op.drop_table("raw_habitsync_responses")


def downgrade() -> None:
    """Recreate the empty table. Backup data is not auto-restored — load from
    ``raw_habitsync_responses_backup.json`` manually if needed."""
    op.create_table(
        "raw_habitsync_responses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )
