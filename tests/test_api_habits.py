"""Tests for the native habit logging API.

Endpoints under /api/habits:
- GET /list — active habits joined with display config
- PUT /log/{date}/{habit_id} — upsert a logged value
- DELETE /log/{date}/{habit_id} — clear a logged value
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.habits import router
from app.core.database import get_db
from app.models.database import DailyHabit, Habit, HabitDisplayConfig
from tests.conftest import ensure_habit, log_habit


def _make_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


class TestListHabits:

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_habits(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/list")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_includes_id_name_type_and_display_config(self, async_session):
        habit = await ensure_habit(async_session, "pm_slump", habit_type="binary")
        async_session.add(HabitDisplayConfig(
            habit_name="pm_slump",
            display_name="PM Slump",
            emoji="😩",
            color="#ff4466",
            sort_order=2,
        ))
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/list")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        entry = body[0]
        assert entry["id"] == habit.id
        assert entry["name"] == "pm_slump"
        assert entry["habit_type"] == "binary"
        assert entry["archived"] is False
        assert entry["display_name"] == "PM Slump"
        assert entry["emoji"] == "😩"
        assert entry["color"] == "#ff4466"
        assert entry["sort_order"] == 2

    @pytest.mark.asyncio
    async def test_excludes_archived_by_default(self, async_session):
        from datetime import datetime
        active = await ensure_habit(async_session, "coffee", habit_type="counter")
        archived = await ensure_habit(async_session, "stretch", habit_type="binary")
        archived.archived_at = datetime(2026, 1, 1)
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/list")

        names = {row["name"] for row in resp.json()}
        assert names == {"coffee"}

    @pytest.mark.asyncio
    async def test_include_archived_query_param(self, async_session):
        from datetime import datetime
        await ensure_habit(async_session, "coffee", habit_type="counter")
        archived = await ensure_habit(async_session, "stretch", habit_type="binary")
        archived.archived_at = datetime(2026, 1, 1)
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/list", params={"include_archived": "true"})

        rows = resp.json()
        names_with_archived = {row["name"]: row["archived"] for row in rows}
        assert names_with_archived == {"coffee": False, "stretch": True}

    @pytest.mark.asyncio
    async def test_results_sorted_by_sort_order_then_name(self, async_session):
        for name in ("coffee", "alcohol", "pm_slump"):
            await ensure_habit(async_session, name, habit_type="binary")
        async_session.add(HabitDisplayConfig(habit_name="pm_slump", sort_order=1))
        async_session.add(HabitDisplayConfig(habit_name="coffee", sort_order=2))
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/list")

        names = [row["name"] for row in resp.json()]
        # alcohol has no config → sort_order 0 first; then pm_slump=1; then coffee=2
        assert names == ["alcohol", "pm_slump", "coffee"]


class TestPutHabitLog:

    @pytest.mark.asyncio
    async def test_creates_new_log_entry(self, async_session):
        habit = await ensure_habit(async_session, "pm_slump", habit_type="binary")
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                f"/api/habits/log/2026-04-15/{habit.id}",
                json={"value": 1},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"date": "2026-04-15", "habit_id": habit.id, "value": 1}

        row = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit.id)
        )).scalar_one()
        assert row.habit_value == 1

    @pytest.mark.asyncio
    async def test_overwrites_existing_value_idempotent(self, async_session):
        """Retrospective edit: PUT twice on the same (date, habit) overwrites."""
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            client.put(f"/api/habits/log/2026-04-15/{habit.id}", json={"value": 2})
            resp = client.put(f"/api/habits/log/2026-04-15/{habit.id}", json={"value": 5})

        assert resp.status_code == 200
        await async_session.commit()  # release current txn before re-fetching
        rows = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit.id)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].habit_value == 5

    @pytest.mark.asyncio
    async def test_binary_value_must_be_zero_or_one(self, async_session):
        habit = await ensure_habit(async_session, "pm_slump", habit_type="binary")
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                f"/api/habits/log/2026-04-15/{habit.id}", json={"value": 3}
            )

        assert resp.status_code == 422
        assert "binary" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_negative_value_rejected(self, async_session):
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                f"/api/habits/log/2026-04-15/{habit.id}", json={"value": -1}
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_habit_returns_404(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.put("/api/habits/log/2026-04-15/9999", json={"value": 1})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_habit_rejects_logging(self, async_session):
        from datetime import datetime
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        habit.archived_at = datetime(2026, 1, 1)
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                f"/api/habits/log/2026-04-15/{habit.id}", json={"value": 1}
            )

        assert resp.status_code == 409


class TestDeleteHabitLog:

    @pytest.mark.asyncio
    async def test_removes_existing_entry(self, async_session):
        target = date(2026, 4, 15)
        await log_habit(async_session, "coffee", target, 3, habit_type="counter")
        habit = (await async_session.execute(
            select(Habit).where(Habit.name == "coffee")
        )).scalar_one()
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.delete(f"/api/habits/log/2026-04-15/{habit.id}")

        assert resp.status_code == 204

        await async_session.commit()
        remaining = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit.id)
        )).scalars().all()
        assert remaining == []

    @pytest.mark.asyncio
    async def test_returns_404_when_no_entry(self, async_session):
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.delete(f"/api/habits/log/2026-04-15/{habit.id}")

        assert resp.status_code == 404
