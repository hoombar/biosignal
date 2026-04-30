"""Tests for the native habit logging API.

Endpoints under /api/habits:
- GET /list — active habits joined with display config
- PUT /log/{date}/{habit_id} — upsert a logged value
- DELETE /log/{date}/{habit_id} — clear a logged value
"""
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

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


async def _habit_snapshot(session):
    habits = (await session.execute(select(Habit).order_by(Habit.name))).scalars().all()
    configs = (await session.execute(select(HabitDisplayConfig))).scalars().all()
    cfg_by_name = {cfg.habit_name: cfg for cfg in configs}
    rows = (await session.execute(select(DailyHabit).order_by(DailyHabit.date, DailyHabit.habit_id))).scalars().all()

    habit_by_id = {habit.id: habit for habit in habits}
    logs_by_name: dict[str, list[dict]] = {habit.name: [] for habit in habits}
    for row in rows:
        habit = habit_by_id[row.habit_id]
        logs_by_name[habit.name].append({
            "date": row.date.isoformat(),
            "value": row.habit_value,
        })

    snapshot = []
    for habit in habits:
        cfg = cfg_by_name.get(habit.name)
        snapshot.append({
            "name": habit.name,
            "habit_type": habit.habit_type,
            "is_negative": habit.is_negative,
            "target_value": habit.target_value,
            "period": habit.period,
            "archived_at": habit.archived_at.isoformat() if habit.archived_at else None,
            "created_at": habit.created_at.isoformat(),
            "display": None if cfg is None else {
                "display_name": cfg.display_name,
                "emoji": cfg.emoji,
                "color": cfg.color,
                "sort_order": cfg.sort_order,
            },
            "logs": logs_by_name[habit.name],
        })
    return snapshot


async def _wipe_habit_tables(session):
    await session.execute(delete(DailyHabit))
    await session.execute(delete(HabitDisplayConfig))
    await session.execute(delete(Habit))
    await session.commit()


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


class TestCreateHabit:

    @pytest.mark.asyncio
    async def test_creates_binary_habit(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post(
                "/api/habits",
                json={"name": "Stretch", "habit_type": "binary"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "stretch"  # normalized
        assert body["habit_type"] == "binary"
        assert body["archived"] is False
        assert body["display_name"] is None
        # New generic-tracker fields default sensibly
        assert body["is_negative"] is False
        assert body["target_value"] is None
        assert body["period"] == "day"

    @pytest.mark.asyncio
    async def test_creates_negative_habit_with_target_and_period(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "Alcohol",
                "habit_type": "counter",
                "is_negative": True,
                "target_value": 2,
                "period": "week",
            })
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_negative"] is True
        assert body["target_value"] == 2
        assert body["period"] == "week"

    @pytest.mark.asyncio
    async def test_rejects_invalid_period(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "x",
                "habit_type": "binary",
                "period": "fortnight",
            })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_negative_target(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "x",
                "habit_type": "counter",
                "target_value": -3,
            })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_creates_with_display_config(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "PM Slump",
                "habit_type": "binary",
                "display_name": "PM Slump",
                "emoji": "😩",
                "color": "#ff4466",
                "sort_order": 3,
            })
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "pm_slump"
        assert body["display_name"] == "PM Slump"
        assert body["emoji"] == "😩"
        assert body["color"] == "#ff4466"
        assert body["sort_order"] == 3

    @pytest.mark.asyncio
    async def test_rejects_duplicate_name(self, async_session):
        await ensure_habit(async_session, "coffee", habit_type="counter")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "coffee",
                "habit_type": "counter",
            })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_rejects_invalid_type(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "thing",
                "habit_type": "weekly",
            })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_blank_name_after_normalization(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits", json={
                "name": "!@#$",
                "habit_type": "binary",
            })
        assert resp.status_code == 422


class TestListMetrics:

    @pytest.mark.asyncio
    async def test_list_includes_metrics_fields(self, async_session):
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/list")
        assert resp.status_code == 200
        row = resp.json()[0]
        assert row["streak"] == 0
        assert row["completion_hit"] == 0
        assert row["completion_total"] == 7
        assert row["period"] == "day"
        assert row["is_negative"] is False
        assert row["target_value"] is None


