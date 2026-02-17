"""Tests for sync API endpoints.

Tests focus on:
1. GET /api/sync/status — response shape with no data, and with sync log data
2. POST /api/sync/garmin — returns correct response shape (background task not awaited)
3. POST /api/sync/backfill — validates input, returns correct response

We test the router directly using a test client with get_db overridden to use
the in-memory session from conftest.
"""

import pytest
import pytest_asyncio
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.sync import router
from app.core.database import get_db
from app.models.sync_log import SyncLog


def _make_test_app(session):
    """Build a minimal FastAPI app with the sync router and a mocked DB."""
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


class TestSyncStatus:

    @pytest.mark.asyncio
    async def test_returns_never_synced_when_no_logs(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["garmin_status"] == "never_synced"
        assert data["habitsync_status"] == "never_synced"
        assert data["garmin_last_sync"] is None
        assert data["habitsync_last_sync"] is None
        assert data["last_sync_date"] is None

    @pytest.mark.asyncio
    async def test_returns_last_sync_when_logs_exist(self, async_session):
        now = datetime(2025, 1, 28, 6, 30)
        async_session.add(SyncLog(
            sync_type="garmin",
            date_synced=date(2025, 1, 27),
            started_at=now,
            completed_at=now,
            status="success",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/sync/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["garmin_status"] == "success"
        assert data["last_sync_date"] == "2025-01-27"
        assert data["garmin_last_sync"] is not None


class TestSyncPostEndpoints:

    @pytest.mark.asyncio
    async def test_post_garmin_returns_200_with_message(self, async_session):
        """POST /api/sync/garmin should return 200 immediately (background task)."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/garmin?date_param=2025-01-28")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["date"] == "2025-01-28"

    @pytest.mark.asyncio
    async def test_post_habitsync_returns_200(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/habitsync?date_param=2025-01-28")
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2025-01-28"

    @pytest.mark.asyncio
    async def test_post_all_returns_200(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/all?date_param=2025-01-28")
        assert resp.status_code == 200


class TestSyncBackfill:

    @pytest.mark.asyncio
    async def test_backfill_with_days_parameter(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/backfill", json={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_days"] == 7
        assert "start_date" in data
        assert "end_date" in data

    @pytest.mark.asyncio
    async def test_backfill_validates_days_range(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/backfill", json={"days": 400})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_backfill_requires_params(self, async_session):
        """Providing no days and no dates should return 422."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/backfill", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_backfill_status_endpoint(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/sync/backfill/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_running" in data
