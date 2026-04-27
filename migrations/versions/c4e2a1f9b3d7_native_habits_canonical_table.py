"""native habits: canonical habits table + integer values

Revision ID: c4e2a1f9b3d7
Revises: 9f4c2bd5d7ae
Create Date: 2026-04-27 12:00:00.000000

Introduces a canonical ``habits`` table and rewrites ``daily_habits`` to FK
into it with an integer value column (binary 0/1 or counter ≥ 0).

Backfill strategy: for each distinct ``habit_name`` in the existing
``daily_habits``, infer ``habit_type`` from the values (all in
{0,1,true,false} ⇒ binary, else counter). Convert each row's string
``habit_value`` to integer using the same coercion rules previously baked
into ``_habit_value_indicates_event``. The inferred type per habit is
logged for human spot-check.
"""
import logging
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4e2a1f9b3d7"
down_revision: Union[str, Sequence[str], None] = "9f4c2bd5d7ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")


_BINARYISH_VALUES = {None, "", "0", "1"}
_BINARY_TRUE_TOKENS = {"true", "yes", "y", "on"}
_BINARY_FALSE_TOKENS = {"false", "no", "n", "off"}


def _infer_type(values: list) -> str:
    """Return 'binary' if all values look binary, else 'counter'."""
    for raw in values:
        if raw in _BINARYISH_VALUES:
            continue
        normalized = str(raw).strip().lower()
        if normalized in _BINARY_TRUE_TOKENS or normalized in _BINARY_FALSE_TOKENS:
            continue
        # any non-binary token (e.g. "2", "3") flips us to counter
        return "counter"
    return "binary"


def _coerce_value(raw, habit_type: str) -> int:
    """Convert a stored string value into the new integer encoding."""
    if raw is None:
        return 0
    text = str(raw).strip().lower()
    if text == "":
        return 0
    if text in _BINARY_TRUE_TOKENS:
        return 1
    if text in _BINARY_FALSE_TOKENS:
        return 0
    try:
        n = int(float(text))
    except (TypeError, ValueError):
        return 0
    if habit_type == "binary":
        return 1 if n > 0 else 0
    return max(n, 0)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create canonical habits table.
    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("habit_type", sa.String(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_habits_name", "habits", ["name"], unique=True)

    # 2. Backfill habits from existing daily_habits rows.
    rows = bind.execute(
        sa.text("SELECT habit_name, habit_value FROM daily_habits")
    ).fetchall()

    by_name: dict[str, list] = {}
    for row in rows:
        name = row[0]
        value = row[1]
        by_name.setdefault(name, []).append(value)

    inferred_types: dict[str, str] = {}
    now = datetime.utcnow()
    for name, values in by_name.items():
        habit_type = _infer_type(values)
        inferred_types[name] = habit_type
        bind.execute(
            sa.text(
                "INSERT INTO habits (name, habit_type, created_at) "
                "VALUES (:name, :habit_type, :created_at)"
            ),
            {"name": name, "habit_type": habit_type, "created_at": now},
        )
        logger.info(
            "habits backfill: name=%s type=%s rows=%d",
            name,
            habit_type,
            len(values),
        )

    # Build a name → id map for the upcoming row conversion.
    name_to_id = {
        row[0]: row[1]
        for row in bind.execute(sa.text("SELECT name, id FROM habits")).fetchall()
    }

    # 3. Drop existing daily_habits indexes (they share names with the
    #    new schema's indexes).
    op.drop_index("ix_daily_habits_habit_name", table_name="daily_habits")
    op.drop_index("ix_daily_habits_date", table_name="daily_habits")

    # 4. Rename old table aside, create the new shape, copy data through.
    op.rename_table("daily_habits", "daily_habits_old")

    op.create_table(
        "daily_habits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("habit_value", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "habit_id", name="uix_habit_date_habit"),
    )
    op.create_index("ix_daily_habits_date", "daily_habits", ["date"])
    op.create_index("ix_daily_habits_habit_id", "daily_habits", ["habit_id"])

    old_rows = bind.execute(
        sa.text(
            "SELECT date, habit_name, habit_value FROM daily_habits_old"
        )
    ).fetchall()

    insert_stmt = sa.text(
        "INSERT INTO daily_habits (date, habit_id, habit_value) "
        "VALUES (:date, :habit_id, :habit_value)"
    )
    for row in old_rows:
        date_value, habit_name, raw_value = row[0], row[1], row[2]
        habit_id = name_to_id.get(habit_name)
        if habit_id is None:
            # Should never happen — every habit_name was inserted above.
            logger.warning("orphan daily_habits row for unknown habit %r", habit_name)
            continue
        habit_type = inferred_types.get(habit_name, "counter")
        bind.execute(
            insert_stmt,
            {
                "date": date_value,
                "habit_id": habit_id,
                "habit_value": _coerce_value(raw_value, habit_type),
            },
        )

    op.drop_table("daily_habits_old")


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_daily_habits_habit_id", table_name="daily_habits")
    op.drop_index("ix_daily_habits_date", table_name="daily_habits")
    op.rename_table("daily_habits", "daily_habits_new")

    op.create_table(
        "daily_habits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("habit_name", sa.String(), nullable=False),
        sa.Column("habit_value", sa.String(), nullable=False),
        sa.Column("habit_type", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "habit_name", name="uix_habit_date_name"),
    )
    op.create_index("ix_daily_habits_date", "daily_habits", ["date"])
    op.create_index("ix_daily_habits_habit_name", "daily_habits", ["habit_name"])

    bind.execute(
        sa.text(
            """
            INSERT INTO daily_habits (date, habit_name, habit_value, habit_type)
            SELECT new.date, h.name, CAST(new.habit_value AS TEXT), h.habit_type
            FROM daily_habits_new new
            JOIN habits h ON h.id = new.habit_id
            """
        )
    )

    op.drop_table("daily_habits_new")
    op.drop_index("ix_habits_name", table_name="habits")
    op.drop_table("habits")
