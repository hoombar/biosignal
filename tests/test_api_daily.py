"""Tests for daily API endpoints.

Tests:
- GET /api/daily with start/end date params (new)
- GET /api/daily with days param (backwards compat)
- GET /api/daily/calendar?year=YYYY (new lightweight endpoint)
- GET /api/daily/notable?year=YYYY&month=MM (new notable days endpoint)
"""

import pytest
from datetime import date, datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.daily import router
from app.core.database import get_db
from app.models.database import SleepSession, HeartRateSample, DailyHabit


def _make_test_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def utc_dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute)


class TestDailyDateRange:
    """Tests for /api/daily with start/end date parameters."""

    @pytest.mark.asyncio
    async def test_start_end_returns_only_requested_range(self, async_session):
        """When start and end are provided, only those dates are returned."""
        for d, score in [
            (date(2025, 1, 26), 70),
            (date(2025, 1, 27), 75),
            (date(2025, 1, 28), 80),
            (date(2025, 1, 29), 85),
        ]:
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=7 * 3600,
                sleep_score=score,
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily",
                params={"start": "2025-01-27", "end": "2025-01-28"}
            )

        assert resp.status_code == 200
        data = resp.json()
        dates = [d["date"] for d in data]
        assert "2025-01-27" in dates
        assert "2025-01-28" in dates
        assert "2025-01-26" not in dates
        assert "2025-01-29" not in dates

    @pytest.mark.asyncio
    async def test_days_param_still_works(self, async_session):
        """Backwards compat: days param should still work for other pages."""
        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/daily", params={"days": 5})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_start_end_single_day(self, async_session):
        """start == end should return exactly one day."""
        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily",
                params={"start": "2025-01-28", "end": "2025-01-28"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["date"] == "2025-01-28"

    @pytest.mark.asyncio
    async def test_results_are_oldest_first(self, async_session):
        """Results should be sorted oldest-first."""
        for d, score in [
            (date(2025, 1, 26), 70),
            (date(2025, 1, 28), 80),
            (date(2025, 1, 27), 75),
        ]:
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=7 * 3600,
                sleep_score=score,
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily",
                params={"start": "2025-01-26", "end": "2025-01-28"}
            )

        data = resp.json()
        dates = [d["date"] for d in data]
        assert dates == ["2025-01-26", "2025-01-27", "2025-01-28"]


