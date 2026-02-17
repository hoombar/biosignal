"""Tests for computed features engine.

Uses an in-memory SQLite database (from conftest.py async_session fixture).
Timestamps are stored as naive UTC datetimes, matching how parsers store them
after stripping tzinfo from epoch ms conversions.
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.models.database import (
    SleepSession,
    HeartRateSample,
    BodyBatterySample,
    StressSample,
    HrvSample,
    StepsSample,
    Activity,
    DailyHabit,
)
from app.services.features import (
    compute_sleep_features,
    compute_hrv_features,
    compute_heart_rate_features,
    compute_body_battery_features,
    compute_stress_features,
    compute_activity_features,
    compute_habit_features,
    compute_daily_features,
)

# Test date and timezone used throughout
TEST_DATE = date(2025, 1, 28)
TZ = ZoneInfo("Europe/London")  # UTC+0 in January, so UTC == local


def naive_utc(dt: datetime) -> datetime:
    """Strip tzinfo, keeping the UTC value, for storage in SQLite."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def utc_dt(year, month, day, hour, minute=0, second=0) -> datetime:
    """Create a naive UTC datetime (as stored by parsers)."""
    return datetime(year, month, day, hour, minute, second)


class TestSleepFeatures:

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_sleep(self, async_session):
        result = await compute_sleep_features(async_session, TEST_DATE, TZ)
        assert result == {}

    @pytest.mark.asyncio
    async def test_computes_sleep_hours(self, async_session):
        sleep = SleepSession(
            date=TEST_DATE,
            sleep_start=utc_dt(2025, 1, 27, 23, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            deep_sleep_seconds=3600,
            rem_sleep_seconds=5400,
            sleep_score=78,
        )
        async_session.add(sleep)
        await async_session.commit()

        result = await compute_sleep_features(async_session, TEST_DATE, TZ)

        assert result["sleep_hours"] == pytest.approx(7.0)
        assert result["sleep_score"] == 78
        assert result["deep_sleep_pct"] == pytest.approx(100 / 7, rel=0.01)
        assert result["rem_sleep_pct"] == pytest.approx(5400 / (7 * 3600) * 100, rel=0.01)

    @pytest.mark.asyncio
    async def test_computes_sleep_efficiency(self, async_session):
        # 7h sleep in 8h time in bed = 87.5% efficiency
        sleep = SleepSession(
            date=TEST_DATE,
            sleep_start=utc_dt(2025, 1, 27, 23, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        )
        async_session.add(sleep)
        await async_session.commit()

        result = await compute_sleep_features(async_session, TEST_DATE, TZ)
        assert result["sleep_efficiency"] == pytest.approx(87.5, rel=0.01)

    @pytest.mark.asyncio
    async def test_handles_zero_sleep_seconds(self, async_session):
        sleep = SleepSession(date=TEST_DATE, total_sleep_seconds=0)
        async_session.add(sleep)
        await async_session.commit()

        result = await compute_sleep_features(async_session, TEST_DATE, TZ)
        assert result == {}


class TestHrvFeatures:

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sleep(self, async_session):
        result = await compute_hrv_features(async_session, TEST_DATE, TZ)
        assert result == {}

    @pytest.mark.asyncio
    async def test_computes_overnight_avg_and_min(self, async_session):
        sleep = SleepSession(
            date=TEST_DATE,
            sleep_start=utc_dt(2025, 1, 28, 0, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        )
        async_session.add(sleep)

        for hour, val in [(1, 45.0), (2, 50.0), (3, 55.0), (4, 48.0), (5, 52.0)]:
            async_session.add(HrvSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                hrv_value=val,
                reading_type="overnight",
            ))
        await async_session.commit()

        result = await compute_hrv_features(async_session, TEST_DATE, TZ)

        assert result["hrv_overnight_avg"] == pytest.approx(50.0)
        assert result["hrv_overnight_min"] == pytest.approx(45.0)
        assert "hrv_rmssd_slope" in result

    @pytest.mark.asyncio
    async def test_no_slope_with_fewer_than_3_samples(self, async_session):
        sleep = SleepSession(
            date=TEST_DATE,
            sleep_start=utc_dt(2025, 1, 28, 0, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        )
        async_session.add(sleep)
        for hour, val in [(1, 45.0), (3, 55.0)]:
            async_session.add(HrvSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                hrv_value=val,
                reading_type="overnight",
            ))
        await async_session.commit()

        result = await compute_hrv_features(async_session, TEST_DATE, TZ)
        assert "hrv_rmssd_slope" not in result


class TestHeartRateFeatures:

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_data(self, async_session):
        result = await compute_heart_rate_features(async_session, TEST_DATE, TZ)
        assert result == {}

    @pytest.mark.asyncio
    async def test_computes_morning_and_afternoon_avg(self, async_session):
        # Morning samples: 7am, 8am, 9am (UTC = local in Jan)
        for hour, hr in [(7, 60), (8, 65), (9, 62)]:
            async_session.add(HeartRateSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                heart_rate=hr,
            ))
        # Afternoon samples: 1pm, 2pm, 3pm
        for hour, hr in [(13, 75), (14, 72), (15, 78)]:
            async_session.add(HeartRateSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                heart_rate=hr,
            ))
        await async_session.commit()

        result = await compute_heart_rate_features(async_session, TEST_DATE, TZ)

        assert result["hr_morning_avg"] == pytest.approx((60 + 65 + 62) / 3, rel=0.01)
        assert result["hr_afternoon_avg"] == pytest.approx((75 + 72 + 78) / 3, rel=0.01)
        assert result["hr_2pm_window"] == pytest.approx((75 + 72 + 78) / 3, rel=0.01)
        assert result["hr_max_24h"] == 78

    @pytest.mark.asyncio
    async def test_ignores_zero_hr_values(self, async_session):
        async_session.add(HeartRateSample(
            timestamp=utc_dt(2025, 1, 28, 10), heart_rate=0
        ))
        async_session.add(HeartRateSample(
            timestamp=utc_dt(2025, 1, 28, 11), heart_rate=65
        ))
        await async_session.commit()

        result = await compute_heart_rate_features(async_session, TEST_DATE, TZ)
        assert result["hr_morning_avg"] == pytest.approx(65.0)


