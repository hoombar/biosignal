#!/usr/bin/env python3
"""One-shot import of habit history from an external HabitSync instance.

Run after the canonical-habits migration has been applied to the live DB.
Pulls every habit (with embedded records) from HabitSync, ensures a Habit
row exists per habit name, and upserts a DailyHabit row for each record
that falls inside ``--from``..``--to`` (inclusive).

Idempotent: re-running on the same range overwrites existing values for
those (date, habit) cells but doesn't duplicate rows.

Usage:
    docker compose exec biosignal python -m scripts.import_habitsync_history \\
        --from 2025-01-01 --to 2026-04-26 \\
        --binary pm_slump,healthy_lunch,carb_heavy_lunch \\
        --counter coffee,alcohol

Habit type defaults to ``counter`` if a name isn't listed in either
``--binary`` or ``--counter``.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.database import DailyHabit, Habit


logger = logging.getLogger("import_habitsync_history")


EPOCH = date(1970, 1, 1)


def _normalize_habit_name(name: str) -> str:
    """Normalize a habit name to snake_case (matches HabitSync's rule)."""
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return normalized.strip("_")


async def _fetch_habits(base_url: str, api_key: str) -> list[dict]:
    """Pull every habit (with embedded records) from a HabitSync instance.

    Tries the documented endpoint first and falls back to a couple of
    older paths so this script keeps working across HabitSync versions.
    """
    base_url = base_url.rstrip("/")
    endpoints = ["/api/habit/list", "/api/user/habit", "/api/habit"]
    async with httpx.AsyncClient(
        headers={"X-API-Key": api_key}, timeout=30.0
    ) as client:
        last_error: Exception | None = None
        for path in endpoints:
            try:
                resp = await client.get(f"{base_url}{path}")
                resp.raise_for_status()
                if "application/json" not in resp.headers.get("content-type", ""):
                    last_error = RuntimeError(f"non-JSON response from {path}")
                    continue
                data = resp.json()
                logger.info("fetched %d habits via %s", len(data), path)
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning("endpoint %s failed: %s", path, exc)
        raise RuntimeError(f"all HabitSync endpoints failed: {last_error}")


def _parse_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {_normalize_habit_name(item) for item in value.split(",") if item.strip()}


def _coerce_value(raw, habit_type: str, completion: str | None) -> int:
    """Encode a HabitSync record value into the integer schema."""
    try:
        n = int(float(raw)) if raw is not None else 0
        has_numeric_value = raw is not None
    except (TypeError, ValueError):
        n = 0
        has_numeric_value = False
    if habit_type == "binary":
        if n > 0:
            return 1
        if not has_numeric_value and completion in (
            "COMPLETED",
            "COMPLETED_BY_OTHER_RECORDS",
        ):
            return 1
        return 0
    return max(n, 0)


async def _ensure_habit(
    session: AsyncSession, name: str, habit_type: str
) -> Habit:
    result = await session.execute(select(Habit).where(Habit.name == name))
    habit = result.scalar_one_or_none()
    if habit is not None:
        return habit
    habit = Habit(name=name, habit_type=habit_type)
    session.add(habit)
    await session.flush()
    logger.info("created habit %r as %s", name, habit_type)
    return habit


async def _import(
    start: date,
    end: date,
    binary_names: set[str],
    counter_names: set[str],
) -> None:
    base_url = os.environ.get("HABITSYNC_URL")
    api_key = os.environ.get("HABITSYNC_API_KEY")
    if not base_url or not api_key:
        sys.exit(
            "HABITSYNC_URL and HABITSYNC_API_KEY must be set in the environment "
            "for this one-shot import."
        )

    habits = await _fetch_habits(base_url, api_key)

    if not habits:
        logger.error("HabitSync returned no habits — aborting")
        return

    total_inserted = 0
    total_skipped_out_of_range = 0
    summary_per_habit: dict[str, int] = {}

    async with async_session_maker() as session:
        for habit_payload in habits:
            raw_name = habit_payload.get("name")
            if not raw_name:
                continue
            name = _normalize_habit_name(raw_name)

            if name in binary_names:
                habit_type = "binary"
            elif name in counter_names:
                habit_type = "counter"
            else:
                # Heuristic fallback for unflagged habits: HabitSync tags
                # YesNoHabit vs CounterHabit on each habit object.
                api_type = (habit_payload.get("type") or "").lower()
                if "yes" in api_type or "no" in api_type:
                    habit_type = "binary"
                else:
                    habit_type = "counter"
                logger.info(
                    "habit %r not flagged on CLI; defaulting type=%s",
                    name,
                    habit_type,
                )

            habit = await _ensure_habit(session, name, habit_type)
            inserted_for_habit = 0

            for record in habit_payload.get("records", []) or []:
                epoch_day = record.get("epochDay")
                if epoch_day is None:
                    continue
                record_date = EPOCH + timedelta(days=int(epoch_day))
                if record_date < start or record_date > end:
                    total_skipped_out_of_range += 1
                    continue

                value = _coerce_value(
                    record.get("recordValue"),
                    habit_type,
                    record.get("completion"),
                )
                stmt = insert(DailyHabit).values(
                    date=record_date,
                    habit_id=habit.id,
                    habit_value=value,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "habit_id"],
                    set_={"habit_value": stmt.excluded.habit_value},
                )
                await session.execute(stmt)
                inserted_for_habit += 1
                total_inserted += 1

            summary_per_habit[name] = inserted_for_habit
            logger.info(
                "habit %r (%s): %d records imported",
                name,
                habit_type,
                inserted_for_habit,
            )

        await session.commit()

    logger.info(
        "import complete: %d records written across %d habits "
        "(%d records outside %s..%s skipped)",
        total_inserted,
        len(summary_per_habit),
        total_skipped_out_of_range,
        start,
        end,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="start",
        required=True,
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Earliest record date to import (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--to",
        dest="end",
        required=True,
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Latest record date to import (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--binary",
        default="",
        help="Comma-separated habit names (post-normalization) to treat as binary",
    )
    parser.add_argument(
        "--counter",
        default="",
        help="Comma-separated habit names (post-normalization) to treat as counter",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args()
    if args.start > args.end:
        sys.exit("--from must be before or equal to --to")
    binary_names = _parse_csv(args.binary)
    counter_names = _parse_csv(args.counter)
    overlap = binary_names & counter_names
    if overlap:
        sys.exit(f"habits listed in both --binary and --counter: {sorted(overlap)}")
    asyncio.run(_import(args.start, args.end, binary_names, counter_names))


if __name__ == "__main__":
    main()
