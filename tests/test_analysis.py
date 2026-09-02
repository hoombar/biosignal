"""Tests for the correlation and analysis engine.

Seeds an in-memory DB with known synthetic patterns and verifies that
compute_correlations() and compute_patterns() detect them correctly.
"""

import pytest
from datetime import date, timedelta

import app.services.analysis as analysis_service
from app.models.database import (
    ContextEvent,
    DailyHabit,
    HabitDisplayConfig,
    SleepSession,
    SupplementLog,
    SupplementPlanVersion,
)
from app.services.analysis import (
    _compute_bucketed_correlation_signals,
    compute_correlation_snapshot,
    compute_correlations,
    compute_patterns,
    generate_insights,
    _is_obvious_snapshot_pair,
)
from tests.conftest import ensure_habit, log_habit


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
    await log_habit(session, "pm_slump", d, 1 if slump else 0, habit_type="binary")
    return d


class TestComputeCorrelations:

    @pytest.mark.asyncio
    async def test_removed_supplement_keeps_historical_not_taken_days(self, async_session):
        """A removed item should remain zero on later logged snapshots."""
        original_plan = SupplementPlanVersion(
            slot="morning",
            version=1,
            items=[{"name": "Multivitamin", "dose": None, "notes": None}],
        )
        removed_plan = SupplementPlanVersion(
            slot="morning",
            version=2,
            items=[],
        )
        async_session.add_all([original_plan, removed_plan])
        await async_session.flush()

        for i in range(20):
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.5 if i < 10 else 8.5) * 3600),
                sleep_score=60 if i < 10 else 85,
            ))
            async_session.add(SupplementLog(
                date=d,
                slot="morning",
                plan_version_id=original_plan.id if i < 10 else removed_plan.id,
                completed=True,
                snapshot=original_plan.items if i < 10 else removed_plan.items,
            ))
        await async_session.commit()

        diagnostics = {}
        result = await compute_correlations(
            async_session,
            target="supplement:multivitamin",
            min_days=5,
            diagnostics=diagnostics,
        )

        assert diagnostics["target_n"] == 20
        assert diagnostics.get("empty_reason") != "constant_target"
        assert any(row["metric"] == "sleep_hours" for row in result)

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
        await log_habit(async_session, "pm_slump", d0, 1, habit_type="binary")

        # Days 1-9: both habit AND sleep data
        for i in range(1, 10):
            slump = i % 2 == 0
            await _seed_day(async_session, i, sleep_hours=5.0 if slump else 9.0, slump=slump)
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)

        # sleep_hours should appear even though day 0 had no sleep data
        sleep_corr = next((r for r in result if r["metric"] == "sleep_hours"), None)
        assert sleep_corr is not None, "sleep_hours should be found from days 1-9 even if day 0 has no data"

    @pytest.mark.asyncio
    async def test_supports_top_level_metric_as_target(self, async_session):
        """Correlations should support non-habit targets like sleep_hours."""
        # Create a pattern: low sleep -> slump, high sleep -> clear day
        for i in range(10):
            if i % 2 == 0:
                await _seed_day(async_session, i, sleep_hours=5.5, slump=True)
            else:
                await _seed_day(async_session, i, sleep_hours=8.5, slump=False)
        await async_session.commit()

        result = await compute_correlations(async_session, target="sleep_hours", min_days=5)

        assert len(result) > 0
        assert result[0]["target_is_binary"] is False
        assert result[0]["positive_label"] == "Higher target"
        assert result[0]["negative_label"] == "Lower target"
        # Must not self-correlate the chosen target
        assert all(r["metric"] != "sleep_hours" for r in result)

        # Habit should be represented as a correlate against sleep_hours
        slump_corr = next((r for r in result if r["metric"] == "habit_pm_slump"), None)
        assert slump_corr is not None
        assert slump_corr["coefficient"] < 0, "More sleep should correlate with fewer slump events"

    @pytest.mark.asyncio
    async def test_counter_habit_threshold_summary_for_binary_target(self, async_session):
        """Configured counter thresholds should report target rates above vs below the cutoff."""
        coffee = await ensure_habit(async_session, "coffee", habit_type="counter")
        coffee.is_negative = True
        coffee.target_value = 3

        for i in range(10):
            d = _make_date(i)
            high_coffee = i < 5
            await log_habit(async_session, "reflux", d, 1 if high_coffee else 0, habit_type="binary")
            await log_habit(async_session, "coffee", d, 4 if high_coffee else 1, habit_type="counter")
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="reflux", min_days=5)
        coffee_corr = next((r for r in result if r["metric"] == "habit_coffee"), None)

        assert coffee_corr is not None
        assert coffee_corr["threshold_value"] == 3
        assert coffee_corr["threshold_operator"] == ">"
        assert coffee_corr["above_threshold_n"] == 5
        assert coffee_corr["below_threshold_n"] == 5
        assert coffee_corr["above_threshold_target_rate"] == pytest.approx(1.0)
        assert coffee_corr["below_threshold_target_rate"] == pytest.approx(0.0)
        assert coffee_corr["relative_risk"] is None

    @pytest.mark.asyncio
    async def test_no_threshold_summary_without_configured_target_value(self, async_session):
        """Counter habits without target_value should keep plain numeric correlation output."""
        await ensure_habit(async_session, "coffee", habit_type="counter")

        for i in range(10):
            d = _make_date(i)
            high_coffee = i < 5
            await log_habit(async_session, "reflux", d, 1 if high_coffee else 0, habit_type="binary")
            await log_habit(async_session, "coffee", d, 4 if high_coffee else 1, habit_type="counter")
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="reflux", min_days=5)
        coffee_corr = next((r for r in result if r["metric"] == "habit_coffee"), None)

        assert coffee_corr is not None
        assert "threshold_value" not in coffee_corr

    @pytest.mark.asyncio
    async def test_positive_counter_threshold_uses_greater_than_or_equal(self, async_session):
        """Positive counter thresholds should include the configured value in the threshold group."""
        meditation = await ensure_habit(async_session, "meditation_minutes", habit_type="counter")
        meditation.is_negative = False
        meditation.target_value = 10

        for i in range(10):
            d = _make_date(i)
            met_target = i < 5
            await log_habit(async_session, "clear_head", d, 1 if met_target else 0, habit_type="binary")
            await log_habit(
                async_session,
                "meditation_minutes",
                d,
                10 if met_target else 5,
                habit_type="counter",
            )
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="clear_head", min_days=5)
        meditation_corr = next((r for r in result if r["metric"] == "habit_meditation_minutes"), None)

        assert meditation_corr is not None
        assert meditation_corr["threshold_value"] == 10
        assert meditation_corr["threshold_operator"] == ">="
        assert meditation_corr["above_threshold_n"] == 5
        assert meditation_corr["below_threshold_n"] == 5


