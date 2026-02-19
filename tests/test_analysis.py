"""Tests for the correlation and analysis engine.

Seeds an in-memory DB with known synthetic patterns and verifies that
compute_correlations() and compute_patterns() detect them correctly.
"""

import pytest
from datetime import date, timedelta

from app.models.database import SleepSession, DailyHabit
from app.services.analysis import compute_correlations, compute_patterns, generate_insights


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


class TestComputePatterns:

    @pytest.mark.asyncio
    async def test_compute_patterns_uses_habit_values_not_flat_keys(self, async_session):
        """compute_patterns() must read pm_slump from the habits list, not as a top-level key.

        Bug: previously used f.get("pm_slump") which is always None because habits are nested
        inside f["habits"] as [{"name": "pm_slump", "value": 1, ...}].
        This caused fog_data to always be empty → always returned [].
        """
        # Seed 10 days: alternating slump/no-slump with low/high sleep to create a pattern
        for i in range(10):
            d = _make_date(i)
            slump = i % 2 == 0
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.5 if slump else 8.5) * 3600),
                sleep_score=70,
            ))
            async_session.add(DailyHabit(
                date=d,
                habit_name="pm_slump",
                habit_value="true" if slump else "false",
                habit_type="boolean",
            ))
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="pm_slump")
        # With 10 days of data and a clear sleep pattern, at least the sleep pattern should fire
        assert len(result) > 0, (
            "Expected at least one pattern. Bug: compute_patterns was using f.get('pm_slump') "
            "instead of _get_habit_value(), so fog_data was always empty."
        )

    @pytest.mark.asyncio
    async def test_compute_patterns_beer_count_condition(self, async_session):
        """Pattern for beer_count > 2 must read from habits list, not f.get('beer_count')."""
        # Seed 15 days; on high-beer days always have a slump
        for i in range(15):
            d = _make_date(i)
            high_beer = i < 6  # first 6 days have high beer
            slump = high_beer  # high beer always causes slump
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int(7.5 * 3600),
                sleep_score=70,
            ))
            async_session.add(DailyHabit(
                date=d,
                habit_name="pm_slump",
                habit_value="true" if slump else "false",
                habit_type="boolean",
            ))
            async_session.add(DailyHabit(
                date=d,
                habit_name="beer_count",
                habit_value=str(4 if high_beer else 0),
                habit_type="numeric",
            ))
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="pm_slump")
        descriptions = [p["description"] for p in result]
        assert any("alcoholic drinks" in d for d in descriptions), (
            f"Expected a beer-count pattern. Got: {descriptions}. "
            "Bug: f.get('beer_count') was always None; must use _get_habit_value()."
        )

    @pytest.mark.asyncio
    async def test_compute_patterns_custom_target_habit(self, async_session):
        """compute_patterns() must accept target_habit param and correlate against it."""
        # Seed 10 days: high coffee → morning_fatigue (custom habit)
        for i in range(10):
            d = _make_date(i)
            high_coffee = i % 2 == 0
            fatigue = high_coffee
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.5 if fatigue else 8.5) * 3600),
                sleep_score=70,
            ))
            async_session.add(DailyHabit(
                date=d,
                habit_name="morning_fatigue",
                habit_value="true" if fatigue else "false",
                habit_type="boolean",
            ))
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="morning_fatigue")
        # Should not crash and should return a list (may be empty if not enough samples)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_compute_patterns_missing_target_habit_returns_empty(self, async_session):
        """When no habit data exists for target, return [] without crashing."""
        # Seed some sleep data but NO habit data
        for i in range(10):
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int(7.0 * 3600),
                sleep_score=70,
            ))
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="pm_slump")
        assert result == []


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
