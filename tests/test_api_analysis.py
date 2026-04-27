"""Tests for analysis API endpoints."""

import pytest
from datetime import date, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analysis import router
from app.core.database import get_db
from app.models.database import SleepSession, DailyHabit, HabitDisplayConfig
from tests.conftest import log_habit


def _make_test_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _make_date(offset: int) -> date:
    anchor = date.today() - timedelta(days=30)
    return anchor + timedelta(days=offset)


class TestCorrelationsApi:
    """Tests for GET /api/correlations."""

    @pytest.mark.asyncio
    async def test_accepts_metric_target(self, async_session):
        """Should allow metric targets like sleep_hours (not only habits)."""
        for i in range(10):
            slump = i % 2 == 0
            sleep_hours = 5.5 if slump else 8.5
            async_session.add(SleepSession(
                date=_make_date(i),
                total_sleep_seconds=int(sleep_hours * 3600),
                sleep_score=int(sleep_hours * 10),
            ))
            await log_habit(
                async_session, "pm_slump", _make_date(i), 1 if slump else 0, habit_type="binary"
            )
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/correlations", params={"target": "sleep_hours", "min_days": 5})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["target_is_binary"] is False
        assert data[0]["positive_label"] == "Higher target"
        assert data[0]["negative_label"] == "Lower target"

    @pytest.mark.asyncio
    async def test_target_habit_backwards_compatible(self, async_session):
        """Legacy target_habit query parameter should still work."""
        for i in range(7):
            slump = i % 2 == 0
            async_session.add(SleepSession(
                date=_make_date(i),
                total_sleep_seconds=int((6.0 + i * 0.1) * 3600),
                sleep_score=70,
            ))
            await log_habit(
                async_session, "pm_slump", _make_date(i), 1 if slump else 0, habit_type="binary"
            )
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/correlations", params={"target_habit": "pm_slump", "min_days": 5})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestCorrelationTargetsApi:
    """Tests for GET /api/correlation-targets."""

    @pytest.mark.asyncio
    async def test_includes_metric_and_habit_targets(self, async_session):
        """Target options should include Garmin metrics and DB habits."""
        d = _make_date(0)
        await log_habit(async_session, "pm_slump", d, 1, habit_type="binary")
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/correlation-targets")

        assert resp.status_code == 200
        data = resp.json()
        targets = {row["target"] for row in data}

        assert "sleep_hours" in targets
        assert "steps_total" in targets
        assert "habit:pm_slump" in targets


class TestPatternsAndInsightsApi:
    """Tests for GET /api/patterns and GET /api/insights."""

    @pytest.mark.asyncio
    async def test_patterns_defaults_to_first_habit_by_sort_order(self, async_session):
        """When target_habit is omitted, endpoint should choose first configured habit."""
        for i in range(10):
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

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            default_resp = client.get("/api/patterns")
            explicit_resp = client.get("/api/patterns", params={"target_habit": "morning_fatigue"})

        assert default_resp.status_code == 200
        assert explicit_resp.status_code == 200
        assert default_resp.json() == explicit_resp.json()

    @pytest.mark.asyncio
    async def test_insights_defaults_to_first_habit_by_sort_order(self, async_session):
        """Insights endpoint should mirror explicit target when omitted."""
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

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            default_resp = client.get("/api/insights")
            explicit_resp = client.get("/api/insights", params={"target_habit": "morning_fatigue"})

        assert default_resp.status_code == 200
        assert explicit_resp.status_code == 200
        assert default_resp.json() == explicit_resp.json()
