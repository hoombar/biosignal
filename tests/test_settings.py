"""Tests for settings API endpoints.

Tests:
- GET /api/settings/habits - returns all habits with display config
- PUT /api/settings/habits/{habit_name} - upsert display config for a habit
"""

import pytest
from datetime import date
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.database import DailyHabit, HabitDisplayConfig


def _make_test_app(session):
    from app.api.settings import router
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


class TestGetHabitsSettings:
    """Tests for GET /api/settings/habits."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_habits(self, async_session):
        """When no habits exist in DB, returns empty list."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/settings/habits")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_known_habits_with_defaults(self, async_session):
        """Habits that exist in daily_habits but have no config are returned with null display fields."""
        async_session.add(DailyHabit(
            date=date(2025, 1, 15),
            habit_name="afternoon_slump",
            habit_value="1",
            habit_type="boolean",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/settings/habits")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["habit_name"] == "afternoon_slump"
        assert data[0]["display_name"] is None
        assert data[0]["emoji"] is None
        assert data[0]["sort_order"] == 0

    @pytest.mark.asyncio
    async def test_returns_config_when_set(self, async_session):
        """Habits with saved config return the config values."""
        async_session.add(DailyHabit(
            date=date(2025, 1, 15),
            habit_name="afternoon_slump",
            habit_value="1",
            habit_type="boolean",
        ))
        async_session.add(HabitDisplayConfig(
            habit_name="afternoon_slump",
            display_name="Low energy afternoon",
            emoji="😮‍💨",
            sort_order=1,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/settings/habits")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        entry = data[0]
        assert entry["habit_name"] == "afternoon_slump"
        assert entry["display_name"] == "Low energy afternoon"
        assert entry["emoji"] == "😮‍💨"
        assert entry["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_habits_sorted_by_sort_order_then_name(self, async_session):
        """Results are sorted by sort_order ascending, then habit_name."""
        for name, val in [("coffee", "2"), ("beer", "1"), ("afternoon_slump", "0")]:
            async_session.add(DailyHabit(
                date=date(2025, 1, 15),
                habit_name=name,
                habit_value=val,
                habit_type="counter",
            ))
        async_session.add(HabitDisplayConfig(
            habit_name="afternoon_slump",
            display_name="Low energy afternoon",
            emoji="😮‍💨",
            sort_order=1,
        ))
        async_session.add(HabitDisplayConfig(
            habit_name="coffee",
            display_name="Coffee",
            emoji="☕",
            sort_order=2,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/settings/habits")

        data = resp.json()
        names = [d["habit_name"] for d in data]
        # beer has no config (sort_order=0), afternoon_slump=1, coffee=2
        assert names[0] == "beer"
        assert names[1] == "afternoon_slump"
        assert names[2] == "coffee"

    @pytest.mark.asyncio
    async def test_deduplicates_habit_names_across_dates(self, async_session):
        """Same habit appearing on multiple dates is returned once."""
        for d in [date(2025, 1, 10), date(2025, 1, 11), date(2025, 1, 12)]:
            async_session.add(DailyHabit(
                date=d,
                habit_name="coffee",
                habit_value="1",
                habit_type="counter",
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/settings/habits")

        data = resp.json()
        assert len(data) == 1
        assert data[0]["habit_name"] == "coffee"


class TestPutHabitSettings:
    """Tests for PUT /api/settings/habits/{habit_name}."""

    @pytest.mark.asyncio
    async def test_creates_config_for_new_habit(self, async_session):
        """PUT creates a new config row when none exists."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                "/api/settings/habits/afternoon_slump",
                json={"display_name": "Low energy afternoon", "emoji": "😮‍💨", "sort_order": 1},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["habit_name"] == "afternoon_slump"
        assert data["display_name"] == "Low energy afternoon"
        assert data["emoji"] == "😮‍💨"
        assert data["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_updates_existing_config(self, async_session):
        """PUT updates an existing config row."""
        async_session.add(HabitDisplayConfig(
            habit_name="coffee",
            display_name="Old name",
            emoji="🍵",
            sort_order=0,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                "/api/settings/habits/coffee",
                json={"display_name": "Coffee", "emoji": "☕", "sort_order": 2},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Coffee"
        assert data["emoji"] == "☕"
        assert data["sort_order"] == 2

    @pytest.mark.asyncio
    async def test_partial_update_clears_unset_fields(self, async_session):
        """PUT with null fields clears those fields."""
        async_session.add(HabitDisplayConfig(
            habit_name="beer",
            display_name="Beer",
            emoji="🍺",
            sort_order=3,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.put(
                "/api/settings/habits/beer",
                json={"display_name": "Beer", "emoji": None, "sort_order": 3},
            )

        assert resp.status_code == 200
        assert resp.json()["emoji"] is None

    @pytest.mark.asyncio
    async def test_persists_across_requests(self, async_session):
        """Config saved via PUT is returned in subsequent GET."""
        app = _make_test_app(async_session)
        # Seed a habit so it appears in the list
        async_session.add(DailyHabit(
            date=date(2025, 1, 15),
            habit_name="afternoon_slump",
            habit_value="1",
            habit_type="boolean",
        ))
        await async_session.commit()

        with TestClient(app) as client:
            client.put(
                "/api/settings/habits/afternoon_slump",
                json={"display_name": "PM slump", "emoji": "😩", "sort_order": 0},
            )
            resp = client.get("/api/settings/habits")

        data = resp.json()
        entry = next(d for d in data if d["habit_name"] == "afternoon_slump")
        assert entry["display_name"] == "PM slump"
        assert entry["emoji"] == "😩"
