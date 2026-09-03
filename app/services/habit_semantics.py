"""Missing-value semantics for sparse, positive-only habit logs."""

from __future__ import annotations

from datetime import date

from app.models.database import DailyHabit, Habit


def habit_activation(habit: Habit, rows: list[DailyHabit]) -> tuple[date | None, str]:
    """Resolve an activation date without treating habit creation as tracking."""
    if habit.tracking_start_date is not None:
        return habit.tracking_start_date, "explicit_tracking_start"
    positives = [row.date for row in rows if row.habit_value > 0]
    if positives:
        return min(positives), "first_positive_fallback"
    return None, "no_positive_value"


def normalized_habit_value(
    habit: Habit, row: DailyHabit | None, target_date: date, activation: date | None
) -> tuple[int | None, str]:
    """Return effective value and auditable provenance for one calendar date."""
    # Archive timestamps are UTC-naive in the database; archive date is excluded.
    if habit.archived_at is not None and target_date >= habit.archived_at.date():
        return None, "no_longer_tracked"
    if row is not None:
        return row.habit_value, "explicit_positive" if row.habit_value > 0 else "explicit_zero"
    if activation is None or target_date < activation:
        return None, "not_yet_tracked"
    return 0, "inferred_zero"
