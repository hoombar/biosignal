"""Tests for ORM model constraints.

Verifies UniqueConstraints and unique=True columns raise IntegrityError
on duplicate inserts, ensuring data integrity is enforced at the DB level.
"""

import pytest
from datetime import date, datetime
from sqlalchemy.exc import IntegrityError

from app.models.database import (
    RawGarminResponse,
    RawHabitSyncResponse,
    HeartRateSample,
    BodyBatterySample,
    StressSample,
    HrvSample,
    Spo2Sample,
    SleepSession,
    Activity,
    DailyHabit,
)


def utc_dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute)


class TestRawGarminResponseConstraints:

    @pytest.mark.asyncio
    async def test_duplicate_date_endpoint_raises(self, async_session):
        """(date, endpoint) must be unique."""
        async_session.add(RawGarminResponse(
            date=date(2025, 1, 28),
            endpoint="sleep",
            response={"data": 1},
        ))
        await async_session.commit()

        async_session.add(RawGarminResponse(
            date=date(2025, 1, 28),
            endpoint="sleep",
            response={"data": 2},
        ))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_same_date_different_endpoint_allowed(self, async_session):
        """Same date but different endpoint should not conflict."""
        async_session.add(RawGarminResponse(
            date=date(2025, 1, 28),
            endpoint="sleep",
            response={"data": 1},
        ))
        async_session.add(RawGarminResponse(
            date=date(2025, 1, 28),
            endpoint="heart_rate",
            response={"data": 2},
        ))
        await async_session.commit()  # should not raise


class TestRawHabitSyncConstraints:

    @pytest.mark.asyncio
    async def test_duplicate_date_raises(self, async_session):
        """date must be unique in raw_habitsync_responses."""
        async_session.add(RawHabitSyncResponse(
            date=date(2025, 1, 28),
            response={"habits": []},
        ))
        await async_session.commit()

        async_session.add(RawHabitSyncResponse(
            date=date(2025, 1, 28),
            response={"habits": ["x"]},
        ))
        with pytest.raises(IntegrityError):
            await async_session.commit()


class TestTimestampUniqueness:

    @pytest.mark.asyncio
    async def test_heart_rate_duplicate_timestamp_raises(self, async_session):
        """HeartRateSample.timestamp must be unique."""
        ts = utc_dt(2025, 1, 28, 8, 0)
        async_session.add(HeartRateSample(timestamp=ts, heart_rate=65))
        await async_session.commit()

        async_session.add(HeartRateSample(timestamp=ts, heart_rate=70))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_body_battery_duplicate_timestamp_raises(self, async_session):
        """BodyBatterySample.timestamp must be unique."""
        ts = utc_dt(2025, 1, 28, 9, 0)
        async_session.add(BodyBatterySample(timestamp=ts, body_battery=80))
        await async_session.commit()

        async_session.add(BodyBatterySample(timestamp=ts, body_battery=85))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_stress_duplicate_timestamp_raises(self, async_session):
        """StressSample.timestamp must be unique."""
        ts = utc_dt(2025, 1, 28, 10, 0)
        async_session.add(StressSample(timestamp=ts, stress_level=25))
        await async_session.commit()

        async_session.add(StressSample(timestamp=ts, stress_level=30))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_hrv_duplicate_timestamp_raises(self, async_session):
        """HrvSample.timestamp must be unique."""
        ts = utc_dt(2025, 1, 28, 2, 0)
        async_session.add(HrvSample(timestamp=ts, hrv_value=55.0))
        await async_session.commit()

        async_session.add(HrvSample(timestamp=ts, hrv_value=60.0))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_spo2_duplicate_timestamp_raises(self, async_session):
        """Spo2Sample.timestamp must be unique."""
        ts = utc_dt(2025, 1, 28, 3, 0)
        async_session.add(Spo2Sample(timestamp=ts, spo2_value=96))
        await async_session.commit()

        async_session.add(Spo2Sample(timestamp=ts, spo2_value=97))
        with pytest.raises(IntegrityError):
            await async_session.commit()


class TestSleepSessionConstraints:

    @pytest.mark.asyncio
    async def test_duplicate_date_raises(self, async_session):
        """SleepSession.date must be unique (one record per night)."""
        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            total_sleep_seconds=7 * 3600,
            sleep_score=78,
        ))
        await async_session.commit()

        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            total_sleep_seconds=8 * 3600,
            sleep_score=80,
        ))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_different_dates_allowed(self, async_session):
        """Different dates should coexist without conflict."""
        async_session.add(SleepSession(date=date(2025, 1, 27), total_sleep_seconds=7 * 3600))
        async_session.add(SleepSession(date=date(2025, 1, 28), total_sleep_seconds=8 * 3600))
        await async_session.commit()  # should not raise


class TestActivityConstraints:

    @pytest.mark.asyncio
    async def test_duplicate_garmin_activity_id_raises(self, async_session):
        """Activity.garmin_activity_id must be unique."""
        async_session.add(Activity(
            garmin_activity_id="act-001",
            activity_type="running",
            start_time=utc_dt(2025, 1, 28, 7, 0),
            end_time=utc_dt(2025, 1, 28, 8, 0),
        ))
        await async_session.commit()

        async_session.add(Activity(
            garmin_activity_id="act-001",
            activity_type="cycling",
            start_time=utc_dt(2025, 1, 28, 9, 0),
            end_time=utc_dt(2025, 1, 28, 10, 0),
        ))
        with pytest.raises(IntegrityError):
            await async_session.commit()


class TestDailyHabitConstraints:

    @pytest.mark.asyncio
    async def test_duplicate_date_habit_name_raises(self, async_session):
        """(date, habit_name) must be unique."""
        async_session.add(DailyHabit(
            date=date(2025, 1, 28),
            habit_name="pm_slump",
            habit_value="true",
            habit_type="boolean",
        ))
        await async_session.commit()

        async_session.add(DailyHabit(
            date=date(2025, 1, 28),
            habit_name="pm_slump",
            habit_value="false",
            habit_type="boolean",
        ))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_same_habit_different_dates_allowed(self, async_session):
        """Same habit name on different dates should not conflict."""
        async_session.add(DailyHabit(
            date=date(2025, 1, 27),
            habit_name="pm_slump",
            habit_value="true",
        ))
        async_session.add(DailyHabit(
            date=date(2025, 1, 28),
            habit_name="pm_slump",
            habit_value="false",
        ))
        await async_session.commit()  # should not raise

    @pytest.mark.asyncio
    async def test_same_date_different_habits_allowed(self, async_session):
        """Different habit names on same date should not conflict."""
        async_session.add(DailyHabit(
            date=date(2025, 1, 28),
            habit_name="pm_slump",
            habit_value="true",
        ))
        async_session.add(DailyHabit(
            date=date(2025, 1, 28),
            habit_name="coffee_count",
            habit_value="2",
        ))
        await async_session.commit()  # should not raise
