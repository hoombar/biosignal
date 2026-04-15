"""Tests for analysis API endpoints."""

import pytest
from datetime import date, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analysis import router
from app.core.database import get_db
from app.models.database import SleepSession, DailyHabit


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
            async_session.add(DailyHabit(
                date=_make_date(i),
                habit_name="pm_slump",
                habit_value="true" if slump else "false",
                habit_type="boolean",
            ))
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
            async_session.add(DailyHabit(
                date=_make_date(i),
                habit_name="pm_slump",
                habit_value="true" if slump else "false",
                habit_type="boolean",
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/correlations", params={"target_habit": "pm_slump", "min_days": 5})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
