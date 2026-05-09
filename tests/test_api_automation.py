"""Tests for the external automation logging API."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.automation import router
from app.api.supplements import router as supplements_router
from app.core.config import get_settings
from app.core.database import get_db
from app.models.database import DailyHabit, Habit, SupplementLog
from tests.conftest import ensure_habit


def _make_app(session, settings):
    app = FastAPI()
    app.include_router(supplements_router)
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    return app


class TestAutomationAuth:

    @pytest.mark.asyncio
    async def test_rejects_when_token_not_configured(self, async_session, monkeypatch):
        monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "secret")
        monkeypatch.delenv("AUTOMATION_API_KEY", raising=False)
        settings = get_settings()
        settings.__dict__["automation_api_key"] = None
        app = _make_app(async_session, settings)

        with TestClient(app) as client:
            resp = client.post("/api/automation/log", json={"target": "habit:coffee", "value": 1})

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_missing_or_wrong_bearer_token(self, async_session, monkeypatch):
        monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "secret")
        settings = get_settings()
        settings.__dict__["automation_api_key"] = "expected-token"
        app = _make_app(async_session, settings)

        with TestClient(app) as client:
            missing = client.post("/api/automation/log", json={"target": "habit:coffee", "value": 1})
            wrong = client.post(
                "/api/automation/log",
                headers={"Authorization": "Bearer wrong-token"},
                json={"target": "habit:coffee", "value": 1},
            )

        assert missing.status_code == 401
        assert wrong.status_code == 401


class TestAutomationLogging:

    @pytest.mark.asyncio
    async def test_logs_habit_by_slug(self, async_session, monkeypatch):
        monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "secret")
        settings = get_settings()
        settings.__dict__["automation_api_key"] = "expected-token"
        app = _make_app(async_session, settings)
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        await async_session.commit()

        with TestClient(app) as client:
            resp = client.post(
                "/api/automation/log",
                headers={"Authorization": "Bearer expected-token"},
                json={"target": "habit:coffee", "value": 2, "date": "2026-05-09"},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "target": "habit:coffee",
            "date": "2026-05-09",
            "value": 2,
        }
        row = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit.id)
        )).scalar_one()
        assert row.date == date(2026, 5, 9)
        assert row.habit_value == 2

    @pytest.mark.asyncio
    async def test_logs_supplement_slot(self, async_session, monkeypatch):
        monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "secret")
        settings = get_settings()
        settings.__dict__["automation_api_key"] = "expected-token"
        app = _make_app(async_session, settings)

        with TestClient(app) as client:
            client.put(
                "/api/supplements/slots/morning",
                json={"items": [{"name": "Vitamin D"}]},
            )
            resp = client.post(
                "/api/automation/log",
                headers={"Authorization": "Bearer expected-token"},
                json={"target": "supplement:morning", "date": "2026-05-09"},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "target": "supplement:morning",
            "date": "2026-05-09",
            "value": 1,
        }
        log = (await async_session.execute(select(SupplementLog))).scalar_one()
        assert log.date == date(2026, 5, 9)
        assert log.slot == "morning"
        assert log.completed is True