class TestBodyBatteryFeatures:

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_data(self, async_session):
        result = await compute_body_battery_features(async_session, TEST_DATE, TZ)
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_bb_samples_with_times(self, async_session):
        # Add samples at various times (UTC = local in Jan for Europe/London)
        for hour, bb in [(7, 80), (9, 72), (12, 60), (14, 50), (18, 35)]:
            async_session.add(BodyBatterySample(
                timestamp=utc_dt(2025, 1, 28, hour),
                body_battery=bb,
            ))
        await async_session.commit()

        result = await compute_body_battery_features(async_session, TEST_DATE, TZ)

        # Should return all samples with their actual times
        assert "bb_samples" in result
        assert len(result["bb_samples"]) == 5
        # Samples should have time and value
        assert result["bb_samples"][0]["value"] == 80
        assert "AM" in result["bb_samples"][0]["time"] or "PM" in result["bb_samples"][0]["time"]
        assert result["bb_daily_min"] == 35

    @pytest.mark.asyncio
    async def test_computes_drain_rates(self, async_session):
        # 12pm BB = 60, 6pm BB = 36 → drain rate = (36-60)/6 = -4/hr
        for hour, bb in [(9, 72), (12, 60), (14, 50), (18, 36)]:
            async_session.add(BodyBatterySample(
                timestamp=utc_dt(2025, 1, 28, hour),
                body_battery=bb,
            ))
        # Sleep session for wakeup
        sleep = SleepSession(
            date=TEST_DATE,
            sleep_start=utc_dt(2025, 1, 27, 23, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        )
        async_session.add(sleep)
        await async_session.commit()

        result = await compute_body_battery_features(async_session, TEST_DATE, TZ)

        assert result["bb_afternoon_drain_rate"] == pytest.approx((36 - 60) / 6, rel=0.01)


class TestStressFeatures:

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_data(self, async_session):
        result = await compute_stress_features(async_session, TEST_DATE, TZ)
        assert result == {}

    @pytest.mark.asyncio
    async def test_excludes_rest_unmeasured_sentinels(self, async_session):
        # Only -1/-2 values — should return empty dict
        for hour in [1, 2, 3]:
            async_session.add(StressSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                stress_level=-1,
            ))
        await async_session.commit()

        result = await compute_stress_features(async_session, TEST_DATE, TZ)
        assert result == {}

    @pytest.mark.asyncio
    async def test_computes_morning_and_afternoon_avg(self, async_session):
        # Morning samples (7am-11am)
        for hour, stress in [(7, 20), (8, 25), (9, 30), (10, 22)]:
            async_session.add(StressSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                stress_level=stress,
            ))
        # Afternoon samples (1pm-5pm)
        for hour, stress in [(13, 45), (14, 50), (15, 65), (16, 55)]:
            async_session.add(StressSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                stress_level=stress,
            ))
        await async_session.commit()

        result = await compute_stress_features(async_session, TEST_DATE, TZ)

        assert result["stress_morning_avg"] == pytest.approx((20 + 25 + 30 + 22) / 4, rel=0.01)
        assert result["stress_afternoon_avg"] == pytest.approx((45 + 50 + 65 + 55) / 4, rel=0.01)
        assert result["stress_peak"] == 65
        # 65 > 60, so 1 high-stress sample × 15 min
        assert result["high_stress_minutes"] == 15

    @pytest.mark.asyncio
    async def test_stress_2pm_window(self, async_session):
        for hour, stress in [(13, 40), (14, 55), (15, 60), (17, 30)]:
            async_session.add(StressSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                stress_level=stress,
            ))
        await async_session.commit()

        result = await compute_stress_features(async_session, TEST_DATE, TZ)
        # 2pm window = 1pm-4pm → 13h, 14h, 15h
        assert result["stress_2pm_window"] == pytest.approx((40 + 55 + 60) / 3, rel=0.01)


