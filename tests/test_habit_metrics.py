"""Tests for app/services/habit_metrics.py.

Pure unit tests for hit_state and the period helpers, plus async tests
for compute_streak / compute_completion / compute_metrics that seed
the in-memory DB with deterministic patterns.
"""
from datetime import date, timedelta

import pytest

from app.models.database import Habit
from app.services.habit_metrics import (
    compute_completion,
    compute_metrics,
    compute_streak,
    hit_state,
    _period_key,
    _previous_period_key,
    _totals_by_period,
)
from tests.conftest import ensure_habit, log_habit


def _make_habit(**kwargs) -> Habit:
    """Construct a Habit instance without touching the DB (handy for hit_state tests)."""
    defaults = dict(
        id=1,
        name="x",
        habit_type="counter",
        archived_at=None,
        is_negative=False,
        target_value=None,
        period="day",
    )
    defaults.update(kwargs)
    return Habit(**defaults)


class TestHitState:

    def test_positive_no_target_zero_is_miss(self):
        assert hit_state(_make_habit(is_negative=False, target_value=None), 0) is False

    def test_positive_no_target_any_positive_is_hit(self):
        assert hit_state(_make_habit(is_negative=False, target_value=None), 1) is True

    def test_positive_with_target_below_is_miss(self):
        assert hit_state(_make_habit(is_negative=False, target_value=3), 2) is False

    def test_positive_with_target_at_threshold_is_hit(self):
        assert hit_state(_make_habit(is_negative=False, target_value=3), 3) is True

    def test_positive_with_target_above_is_hit(self):
        assert hit_state(_make_habit(is_negative=False, target_value=3), 5) is True

    def test_negative_no_target_zero_is_hit(self):
        assert hit_state(_make_habit(is_negative=True, target_value=None), 0) is True

    def test_negative_no_target_any_positive_is_miss(self):
        assert hit_state(_make_habit(is_negative=True, target_value=None), 1) is False

    def test_negative_with_target_below_is_hit(self):
        assert hit_state(_make_habit(is_negative=True, target_value=2), 1) is True

    def test_negative_with_target_at_threshold_is_hit(self):
        assert hit_state(_make_habit(is_negative=True, target_value=2), 2) is True

    def test_negative_with_target_above_is_miss(self):
        assert hit_state(_make_habit(is_negative=True, target_value=2), 3) is False


class TestPeriodKeys:

    def test_day_key_is_ordinal(self):
        assert _period_key(date(2026, 4, 28), "day") == date(2026, 4, 28).toordinal()

    def test_week_key_uses_iso_calendar(self):
        # 2026-04-28 is a Tuesday in ISO week 18
        assert _period_key(date(2026, 4, 28), "week") == (2026, 18)

    def test_month_key(self):
        assert _period_key(date(2026, 4, 28), "month") == (2026, 4)

    def test_previous_day(self):
        d = date(2026, 4, 28).toordinal()
        assert _previous_period_key(d, "day") == d - 1

    def test_previous_week_within_year(self):
        assert _previous_period_key((2026, 18), "week") == (2026, 17)

    def test_previous_week_crosses_year(self):
        # 2026 has 53 ISO weeks (Jan 1 falls on a Thursday). So week 1 of
        # 2027 has week 53 of 2026 as its predecessor.
        assert _previous_period_key((2027, 1), "week") == (2026, 53)
        # And 2025 has only 52 weeks, so week 1 of 2026 → week 52 of 2025.
        assert _previous_period_key((2026, 1), "week") == (2025, 52)

    def test_previous_month_within_year(self):
        assert _previous_period_key((2026, 4), "month") == (2026, 3)

    def test_previous_month_january_wraps(self):
        assert _previous_period_key((2026, 1), "month") == (2025, 12)


class TestTotalsByPeriod:

    def test_daily_groups_per_date(self):
        rows = [
            (date(2026, 4, 28), 2),
            (date(2026, 4, 27), 3),
        ]
        totals = _totals_by_period(rows, "day")
        assert totals[date(2026, 4, 28).toordinal()] == 2
        assert totals[date(2026, 4, 27).toordinal()] == 3

    def test_weekly_sums_within_iso_week(self):
        # 2026-04-27 (Mon) + 2026-04-28 (Tue) are both ISO week 18
        rows = [
            (date(2026, 4, 27), 2),
            (date(2026, 4, 28), 3),
        ]
        totals = _totals_by_period(rows, "week")
        assert totals[(2026, 18)] == 5

    def test_monthly_sums_within_month(self):
        rows = [
            (date(2026, 4, 1), 1),
            (date(2026, 4, 30), 4),
        ]
        totals = _totals_by_period(rows, "month")
        assert totals[(2026, 4)] == 5


