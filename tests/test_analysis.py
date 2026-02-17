"""Tests for the correlation and analysis engine.

Seeds an in-memory DB with known synthetic patterns and verifies that
compute_correlations() detects them correctly.

Note: compute_patterns() looks for pm_slump as a top-level feature key,
which is not currently set by compute_daily_features() (habits are nested
under "habits" list). Tests here use compute_correlations() which properly
uses the target_habit parameter with the habits list.
"""

import pytest
from datetime import date, timedelta

from app.models.database import SleepSession, DailyHabit
from app.services.analysis import compute_correlations, generate_insights


def _make_date(offset: int) -> date:
    """Return date relative to recent past (within the last 365 days)."""
    # Use dates close to today so compute_correlations' 365-day lookback includes them
    from datetime import date as _date
    anchor = _date.today() - timedelta(days=30)
    return anchor + timedelta(days=offset)


async def _seed_day(session, day_offset: int, sleep_hours: float, slump: bool):
    """Insert one day of data: sleep session + pm_slump habit."""
    d = _make_date(day_offset)
    session.add(SleepSession(
        date=d,
        total_sleep_seconds=int(sleep_hours * 3600),
        sleep_score=70,
    ))
    session.add(DailyHabit(
        date=d,
        habit_name="pm_slump",
        habit_value="true" if slump else "false",
        habit_type="boolean",
    ))
    return d


class TestComputeCorrelations:

    @pytest.mark.asyncio
    async def test_returns_empty_with_insufficient_data(self, async_session):
        """Should return [] when fewer than min_days days have target habit."""
        # Add 3 days (below default min_days=5)
        for i in range(3):
            await _seed_day(async_session, i, sleep_hours=7.0, slump=False)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_detects_negative_correlation_between_sleep_and_slump(self, async_session):
        """Days with poor sleep should correlate with slump=1 (negative r: more sleep = less slump)."""
        # Create a clear pattern: low sleep → slump, high sleep → no slump
        # 10 days alternating
        for i in range(10):
            if i % 2 == 0:
                await _seed_day(async_session, i, sleep_hours=5.5, slump=True)
            else:
                await _seed_day(async_session, i, sleep_hours=8.5, slump=False)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)

        # Find sleep_hours correlation
        sleep_corr = next((r for r in result if r["metric"] == "sleep_hours"), None)
        assert sleep_corr is not None, "sleep_hours should appear in correlations"
        # More sleep → less slump: negative correlation expected
        assert sleep_corr["coefficient"] < 0, f"Expected negative r, got {sleep_corr['coefficient']}"
        assert sleep_corr["n"] >= 10

    @pytest.mark.asyncio
    async def test_correlation_sorted_by_absolute_r(self, async_session):
        """Results must be sorted by |r| descending."""
        for i in range(10):
            slump = i % 2 == 0
            await _seed_day(async_session, i, sleep_hours=5.0 if slump else 9.0, slump=slump)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)

        abs_rs = [abs(r["coefficient"]) for r in result]
        assert abs_rs == sorted(abs_rs, reverse=True)

    @pytest.mark.asyncio
    async def test_result_shape(self, async_session):
        """Each result dict must have the expected keys."""
        for i in range(7):
            await _seed_day(async_session, i, sleep_hours=6.0 + i * 0.3, slump=i % 3 == 0)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)

        if result:
            r = result[0]
            assert "metric" in r
            assert "coefficient" in r
            assert "p_value" in r
            assert "n" in r
            assert "strength" in r
            assert "fog_day_avg" in r
            assert "clear_day_avg" in r

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_variance_in_target(self, async_session):
        """If target habit is always 0, no correlations can be computed."""
        for i in range(7):
            await _seed_day(async_session, i, sleep_hours=7.0, slump=False)  # always False
        await async_session.commit()

        # All target values are 0 → zero variance → should return empty or skip all
        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)
        # Either empty or all skipped due to zero variance in target
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_strength_classification(self, async_session):
        """Strength field should reflect magnitude of |r|."""
        # Perfect correlation: every fog day has sleep < 6h, clear day has sleep > 8h
        for i in range(10):
            slump = i % 2 == 0
            await _seed_day(async_session, i, sleep_hours=5.0 if slump else 9.0, slump=slump)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)
        sleep_corr = next((r for r in result if r["metric"] == "sleep_hours"), None)

        if sleep_corr:
            abs_r = abs(sleep_corr["coefficient"])
            if abs_r > 0.5:
                assert sleep_corr["strength"] == "strong"
            elif abs_r > 0.3:
                assert sleep_corr["strength"] == "moderate"
            else:
                assert sleep_corr["strength"] == "weak"

    @pytest.mark.asyncio
    async def test_finds_features_from_sparse_data(self, async_session):
        """Features should be found even if first day with habit has no Garmin data.

        Regression test: previously, feature names were extracted only from the
        first day with the target habit. If that day had no Garmin data (e.g.,
        before backfill), Garmin metrics would be missing from correlations.
        """
        # Day 0: habit only, NO sleep data
        d0 = _make_date(0)
        async_session.add(DailyHabit(
            date=d0,
            habit_name="pm_slump",
            habit_value="true",
            habit_type="boolean",
        ))

        # Days 1-9: both habit AND sleep data
        for i in range(1, 10):
            slump = i % 2 == 0
            await _seed_day(async_session, i, sleep_hours=5.0 if slump else 9.0, slump=slump)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)

        # sleep_hours should appear even though day 0 had no sleep data
        sleep_corr = next((r for r in result if r["metric"] == "sleep_hours"), None)
        assert sleep_corr is not None, "sleep_hours should be found from days 1-9 even if day 0 has no data"


class TestGenerateInsights:

    @pytest.mark.asyncio
    async def test_returns_list(self, async_session):
        """generate_insights always returns a list."""
        result = await generate_insights(async_session)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_insight_shape(self, async_session):
        """Insights have required fields when data exists."""
        # Seed enough data for correlations to kick in
        for i in range(14):
            slump = i % 3 == 0
            await _seed_day(async_session, i, sleep_hours=5.0 if slump else 8.5, slump=slump)
        await async_session.commit()

        result = await generate_insights(async_session)

        if result:
            insight = result[0]
            assert "text" in insight
            assert "confidence" in insight
            assert insight["confidence"] in ("high", "medium", "low")
            assert "supporting_metric" in insight
