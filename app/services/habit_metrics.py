"""Hit/streak/completion-rate computation for the generic habit tracker.

Single source of truth for "did I hit habit H in period P?" Used by the
list endpoint to surface streaks and the rolling completion rate, and by
the daily UI's polarity-aware coloring.

Period semantics
----------------
- ``day``     → keyed by the date itself.
- ``week``    → ISO 8601 week, keyed by ``(year, isoweek)``. Monday-start.
- ``month``   → calendar month, keyed by ``(year, month)``.

Today's period is treated as *in progress*: it never counts against the
streak (so a negative-habit user who's about to over-pour at 11pm doesn't
already "lose" their streak). The streak walks backward starting from
the period immediately before today's.

Hit rules
---------
A period is a "hit" when its summed value satisfies::

    positive habit, no target  → total > 0
    positive habit, target = N → total ≥ N
    negative habit, no target  → total == 0
    negative habit, target = N → total ≤ N

Periods with no rows have total=0 (so e.g. a negative habit with no
recorded "indulgence" days is consistently a hit).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as DateType, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.database import DailyHabit, Habit


PeriodKey = int | tuple[int, int]


COMPLETION_WINDOWS = {"day": 7, "week": 4, "month": 3}
STREAK_SAFETY_CAP = 730  # match the row lookback so we never spin forever


def _period_key(d: DateType, period: str) -> PeriodKey:
    if period == "day":
        return d.toordinal()
    if period == "week":
        iso = d.isocalendar()
        return (iso.year, iso.week)
    if period == "month":
        return (d.year, d.month)
    raise ValueError(f"unknown period: {period!r}")


def _previous_period_key(key: PeriodKey, period: str) -> PeriodKey:
    if period == "day":
        return key - 1  # type: ignore[operator]
    if period == "week":
        year, week = key  # type: ignore[misc]
        anchor = DateType.fromisocalendar(year, week, 1) - timedelta(days=7)
        iso = anchor.isocalendar()
        return (iso.year, iso.week)
    if period == "month":
        year, month = key  # type: ignore[misc]
        if month == 1:
            return (year - 1, 12)
        return (year, month - 1)
    raise ValueError(f"unknown period: {period!r}")


def hit_state(habit: Habit, total: int) -> bool:
    """Is the habit hit for a period whose summed value is ``total``?"""
    if habit.is_negative:
        if habit.target_value is None:
            return total == 0
        return total <= habit.target_value
    if habit.target_value is None:
        return total > 0
    return total >= habit.target_value


def _totals_by_period(rows: list[tuple[DateType, int]], period: str) -> dict[PeriodKey, int]:
    out: dict[PeriodKey, int] = defaultdict(int)
    for d, v in rows:
        out[_period_key(d, period)] += v
    return out


def compute_streak(habit: Habit, totals: dict[PeriodKey, int], today: DateType) -> int:
    """Count consecutive hits walking backward from the period before today's."""
    today_key = _period_key(today, habit.period)
    key = _previous_period_key(today_key, habit.period)
    streak = 0
    while streak < STREAK_SAFETY_CAP:
        total = totals.get(key, 0)
        if not hit_state(habit, total):
            break
        streak += 1
        key = _previous_period_key(key, habit.period)
    return streak


def compute_completion(
    habit: Habit, totals: dict[PeriodKey, int], today: DateType
) -> tuple[int, int]:
    """Return ``(hits, total_periods)`` over the rolling window before today."""
    window = COMPLETION_WINDOWS[habit.period]
    today_key = _period_key(today, habit.period)
    key = _previous_period_key(today_key, habit.period)
    hits = 0
    for _ in range(window):
        total = totals.get(key, 0)
        if hit_state(habit, total):
            hits += 1
        key = _previous_period_key(key, habit.period)
    return hits, window


async def _load_rows_for_habits(
    session: AsyncSession,
    habit_ids: Iterable[int],
    cutoff: DateType,
) -> dict[int, list[tuple[DateType, int]]]:
    ids = list(habit_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(DailyHabit.habit_id, DailyHabit.date, DailyHabit.habit_value)
        .where(DailyHabit.habit_id.in_(ids))
        .where(DailyHabit.date >= cutoff)
    )
    by_habit: dict[int, list[tuple[DateType, int]]] = defaultdict(list)
    for habit_id, d, v in result.all():
        by_habit[habit_id].append((d, v))
    return by_habit


def _today_in_app_tz() -> DateType:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.tz)).date()


async def compute_metrics(
    session: AsyncSession,
    habits: list[Habit],
    today: DateType | None = None,
) -> dict[int, dict[str, int]]:
    """Return ``{habit_id: {streak, completion_hit, completion_total}}``.

    Single batched query for all the input habits — fine for the list
    endpoint where we render the whole habit set at once.
    """
    if today is None:
        today = _today_in_app_tz()
    if not habits:
        return {}

    # 2 years of history covers the safety-capped streak window plus the
    # 4-week / 3-month completion window with margin to spare.
    cutoff = today - timedelta(days=730)
    rows_by_habit = await _load_rows_for_habits(session, [h.id for h in habits], cutoff)

    out: dict[int, dict[str, int]] = {}
    for habit in habits:
        totals = _totals_by_period(rows_by_habit.get(habit.id, []), habit.period)
        streak = compute_streak(habit, totals, today)
        hits, total = compute_completion(habit, totals, today)
        out[habit.id] = {
            "streak": streak,
            "completion_hit": hits,
            "completion_total": total,
        }
    return out