class TestUpdateHabit:

    @pytest.mark.asyncio
    async def test_creates_display_config_on_first_patch(self, async_session):
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.patch(f"/api/habits/{habit.id}", json={
                "display_name": "Coffee",
                "emoji": "☕",
                "color": "#c4a77d",
                "sort_order": 1,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["display_name"] == "Coffee"
        assert body["emoji"] == "☕"
        assert body["color"] == "#c4a77d"
        assert body["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_updates_existing_display_config(self, async_session):
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        async_session.add(HabitDisplayConfig(
            habit_name="coffee",
            display_name="Old",
            emoji="🍵",
            color="#aabbcc",
            sort_order=0,
        ))
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.patch(f"/api/habits/{habit.id}", json={
                "display_name": "Coffee",
                "emoji": "☕",
                "color": None,
                "sort_order": 5,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["display_name"] == "Coffee"
        assert body["color"] is None
        assert body["sort_order"] == 5

    @pytest.mark.asyncio
    async def test_unknown_habit_returns_404(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.patch("/api/habits/9999", json={"display_name": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_updates_target_and_period(self, async_session):
        habit = await ensure_habit(async_session, "alcohol", habit_type="counter")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.patch(f"/api/habits/{habit.id}", json={
                "is_negative": True,
                "target_value": 2,
                "period": "week",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_negative"] is True
        assert body["target_value"] == 2
        assert body["period"] == "week"

    @pytest.mark.asyncio
    async def test_patch_clear_target_erases_existing(self, async_session):
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        habit.target_value = 2
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.patch(f"/api/habits/{habit.id}", json={"clear_target": True})
        assert resp.status_code == 200
        assert resp.json()["target_value"] is None


class TestArchiveHabit:

    @pytest.mark.asyncio
    async def test_archive_marks_habit(self, async_session):
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post(f"/api/habits/{habit.id}/archive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is True

    @pytest.mark.asyncio
    async def test_archive_is_idempotent(self, async_session):
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            client.post(f"/api/habits/{habit.id}/archive")
            resp = client.post(f"/api/habits/{habit.id}/archive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is True

    @pytest.mark.asyncio
    async def test_unarchive(self, async_session):
        from datetime import datetime
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        habit.archived_at = datetime(2026, 1, 1)
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post(f"/api/habits/{habit.id}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is False

    @pytest.mark.asyncio
    async def test_archived_habit_history_still_accessible(self, async_session):
        """Archived habits still hold their historic DailyHabit rows."""
        habit = await ensure_habit(async_session, "stretch", habit_type="binary")
        await log_habit(async_session, "stretch", date(2026, 1, 5), 1, habit_type="binary")
        await async_session.commit()
        app = _make_app(async_session)
        with TestClient(app) as client:
            client.post(f"/api/habits/{habit.id}/archive")
        await async_session.commit()
        rows = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit.id)
        )).scalars().all()
        assert len(rows) == 1


class TestDeleteHabit:

    @pytest.mark.asyncio
    async def test_delete_cascades_daily_rows_and_display_config(self, async_session):
        from app.models.database import HabitDisplayConfig
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        await log_habit(async_session, "coffee", date(2026, 1, 5), 3, habit_type="counter")
        await log_habit(async_session, "coffee", date(2026, 1, 6), 2, habit_type="counter")
        async_session.add(HabitDisplayConfig(habit_name="coffee", display_name="Coffee"))
        await async_session.commit()
        habit_id = habit.id

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.delete(f"/api/habits/{habit_id}")
        assert resp.status_code == 204

        await async_session.commit()
        # Habit row gone
        row = (await async_session.execute(
            select(Habit).where(Habit.id == habit_id)
        )).scalar_one_or_none()
        assert row is None
        # Daily rows gone
        daily = (await async_session.execute(
            select(DailyHabit).where(DailyHabit.habit_id == habit_id)
        )).scalars().all()
        assert daily == []
        # Display config gone
        cfg = (await async_session.execute(
            select(HabitDisplayConfig).where(HabitDisplayConfig.habit_name == "coffee")
        )).scalar_one_or_none()
        assert cfg is None

    @pytest.mark.asyncio
    async def test_delete_unknown_returns_404(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.delete("/api/habits/9999")
        assert resp.status_code == 404


class TestExportHabits:

    @pytest.mark.asyncio
    async def test_returns_empty_bundle_when_no_habits(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/export")

        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == 1
        assert body["habits"] == []
        assert body["exported_at"]
        assert resp.headers["content-disposition"].startswith(
            'attachment; filename="biosignal_habits_'
        )

    @pytest.mark.asyncio
    async def test_exports_habits_with_display_logs_and_archived_state(self, async_session):
        coffee = await ensure_habit(async_session, "coffee", habit_type="counter")
        coffee.is_negative = True
        coffee.target_value = 2
        coffee.period = "week"
        coffee.created_at = datetime(2026, 1, 2, 8, 30, 0)

        stretch = await ensure_habit(async_session, "stretch", habit_type="binary")
        stretch.archived_at = datetime(2026, 4, 10, 9, 15, 0)
        stretch.created_at = datetime(2026, 1, 5, 7, 0, 0)

        async_session.add(HabitDisplayConfig(
            habit_name="coffee",
            display_name="Coffee",
            emoji="☕",
            color="#c4a77d",
            sort_order=3,
        ))
        await log_habit(async_session, "coffee", date(2026, 4, 28), 1, habit_type="counter")
        await log_habit(async_session, "coffee", date(2026, 4, 29), 2, habit_type="counter")
        await log_habit(async_session, "stretch", date(2026, 4, 1), 1, habit_type="binary")
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/habits/export")

        assert resp.status_code == 200
        assert resp.json()["habits"] == [
            {
                "name": "coffee",
                "habit_type": "counter",
                "is_negative": True,
                "target_value": 2,
                "period": "week",
                "archived_at": None,
                "created_at": "2026-01-02T08:30:00",
                "display": {
                    "display_name": "Coffee",
                    "emoji": "☕",
                    "color": "#c4a77d",
                    "sort_order": 3,
                },
                "logs": [
                    {"date": "2026-04-28", "value": 1},
                    {"date": "2026-04-29", "value": 2},
                ],
            },
            {
                "name": "stretch",
                "habit_type": "binary",
                "is_negative": False,
                "target_value": None,
                "period": "day",
                "archived_at": "2026-04-10T09:15:00",
                "created_at": "2026-01-05T07:00:00",
                "display": None,
                "logs": [
                    {"date": "2026-04-01", "value": 1},
                ],
            },
        ]


class TestImportHabits:

    @pytest.mark.asyncio
    async def test_round_trip_export_wipe_import_restores_state(self, async_session):
        coffee = await ensure_habit(async_session, "coffee", habit_type="counter")
        coffee.is_negative = True
        coffee.target_value = 2
        coffee.period = "week"
        coffee.created_at = datetime(2026, 1, 1, 8, 30, 0)

        stretch = await ensure_habit(async_session, "stretch", habit_type="binary")
        stretch.archived_at = datetime(2026, 2, 1, 9, 0, 0)
        stretch.created_at = datetime(2026, 1, 3, 7, 45, 0)

        async_session.add(HabitDisplayConfig(
            habit_name="coffee",
            display_name="Coffee",
            emoji="☕",
            color="#c4a77d",
            sort_order=1,
        ))
        await log_habit(async_session, "coffee", date(2026, 4, 28), 1, habit_type="counter")
        await log_habit(async_session, "coffee", date(2026, 4, 29), 2, habit_type="counter")
        await log_habit(async_session, "stretch", date(2026, 4, 29), 1, habit_type="binary")
        await async_session.commit()
        expected = await _habit_snapshot(async_session)

        app = _make_app(async_session)
        with TestClient(app) as client:
            export_resp = client.get("/api/habits/export")
        assert export_resp.status_code == 200
        bundle = export_resp.json()

        await _wipe_habit_tables(async_session)

        with TestClient(app) as client:
            import_resp = client.post("/api/habits/import", json=bundle)

        assert import_resp.status_code == 200
        assert import_resp.json() == {"habits_imported": 2, "logs_imported": 3}
        assert await _habit_snapshot(async_session) == expected

    @pytest.mark.asyncio
    async def test_import_overwrites_matching_habit_and_replaces_logs_only_for_that_habit(
        self, async_session
    ):
        coffee = await ensure_habit(async_session, "coffee", habit_type="counter")
        coffee.target_value = 5
        coffee.period = "month"
        coffee.created_at = datetime(2026, 1, 1, 8, 0, 0)
        async_session.add(HabitDisplayConfig(
            habit_name="coffee",
            display_name="Old Coffee",
            emoji="🍵",
            color="#AABBCC",
            sort_order=7,
        ))
        await log_habit(async_session, "coffee", date(2026, 4, 27), 5, habit_type="counter")
        await log_habit(async_session, "coffee", date(2026, 4, 28), 4, habit_type="counter")
        await log_habit(async_session, "coffee", date(2026, 4, 29), 3, habit_type="counter")

        stretch = await ensure_habit(async_session, "stretch", habit_type="binary")
        stretch.created_at = datetime(2026, 1, 2, 7, 30, 0)
        await log_habit(async_session, "stretch", date(2026, 4, 29), 1, habit_type="binary")
        await async_session.commit()

        bundle = {
            "version": 1,
            "exported_at": "2026-04-30T12:00:00+01:00",
            "habits": [
                {
                    "name": "coffee",
                    "habit_type": "counter",
                    "is_negative": True,
                    "target_value": 2,
                    "period": "week",
                    "archived_at": None,
                    "created_at": "2026-01-10T09:45:00",
                    "display": {
                        "display_name": "Coffee",
                        "emoji": "☕",
                        "color": "#C4A77D",
                        "sort_order": 1,
                    },
                    "logs": [
                        {"date": "2026-04-28", "value": 1},
                        {"date": "2026-04-30", "value": 2},
                    ],
                }
            ],
        }

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits/import", json=bundle)

        assert resp.status_code == 200
        assert resp.json() == {"habits_imported": 1, "logs_imported": 2}
        assert await _habit_snapshot(async_session) == [
            {
                "name": "coffee",
                "habit_type": "counter",
                "is_negative": True,
                "target_value": 2,
                "period": "week",
                "archived_at": None,
                "created_at": "2026-01-10T09:45:00",
                "display": {
                    "display_name": "Coffee",
                    "emoji": "☕",
                    "color": "#c4a77d",
                    "sort_order": 1,
                },
                "logs": [
                    {"date": "2026-04-28", "value": 1},
                    {"date": "2026-04-30", "value": 2},
                ],
            },
            {
                "name": "stretch",
                "habit_type": "binary",
                "is_negative": False,
                "target_value": None,
                "period": "day",
                "archived_at": None,
                "created_at": "2026-01-02T07:30:00",
                "display": None,
                "logs": [
                    {"date": "2026-04-29", "value": 1},
                ],
            },
        ]

    @pytest.mark.asyncio
    async def test_import_normalizes_names_display_fields_and_color(self, async_session):
        bundle = {
            "version": 1,
            "exported_at": "2026-04-30T12:00:00+01:00",
            "habits": [
                {
                    "name": "Coffee Break!!",
                    "habit_type": "counter",
                    "is_negative": False,
                    "target_value": 1,
                    "period": "day",
                    "archived_at": None,
                    "created_at": "2026-02-01T09:00:00",
                    "display": {
                        "display_name": "",
                        "emoji": " ",
                        "color": "#C4A77D",
                        "sort_order": 0,
                    },
                    "logs": [
                        {"date": "2026-04-30", "value": 1},
                    ],
                }
            ],
        }

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits/import", json=bundle)

        assert resp.status_code == 200
        assert await _habit_snapshot(async_session) == [
            {
                "name": "coffee_break",
                "habit_type": "counter",
                "is_negative": False,
                "target_value": 1,
                "period": "day",
                "archived_at": None,
                "created_at": "2026-02-01T09:00:00",
                "display": {
                    "display_name": None,
                    "emoji": None,
                    "color": "#c4a77d",
                    "sort_order": 0,
                },
                "logs": [
                    {"date": "2026-04-30", "value": 1},
                ],
            }
        ]

    @pytest.mark.asyncio
    async def test_import_rejects_duplicate_names_after_normalization(self, async_session):
        bundle = {
            "version": 1,
            "exported_at": "2026-04-30T12:00:00+01:00",
            "habits": [
                {
                    "name": "Coffee Break",
                    "habit_type": "counter",
                    "is_negative": False,
                    "target_value": None,
                    "period": "day",
                    "archived_at": None,
                    "created_at": "2026-02-01T09:00:00",
                    "display": None,
                    "logs": [],
                },
                {
                    "name": "coffee_break",
                    "habit_type": "binary",
                    "is_negative": False,
                    "target_value": None,
                    "period": "day",
                    "archived_at": None,
                    "created_at": "2026-02-02T09:00:00",
                    "display": None,
                    "logs": [],
                },
            ],
        }

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits/import", json=bundle)

        assert resp.status_code == 422
        assert "duplicate" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_rejects_unknown_bundle_version(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits/import", json={
                "version": 99,
                "exported_at": "2026-04-30T12:00:00+01:00",
                "habits": [],
            })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_bundle_is_a_no_op(self, async_session):
        habit = await ensure_habit(async_session, "coffee", habit_type="counter")
        habit.created_at = datetime(2026, 1, 1, 8, 0, 0)
        await log_habit(async_session, "coffee", date(2026, 4, 30), 2, habit_type="counter")
        await async_session.commit()
        before = await _habit_snapshot(async_session)

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/habits/import", json={
                "version": 1,
                "exported_at": "2026-04-30T12:00:00+01:00",
                "habits": [],
            })

        assert resp.status_code == 200
        assert resp.json() == {"habits_imported": 0, "logs_imported": 0}
        assert await _habit_snapshot(async_session) == before
