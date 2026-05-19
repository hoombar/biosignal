"""Tests for context event logging API."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.context_events import router
from app.core.database import get_db
from app.models.database import ContextEvent


def _make_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


class TestContextEventsApi:
    @pytest.mark.asyncio
    async def test_create_context_event(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/context-events", json={
                "title": "Conference abroad",
                "start_date": "2026-05-19",
                "end_date": "2026-05-24",
                "category": "conference",
                "tags": ["flight", "hotel", "timezone_shift"],
                "intensity": "high",
                "exclude_from_baseline": True,
                "notes": "Long travel day before arrival.",
            })

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] > 0
        assert body["title"] == "Conference abroad"
        assert body["tags"] == ["flight", "hotel", "timezone_shift"]
        assert body["exclude_from_baseline"] is True

        row = (await async_session.execute(select(ContextEvent))).scalar_one()
        assert row.start_date == date(2026, 5, 19)
        assert row.end_date == date(2026, 5, 24)

    @pytest.mark.asyncio
    async def test_list_returns_events_overlapping_range(self, async_session):
        async_session.add_all([
            ContextEvent(
                title="Before",
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 2),
                category="other",
                tags=[],
            ),
            ContextEvent(
                title="Conference abroad",
                start_date=date(2026, 5, 19),
                end_date=date(2026, 5, 24),
                category="conference",
                tags=["hotel"],
            ),
            ContextEvent(
                title="Flight home",
                start_date=date(2026, 5, 24),
                end_date=date(2026, 5, 25),
                category="travel",
                tags=["flight"],
            ),
        ])
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/context-events",
                params={"start": "2026-05-20", "end": "2026-05-24"},
            )

        assert resp.status_code == 200
        assert [event["title"] for event in resp.json()] == [
            "Conference abroad",
            "Flight home",
        ]

    @pytest.mark.asyncio
    async def test_rejects_end_date_before_start_date(self, async_session):
        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/context-events", json={
                "title": "Invalid trip",
                "start_date": "2026-05-24",
                "end_date": "2026-05-19",
                "category": "travel",
            })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_context_event(self, async_session):
        event = ContextEvent(
            title="Trip",
            start_date=date(2026, 5, 19),
            end_date=date(2026, 5, 20),
            category="travel",
            tags=[],
        )
        async_session.add(event)
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.patch(f"/api/context-events/{event.id}", json={
                "title": "Conference abroad",
                "end_date": "2026-05-24",
                "tags": ["flight", "hotel"],
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Conference abroad"
        assert body["end_date"] == "2026-05-24"
        assert body["tags"] == ["flight", "hotel"]

    @pytest.mark.asyncio
    async def test_delete_context_event(self, async_session):
        event = ContextEvent(
            title="Trip",
            start_date=date(2026, 5, 19),
            end_date=date(2026, 5, 20),
            category="travel",
            tags=[],
        )
        async_session.add(event)
        await async_session.commit()

        app = _make_app(async_session)
        with TestClient(app) as client:
            resp = client.delete(f"/api/context-events/{event.id}")

        assert resp.status_code == 204
        row = (await async_session.execute(select(ContextEvent))).scalar_one_or_none()
        assert row is None