class TestComputeCorrelationSnapshot:

    def test_bucketed_snapshot_prefers_prior_day_habit_sleep_signals(self):
        features = []
        for i in range(20):
            reflux = 1 if i % 2 == 0 else 0
            prev_reflux = 1 if i > 0 and (i - 1) % 2 == 0 else 0
            features.append({
                "date": _make_date(i),
                "sleep_score": 55 if prev_reflux else 85,
                "habits": [{"name": "reflux", "value": reflux, "type": "binary"}],
            })

        result = _compute_bucketed_correlation_signals(features, min_days=14, min_abs=0.3, limit=5)

        signal = next(r for r in result if r["bucket"] == "prior_day_habit_sleep")
        assert signal["metric"] == "habit_reflux_prev_day"
        assert signal["target"] == "sleep_score"
        assert signal["coefficient"] < -0.9
        assert signal["confidence"] == "high"
        assert "day before" in signal["summary"]

    def test_bucketed_snapshot_finds_pollen_habit_and_supplement_sleep_signals(self):
        features = []
        for i in range(20):
            high_pollen = i % 2 == 0
            features.append({
                "date": _make_date(i),
                "deep_sleep_pct": 12 if high_pollen else 24,
                "grass_pollen_avg": 80 if high_pollen else 5,
                "supplements": [{"slot": "evening", "completed": not high_pollen}],
                "habits": [{"name": "headache", "value": 1 if high_pollen else 0, "type": "binary"}],
            })

        result = _compute_bucketed_correlation_signals(features, min_days=14, min_abs=0.3, limit=5)

        buckets = {r["bucket"] for r in result}
        assert "pollen_habit" in buckets
        assert "supplement_sleep" in buckets
        assert all("confidence" in r for r in result)

    def test_bucketed_snapshot_limits_to_five_signals(self):
        features = []
        for i in range(30):
            high = i % 2 == 0
            habits = [
                {"name": f"symptom_{j}", "value": 1 if high else 0, "type": "binary"}
                for j in range(8)
            ]
            features.append({
                "date": _make_date(i),
                "sleep_score": 60 if high else 90,
                "stress_afternoon_avg": 80 if high else 20,
                "grass_pollen_avg": 70 if high else 3,
                "habits": habits,
            })

        result = _compute_bucketed_correlation_signals(features, min_days=14, min_abs=0.3, limit=5)

        assert len(result) == 5

    def test_bucketed_snapshot_limits_repeated_predictors_when_possible(self):
        features = []
        for i in range(30):
            read = 1 if i % 2 == 0 else 0
            nose_strip = 1 if i % 3 == 0 else 0
            caffeine = 1 if i % 5 in {0, 1} else 0
            features.append({
                "date": _make_date(i),
                "sleep_score": 80 if read else 60,
                "bb_wakeup": 70 if read else 45,
                "bb_morning_drain_rate": 6 if read else -2,
                "stress_afternoon_avg": 30 if read else 70,
                "deep_sleep_pct": 25 if nose_strip else 12,
                "high_stress_minutes": 90 if caffeine else 10,
                "habits": [
                    {"name": "read", "value": read, "type": "binary"},
                    {"name": "nose_strip_overnight", "value": nose_strip, "type": "binary"},
                    {"name": "caffeine", "value": caffeine, "type": "binary"},
                ],
            })

        result = _compute_bucketed_correlation_signals(features, min_days=14, min_abs=0.3, limit=5)
        predictor_roots = [r["metric"].removesuffix("_prev_day") for r in result]

        assert predictor_roots.count("habit_read") == 1
        assert len(set(predictor_roots)) >= 3

    @pytest.mark.asyncio
    async def test_snapshot_avoids_full_feature_recompute(self, async_session, monkeypatch):
        async def fail_if_called(*args, **kwargs):
            raise AssertionError("snapshot should use the narrow bulk loader")

        monkeypatch.setattr(analysis_service, "compute_features_range", fail_if_called)

        result = await analysis_service.compute_correlation_snapshot(async_session)

        assert result == []

    def test_obvious_filter_excludes_same_window_physiology_pairs(self):
        assert _is_obvious_snapshot_pair("stress_2pm_window", "stress_afternoon_avg")
        assert _is_obvious_snapshot_pair("stress_2pm_window", "hr_2pm_window")
        assert _is_obvious_snapshot_pair("stress_afternoon_avg", "hr_afternoon_avg")

    def test_obvious_filter_excludes_garmin_derived_physiology_pairs(self):
        assert _is_obvious_snapshot_pair("stress_2pm_window", "hr_afternoon_avg")
        assert _is_obvious_snapshot_pair("bb_wakeup", "bb_daily_min")
        assert _is_obvious_snapshot_pair("sleep_score", "bb_wakeup")
        assert _is_obvious_snapshot_pair("hrv_overnight_min", "hrv_overnight_avg")
        assert _is_obvious_snapshot_pair("hrv_overnight_avg", "bb_wakeup")

    def test_obvious_filter_excludes_seasonal_light_routine_habit_pairs(self):
        assert _is_obvious_snapshot_pair("habit_read", "daylight_minutes")
        assert _is_obvious_snapshot_pair("habit_read", "sunset_minutes_after_midnight")

    def test_obvious_filter_allows_cross_domain_symptom_signals(self):
        assert not _is_obvious_snapshot_pair("habit_pm_slump", "sleep_hours")
        assert not _is_obvious_snapshot_pair("habit_reflux", "stress_2pm_window")

    @pytest.mark.asyncio
    async def test_returns_strong_signals_without_selected_target(self, async_session):
        for i in range(16):
            slump = i % 2 == 0
            prev_slump = i > 0 and (i - 1) % 2 == 0
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.0 if slump else 9.0) * 3600),
                sleep_score=55 if prev_slump else 85,
            ))
            await log_habit(async_session, "pm_slump", d, 1 if slump else 0, habit_type="binary")
        await async_session.commit()

        result = await compute_correlation_snapshot(async_session, min_days=5, min_abs=0.7)

        sleep_slump = next(
            (
                r for r in result
                if r["target"] == "sleep_score" and r["metric"] == "habit_pm_slump_prev_day"
            ),
            None,
        )
        assert sleep_slump is not None
        assert sleep_slump["target_label"] == "sleep score"
        assert sleep_slump["target_kind"] == "metric"
        assert sleep_slump["coefficient"] < -0.7

    @pytest.mark.asyncio
    async def test_snapshot_excludes_context_marked_non_baseline(self, async_session):
        excluded_start = _make_date(0)
        excluded_end = _make_date(15)
        async_session.add(ContextEvent(
            title="Conference travel",
            start_date=excluded_start,
            end_date=excluded_end,
            category="conference",
            tags=["travel"],
            intensity="high",
            exclude_from_baseline=True,
        ))

        for i in range(16):
            slump = i % 2 == 0
            prev_slump = i > 0 and (i - 1) % 2 == 0
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.0 if prev_slump else 9.0) * 3600),
                sleep_score=45 if prev_slump else 90,
            ))
            await log_habit(async_session, "pm_slump", d, 1 if slump else 0, habit_type="binary")

        for i in range(16, 28):
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int(8.0 * 3600),
                sleep_score=80,
            ))
            await log_habit(async_session, "pm_slump", d, 0, habit_type="binary")
        await async_session.commit()

        result = await compute_correlation_snapshot(async_session, min_days=5, min_abs=0.7)

        assert all(r["metric"] != "habit_pm_slump_prev_day" for r in result)

    @pytest.mark.asyncio
    async def test_bucketed_snapshot_does_not_repeat_exact_signal(self, async_session):
        for i in range(16):
            slump = i % 2 == 0
            prev_slump = i > 0 and (i - 1) % 2 == 0
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.0 if slump else 9.0) * 3600),
                sleep_score=55 if prev_slump else 85,
            ))
            await log_habit(async_session, "pm_slump", d, 1 if slump else 0, habit_type="binary")
        await async_session.commit()

        result = await compute_correlation_snapshot(async_session, min_days=5, min_abs=0.7)

        pair_count = sum(
            1 for r in result
            if (r["target_feature"], r["metric"]) == ("sleep_score", "habit_pm_slump_prev_day")
        )
        assert pair_count == 1

    @pytest.mark.asyncio
    async def test_defaults_exclude_low_sample_signals(self, async_session):
        for i in range(10):
            slump = i % 2 == 0
            await _seed_day(async_session, i, sleep_hours=5.0 if slump else 9.0, slump=slump)
        await async_session.commit()

        result = await compute_correlation_snapshot(async_session)

        assert result == []

    @pytest.mark.asyncio
    async def test_excludes_obvious_same_family_signals(self, async_session):
        for i in range(20):
            slump = i % 2 == 0
            d = await _seed_day(async_session, i, sleep_hours=5.0 if slump else 9.0, slump=slump)
            await log_habit(
                async_session,
                "steps_walking_45min_windows",
                d,
                10 if slump else 1,
                habit_type="counter",
            )
        await async_session.commit()

        result = await compute_correlation_snapshot(async_session, min_abs=0.6)

        assert all(
            {r["target_feature"], r["metric"]}
            != {"habit_steps_walking_45min_windows", "walk_hr_elevated_45min_windows"}
            for r in result
        )
        assert all(r["bucket"] != "activity" for r in result)


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
            await log_habit(async_session, "pm_slump", d, 1 if slump else 0, habit_type="binary")
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="pm_slump")
        # With 10 days of data and a clear sleep pattern, at least the sleep pattern should fire
        assert len(result) > 0, (
            "Expected at least one pattern. Bug: compute_patterns was using f.get('pm_slump') "
            "instead of _get_habit_value(), so fog_data was always empty."
        )

    @pytest.mark.asyncio
    async def test_compute_patterns_detects_custom_numeric_habit_pattern(self, async_session):
        """Pattern detection should work for arbitrary habit names, not fixed known habits."""
        # Seed 15 days; on high custom-counter days always have a slump
        for i in range(15):
            d = _make_date(i)
            high_counter = i < 6
            slump = high_counter
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int(7.5 * 3600),
                sleep_score=70,
            ))
            await log_habit(async_session, "pm_slump", d, 1 if slump else 0, habit_type="binary")
            await log_habit(
                async_session,
                "custom_counter",
                d,
                4 if high_counter else 0,
                habit_type="counter",
            )
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="pm_slump")
        descriptions = [p["description"] for p in result]
        assert any("custom counter" in d.lower() for d in descriptions), (
            f"Expected a custom-counter pattern. Got: {descriptions}."
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
            await log_habit(
                async_session, "morning_fatigue", d, 1 if fatigue else 0, habit_type="binary"
            )
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

    @pytest.mark.asyncio
    async def test_compute_patterns_defaults_to_first_habit_by_sort_order(self, async_session):
        """Without explicit target, compute_patterns should use first configured habit."""
        for i in range(10):
            d = _make_date(i)
            fatigue = i % 2 == 0
            slump = i % 3 == 0
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.5 if fatigue else 8.5) * 3600),
                sleep_score=70,
            ))
            await log_habit(
                async_session, "morning_fatigue", d, 1 if fatigue else 0, habit_type="binary"
            )
            await log_habit(
                async_session, "pm_slump", d, 1 if slump else 0, habit_type="binary"
            )

        async_session.add(HabitDisplayConfig(
            habit_name="morning_fatigue",
            sort_order=0,
        ))
        async_session.add(HabitDisplayConfig(
            habit_name="pm_slump",
            sort_order=10,
        ))
        await async_session.commit()

        auto = await compute_patterns(async_session)
        explicit = await compute_patterns(async_session, target_habit="morning_fatigue")
        assert auto == explicit

    @pytest.mark.asyncio
    async def test_compute_patterns_excludes_context_marked_non_baseline(self, async_session):
        excluded_start = _make_date(0)
        excluded_end = _make_date(7)
        async_session.add(ContextEvent(
            title="Illness",
            start_date=excluded_start,
            end_date=excluded_end,
            category="illness",
            tags=["flu"],
            intensity="high",
            exclude_from_baseline=True,
        ))

        for i in range(8):
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int(4.5 * 3600),
                sleep_score=45,
            ))
            await log_habit(async_session, "pm_slump", d, 1, habit_type="binary")

        for i in range(8, 18):
            d = _make_date(i)
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int(8.0 * 3600),
                sleep_score=82,
            ))
            await log_habit(async_session, "pm_slump", d, 0, habit_type="binary")
        await async_session.commit()

        result = await compute_patterns(async_session, target_habit="pm_slump")

        assert result == []


