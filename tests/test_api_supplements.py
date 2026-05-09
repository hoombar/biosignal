"""Tests for supplement group configuration and logging."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.supplements import router
from app.core.database import get_db
from app.models.database import DailyHabit, Habit, SupplementLog, SupplementPlanVersion


def _make_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


class TestSupplementConfig:

    @pytest.mark.asyncio
    async def test_empty_config_returns_fixed_slots(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            resp = client.get("/api/supplements/config")

        assert resp.status_code == 200
        body = resp.json()
        assert [slot["slot"] for slot in body["slots"]] == ["morning", "midday", "evening"]
        assert all(slot["items"] == [] for slot in body["slots"])

    @pytest.mark.asyncio
    async def test_put_slot_creates_new_version(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            first = client.put(
                "/api/supplements/slots/morning",
                json={"items": [{"name": "Vitamin D", "dose": "1000 IU"}]},
            )
            second = client.put(
                "/api/supplements/slots/morning",
                json={"items": [{"name": "Vitamin D", "dose": "2000 IU"}]},
            )

        assert first.status_code == 200
        assert first.json()["version"] == 1
        assert second.status_code == 200
        assert second.json()["version"] == 2

        rows = (await async_session.execute(
            select(SupplementPlanVersion).order_by(SupplementPlanVersion.version)
        )).scalars().all()
        assert len(rows) == 2
        assert rows[0].items == [{"name": "Vitamin D", "dose": "1000 IU", "notes": None}]
        assert rows[1].items == [{"name": "Vitamin D", "dose": "2000 IU", "notes": None}]


class TestSupplementLogging:

    @pytest.mark.asyncio
    async def test_logging_slot_freezes_snapshot_and_mirrors_habit(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            client.put(
                "/api/supplements/slots/morning",
                json={"items": [{"name": "Vitamin D"}, {"name": "Magnesium"}]},
            )
            resp = client.put(
                "/api/supplements/log/2026-05-09/morning",
                json={"completed": True},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-05-09"
        assert body["slot"] == "morning"
        assert body["completed"] is True
        assert [item["name"] for item in body["snapshot"]] == ["Vitamin D", "Magnesium"]

        log = (await async_session.execute(select(SupplementLog))).scalar_one()
        assert log.snapshot == [
            {"name": "Vitamin D", "dose": None, "notes": None},
            {"name": "Magnesium", "dose": None, "notes": None},
        ]

        habit = (await async_session.execute(
            select(Habit).where(Habit.name == "supplements_morning")
        )).scalar_one()
        assert habit.source == "supplement_slot"
        mirrored = (await async_session.execute(
            select(DailyHabit).where(
                DailyHabit.date == date(2026, 5, 9),
                DailyHabit.habit_id == habit.id,
            )
        )).scalar_one()
        assert mirrored.habit_value == 1

    @pytest.mark.asyncio
    async def test_old_log_uses_original_snapshot_after_config_change(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            client.put(
                "/api/supplements/slots/evening",
                json={"items": [{"name": "Magnesium"}]},
            )
            client.put(
                "/api/supplements/log/2026-05-01/evening",
                json={"completed": True},
            )
            client.put(
                "/api/supplements/slots/evening",
                json={"items": [{"name": "Magnesium"}, {"name": "Glycine"}]},
            )
            resp = client.get(
                "/api/supplements/logs",
                params={"start": "2026-05-01", "end": "2026-05-01"},
            )

        assert resp.status_code == 200
        logs = resp.json()["logs"]
        assert len(logs) == 1
        assert logs[0]["slot"] == "evening"
        assert [item["name"] for item in logs[0]["snapshot"]] == ["Magnesium"]

    @pytest.mark.asyncio
    async def test_delete_log_clears_mirrored_habit(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            client.put("/api/supplements/slots/midday", json={"items": [{"name": "Omega 3"}]})
            client.put("/api/supplements/log/2026-05-09/midday", json={"completed": True})
            resp = client.delete("/api/supplements/log/2026-05-09/midday")

        assert resp.status_code == 204
        assert (await async_session.execute(select(SupplementLog))).scalars().all() == []

        habit = (await async_session.execute(
            select(Habit).where(Habit.name == "supplements_midday")
        )).scalar_one()
        mirrored = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit.id)
        )).scalars().all()
        assert mirrored == []