class TestCalendarEndpoint:
    """Tests for /api/daily/calendar lightweight year summary."""

    @pytest.mark.asyncio
    async def test_returns_lightweight_summaries(self, async_session):
        """Calendar endpoint returns date + sleep_score + has_slump only."""
        async_session.add(SleepSession(
            date=date(2025, 3, 15),
            total_sleep_seconds=7 * 3600,
            sleep_score=82,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/daily/calendar", params={"year": 2025})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should have entries for every day in 2025
        assert len(data) == 365

        # Find the day with data
        march_15 = next(d for d in data if d["date"] == "2025-03-15")
        assert march_15["sleep_score"] == 82
        assert "date" in march_15
        assert "sleep_score" in march_15
        assert "has_slump" in march_15

        # Should NOT include heavy fields
        assert "hrv_overnight_avg" not in march_15
        assert "bb_samples" not in march_15

    @pytest.mark.asyncio
    async def test_has_slump_true_when_slump_logged(self, async_session):
        """has_slump should be true when afternoon_slump habit value > 0."""
        async_session.add(DailyHabit(
            date=date(2025, 3, 15),
            habit_name="afternoon_slump",
            habit_value="1",
            habit_type="counter",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/daily/calendar", params={"year": 2025})

        data = resp.json()
        march_15 = next(d for d in data if d["date"] == "2025-03-15")
        assert march_15["has_slump"] is True

    @pytest.mark.asyncio
    async def test_has_slump_false_when_clear(self, async_session):
        """has_slump should be false when afternoon_slump habit value is 0."""
        async_session.add(DailyHabit(
            date=date(2025, 3, 15),
            habit_name="afternoon_slump",
            habit_value="0",
            habit_type="counter",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/daily/calendar", params={"year": 2025})

        data = resp.json()
        march_15 = next(d for d in data if d["date"] == "2025-03-15")
        assert march_15["has_slump"] is False

    @pytest.mark.asyncio
    async def test_days_without_data_have_nulls(self, async_session):
        """Days with no data should have null sleep_score and false has_slump."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/daily/calendar", params={"year": 2025})

        data = resp.json()
        jan_1 = next(d for d in data if d["date"] == "2025-01-01")
        assert jan_1["sleep_score"] is None
        assert jan_1["has_slump"] is False


class TestNotableDaysEndpoint:
    """Tests for /api/daily/notable monthly notable days."""

    @pytest.mark.asyncio
    async def test_returns_notable_days_for_month(self, async_session):
        """Notable days endpoint returns extremes for a given month."""
        # Seed multiple days with varying sleep scores
        for day_num, score in [(1, 60), (5, 95), (10, 45), (15, 78), (20, 82)]:
            async_session.add(SleepSession(
                date=date(2025, 3, day_num),
                total_sleep_seconds=7 * 3600,
                sleep_score=score,
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily/notable",
                params={"year": 2025, "month": 3}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert len(data) <= 5  # max 5 notable items

        # Each notable day should have required fields
        for item in data:
            assert "date" in item
            assert "description" in item
            assert "metric" in item
            assert "value" in item

    @pytest.mark.asyncio
    async def test_best_sleep_score_is_notable(self, async_session):
        """The best sleep score in a month should appear as a notable day."""
        for day_num, score in [(1, 60), (5, 95), (10, 70)]:
            async_session.add(SleepSession(
                date=date(2025, 3, day_num),
                total_sleep_seconds=7 * 3600,
                sleep_score=score,
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily/notable",
                params={"year": 2025, "month": 3}
            )

        data = resp.json()
        dates = [d["date"] for d in data]
        assert "2025-03-05" in dates  # best sleep score day

    @pytest.mark.asyncio
    async def test_worst_sleep_score_is_notable(self, async_session):
        """The worst sleep score in a month should appear as a notable day."""
        for day_num, score in [(1, 60), (5, 95), (10, 35)]:
            async_session.add(SleepSession(
                date=date(2025, 3, day_num),
                total_sleep_seconds=7 * 3600,
                sleep_score=score,
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily/notable",
                params={"year": 2025, "month": 3}
            )

        data = resp.json()
        dates = [d["date"] for d in data]
        assert "2025-03-10" in dates  # worst sleep score day

    @pytest.mark.asyncio
    async def test_empty_month_returns_empty_list(self, async_session):
        """A month with no data should return an empty list."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily/notable",
                params={"year": 2025, "month": 6}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data == []


class TestHabitsApiShape:
    """Contract tests: /api/daily habits field has expected shape for frontend."""

    @pytest.mark.asyncio
    async def test_habits_have_name_value_type_fields(self, async_session):
        """Each habit in /api/daily response must have name, value, type fields."""
        async_session.add(SleepSession(
            date=date(2025, 1, 15),
            total_sleep_seconds=7 * 3600,
            sleep_score=75,
        ))
        async_session.add(DailyHabit(
            date=date(2025, 1, 15),
            habit_name="afternoon_slump",
            habit_value="1",
            habit_type="boolean",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily",
                params={"start": "2025-01-15", "end": "2025-01-15"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        habits = data[0]["habits"]
        assert len(habits) == 1
        habit = habits[0]
        assert "name" in habit
        assert "value" in habit
        assert "type" in habit
        assert habit["name"] == "afternoon_slump"
        assert isinstance(habit["value"], int)
        assert isinstance(habit["type"], str)

    @pytest.mark.asyncio
    async def test_day_with_no_habits_returns_empty_list(self, async_session):
        """Days with no habits logged return habits as empty list."""
        async_session.add(SleepSession(
            date=date(2025, 1, 15),
            total_sleep_seconds=7 * 3600,
            sleep_score=75,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/daily",
                params={"start": "2025-01-15", "end": "2025-01-15"}
            )

        data = resp.json()
        assert data[0]["habits"] == []