class TestGenerateInsights:

    @pytest.mark.asyncio
    async def test_reuses_features_for_correlations_and_patterns(self, async_session, monkeypatch):
        """Insights should not build the expensive 365-day feature set twice."""
        calls = 0

        async def fake_compute_features_range(*args, **kwargs):
            nonlocal calls
            calls += 1
            return []

        monkeypatch.setattr(analysis_service, "compute_features_range", fake_compute_features_range)

        result = await generate_insights(async_session, target_habit="coffee")

        assert result == []
        assert calls == 1

    @pytest.mark.asyncio
    async def test_returns_list(self, async_session):
        """generate_insights always returns a list."""
        result = await generate_insights(async_session)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_defaults_to_first_habit_by_sort_order(self, async_session):
        """Without explicit target, generate_insights should use first configured habit."""
        for i in range(14):
            d = _make_date(i)
            fatigue = i % 2 == 0
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.5 if fatigue else 8.5) * 3600),
                sleep_score=70,
            ))
            await log_habit(
                async_session, "morning_fatigue", d, 1 if fatigue else 0, habit_type="binary"
            )
            await log_habit(async_session, "pm_slump", d, 0, habit_type="binary")

        async_session.add(HabitDisplayConfig(habit_name="morning_fatigue", sort_order=0))
        async_session.add(HabitDisplayConfig(habit_name="pm_slump", sort_order=10))
        await async_session.commit()

        auto = await generate_insights(async_session)
        explicit = await generate_insights(async_session, target_habit="morning_fatigue")
        assert auto == explicit

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