class TestComputeStreak:

    def test_no_data_yields_zero(self):
        habit = _make_habit(period="day")
        assert compute_streak(habit, totals={}, today=date(2026, 4, 28)) == 0

    def test_three_day_streak_excluding_today(self):
        habit = _make_habit(period="day", target_value=None)
        # Hits on the 3 days BEFORE today (today excluded from streak)
        totals = {
            date(2026, 4, 27).toordinal(): 1,
            date(2026, 4, 26).toordinal(): 2,
            date(2026, 4, 25).toordinal(): 5,
        }
        assert compute_streak(habit, totals, today=date(2026, 4, 28)) == 3

    def test_streak_breaks_on_miss(self):
        habit = _make_habit(period="day", target_value=None)
        totals = {
            date(2026, 4, 27).toordinal(): 1,
            date(2026, 4, 26).toordinal(): 0,  # miss
            date(2026, 4, 25).toordinal(): 5,
        }
        assert compute_streak(habit, totals, today=date(2026, 4, 28)) == 1

    def test_negative_habit_streak_with_no_logs(self):
        """Negative habit with no rows: every period is a hit (total=0)."""
        habit = _make_habit(is_negative=True, target_value=None)
        # Empty totals; "no smoking" with zero rows is consecutive hits.
        # Capped at the safety limit, so we just confirm a large count.
        streak = compute_streak(habit, totals={}, today=date(2026, 4, 28))
        assert streak >= 30  # safety cap is 730; we just need non-zero

    def test_negative_habit_streak_breaks_on_indulgence(self):
        habit = _make_habit(is_negative=True, target_value=2)
        totals = {
            date(2026, 4, 27).toordinal(): 1,  # hit (≤2)
            date(2026, 4, 26).toordinal(): 5,  # miss (>2)
            date(2026, 4, 25).toordinal(): 0,  # would be hit, but streak broken
        }
        assert compute_streak(habit, totals, today=date(2026, 4, 28)) == 1

    def test_weekly_streak(self):
        habit = _make_habit(period="week", target_value=3)
        # Today is in week 18. Streak walks back from week 17.
        totals = {(2026, 17): 4, (2026, 16): 3, (2026, 15): 2}
        assert compute_streak(habit, totals, today=date(2026, 4, 28)) == 2

    def test_monthly_streak(self):
        habit = _make_habit(period="month", target_value=10)
        totals = {(2026, 3): 12, (2026, 2): 11, (2026, 1): 5}
        # Today is April 2026. Walk: March (hit), Feb (hit), Jan (miss)
        assert compute_streak(habit, totals, today=date(2026, 4, 1)) == 2


class TestComputeCompletion:

    def test_returns_window_size_as_total(self):
        habit = _make_habit(period="day")
        hits, total = compute_completion(habit, totals={}, today=date(2026, 4, 28))
        assert total == 7  # default daily window
        assert hits == 0

    def test_partial_hits_in_window(self):
        habit = _make_habit(period="day", target_value=None)
        # 4 of the last 7 days hit
        totals = {
            (date(2026, 4, 28) - timedelta(days=i)).toordinal(): (1 if i in {1, 2, 4, 7} else 0)
            for i in range(1, 8)
        }
        hits, total = compute_completion(habit, totals, today=date(2026, 4, 28))
        assert (hits, total) == (4, 7)

    def test_weekly_window_is_four_weeks(self):
        habit = _make_habit(period="week", target_value=2)
        totals = {(2026, 17): 3, (2026, 16): 1, (2026, 15): 2, (2026, 14): 5}
        hits, total = compute_completion(habit, totals, today=date(2026, 4, 28))
        assert (hits, total) == (3, 4)  # week 16 misses (1 < 2)

    def test_monthly_window_is_three_months(self):
        habit = _make_habit(period="month", target_value=10)
        totals = {(2026, 3): 12, (2026, 2): 8, (2026, 1): 11}
        hits, total = compute_completion(habit, totals, today=date(2026, 4, 1))
        assert (hits, total) == (2, 3)


class TestComputeMetricsIntegration:

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_input(self, async_session):
        result = await compute_metrics(async_session, [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_streak_from_real_rows(self, async_session):
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        today = date(2026, 4, 28)
        # 5-day streak ending yesterday
        for i in range(1, 6):
            await log_habit(async_session, "stretch", today - timedelta(days=i), 1, habit_type="binary")
        # Gap before that
        await log_habit(async_session, "stretch", today - timedelta(days=7), 1, habit_type="binary")
        await async_session.commit()

        result = await compute_metrics(async_session, [habit], today=today)
        assert result[habit.id]["streak"] == 5

    @pytest.mark.asyncio
    async def test_completion_includes_streak_periods(self, async_session):
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        today = date(2026, 4, 28)
        for i in range(1, 4):
            await log_habit(async_session, "stretch", today - timedelta(days=i), 1, habit_type="binary")
        await async_session.commit()

        result = await compute_metrics(async_session, [habit], today=today)
        assert result[habit.id] == {
            "streak": 3,
            "completion_hit": 3,
            "completion_total": 7,
        }