class TestActivityFeatures:

    @pytest.mark.asyncio
    async def test_had_training_false_when_no_activities(self, async_session):
        result = await compute_activity_features(async_session, TEST_DATE, TZ)
        assert result["had_training"] is False

    @pytest.mark.asyncio
    async def test_computes_steps(self, async_session):
        for hour, steps in [(8, 500), (9, 800), (13, 1200), (15, 600)]:
            async_session.add(StepsSample(
                timestamp=utc_dt(2025, 1, 28, hour),
                steps=steps,
                duration_seconds=3600,
            ))
        await async_session.commit()

        result = await compute_activity_features(async_session, TEST_DATE, TZ)

        assert result["steps_total"] == 500 + 800 + 1200 + 600
        assert result["steps_morning"] == 500 + 800  # before noon

    @pytest.mark.asyncio
    async def test_had_training_true_with_activity(self, async_session):
        async_session.add(Activity(
            garmin_activity_id="12345",
            activity_type="running",
            start_time=utc_dt(2025, 1, 28, 7, 0),
            end_time=utc_dt(2025, 1, 28, 8, 0),
            duration_seconds=3600,
            avg_hr=145,
        ))
        await async_session.commit()

        result = await compute_activity_features(async_session, TEST_DATE, TZ)

        assert result["had_training"] is True
        assert result["training_type"] == "running"
        assert result["training_duration_min"] == pytest.approx(60.0)
        assert result["training_avg_hr"] == 145
        # avg_hr 145 / max_hr 190 = 76.3% → medium
        assert result["training_intensity"] == "medium"

    @pytest.mark.asyncio
    async def test_training_intensity_high(self, async_session):
        async_session.add(Activity(
            garmin_activity_id="99999",
            activity_type="brazilian_jiu_jitsu",
            start_time=utc_dt(2025, 1, 28, 19, 0),
            end_time=utc_dt(2025, 1, 28, 20, 30),
            duration_seconds=5400,
            avg_hr=170,  # 170/190 = 89.5% → high
        ))
        await async_session.commit()

        result = await compute_activity_features(async_session, TEST_DATE, TZ)
        assert result["training_intensity"] == "high"


class TestHabitFeatures:

    @pytest.mark.asyncio
    async def test_returns_empty_habits_list_when_none(self, async_session):
        result = await compute_habit_features(async_session, TEST_DATE)
        assert result == {"habits": []}

    @pytest.mark.asyncio
    async def test_parses_boolean_habit(self, async_session):
        async_session.add(DailyHabit(
            date=TEST_DATE,
            habit_name="pm_energy_slump",
            habit_value="true",
            habit_type="boolean",
        ))
        await async_session.commit()

        result = await compute_habit_features(async_session, TEST_DATE)

        assert len(result["habits"]) == 1
        habit = result["habits"][0]
        assert habit["name"] == "pm_energy_slump"
        assert habit["value"] == 1

    @pytest.mark.asyncio
    async def test_parses_counter_habit(self, async_session):
        async_session.add(DailyHabit(
            date=TEST_DATE,
            habit_name="coffee",
            habit_value="3",
            habit_type="counter",
        ))
        await async_session.commit()

        result = await compute_habit_features(async_session, TEST_DATE)

        habit = result["habits"][0]
        assert habit["name"] == "coffee"
        assert habit["value"] == 3


class TestComputeDailyFeatures:

    @pytest.mark.asyncio
    async def test_returns_date_even_with_no_data(self, async_session):
        result = await compute_daily_features(async_session, TEST_DATE)
        assert result["date"] == TEST_DATE.isoformat()

    @pytest.mark.asyncio
    async def test_aggregates_all_feature_categories(self, async_session):
        # Add minimal data for each category
        async_session.add(SleepSession(
            date=TEST_DATE,
            sleep_start=utc_dt(2025, 1, 28, 0, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=75,
        ))
        async_session.add(HeartRateSample(
            timestamp=utc_dt(2025, 1, 28, 8), heart_rate=62
        ))
        async_session.add(StressSample(
            timestamp=utc_dt(2025, 1, 28, 9), stress_level=25
        ))
        await async_session.commit()

        result = await compute_daily_features(async_session, TEST_DATE)

        assert result["date"] == TEST_DATE.isoformat()
        assert result["sleep_hours"] == pytest.approx(7.0)
        assert result["sleep_score"] == 75
        assert "hr_morning_avg" in result
        assert "stress_morning_avg" in result
        assert result["had_training"] is False
        assert "habits" in result
