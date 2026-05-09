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
from sqlalchemy import select

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
        assert data["garmin_last_sync"] is None
        assert data["last_sync_date"] is None
        assert data["environment_status"] == "never_synced"
        assert data["environment_last_sync"] is None
        assert data["environment_last_sync_date"] is None
        services = {service["service"]: service for service in data["services"]}
        assert services["garmin"]["status"] == "never_synced"
        assert services["environment"]["status"] == "never_synced"
        assert "habitsync_status" not in data
        assert "habitsync_last_sync" not in data

    @pytest.mark.asyncio
    async def test_returns_last_sync_per_service_when_logs_exist(self, async_session):
        now = datetime(2025, 1, 28, 6, 30)
        async_session.add(SyncLog(
            sync_type="garmin",
            date_synced=date(2025, 1, 27),
            started_at=now,
            completed_at=now,
            status="success",
        ))
        async_session.add(SyncLog(
            sync_type="environment",
            date_synced=date(2025, 1, 28),
            started_at=now,
            completed_at=now,
            status="partial",
            error_message="pollen: timeout",
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
        assert data["environment_status"] == "partial"
        assert data["environment_last_sync_date"] == "2025-01-28"
        assert data["environment_error"] == "pollen: timeout"
        services = {service["service"]: service for service in data["services"]}
        assert services["garmin"]["label"] == "Garmin"
        assert services["environment"]["label"] == "Environment / Pollen"


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
    async def test_post_environment_returns_200_with_message(self, async_session):
        """POST /api/sync/environment should return 200 immediately."""
        app = _make_test_app(async_session)
        with patch("app.api.sync._run_environment_sync_in_background", new_callable=AsyncMock):
            with TestClient(app) as client:
                resp = client.post("/api/sync/environment?date_param=2025-01-28")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Environment sync started"
        assert data["date"] == "2025-01-28"

    @pytest.mark.asyncio
    async def test_environment_background_logs_partial_when_pollen_fails_after_light_rows(self, async_session, monkeypatch):
        class FakeSyncService:
            async def sync_environment_day(self, target_date, session):
                return {
                    "date": target_date.isoformat(),
                    "success": False,
                    "skipped": False,
                    "errors": ["pollen: timeout"],
                    "counts": {"environmental_metrics": 4},
                }

        monkeypatch.setattr("app.api.sync._get_environment_sync_service", lambda: FakeSyncService())

        from app.api.sync import _run_environment_sync_in_background

        await _run_environment_sync_in_background(date(2025, 1, 28), async_session)

        result = await async_session.execute(select(SyncLog))
        log = result.scalar_one()
        assert log.sync_type == "environment"
        assert log.status == "partial"
        assert log.error_message == "pollen: timeout"

    @pytest.mark.asyncio
    async def test_post_habitsync_returns_404(self, async_session):
        """The habitsync endpoint was removed; the path now 404s."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/habitsync?date_param=2025-01-28")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_post_all_returns_200(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/all?date_param=2025-01-28")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_all_defaults_to_app_timezone_today(self, async_session):
        app = _make_test_app(async_session)
        with patch("app.api.sync._today_in_app_timezone", return_value=date(2026, 4, 12)):
            with TestClient(app) as client:
                resp = client.post("/api/sync/all")

        assert resp.status_code == 200
        assert resp.json()["date"] == "2026-04-12"


class TestSyncBackfill:

    @pytest.mark.asyncio
    async def test_backfill_with_days_parameter(self, async_session):
        app = _make_test_app(async_session)
        with patch("app.api.sync._run_backfill_in_background", new_callable=AsyncMock):
            with TestClient(app) as client:
                resp = client.post("/api/sync/backfill", json={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_days"] == 7
        assert "start_date" in data
        assert "end_date" in data

    @pytest.mark.asyncio
    async def test_backfill_days_ends_at_yesterday_in_app_timezone(self, async_session):
        app = _make_test_app(async_session)
        with patch("app.api.sync._today_in_app_timezone", return_value=date(2026, 4, 12)):
            with patch("app.api.sync._run_backfill_in_background", new_callable=AsyncMock):
                with TestClient(app) as client:
                    resp = client.post("/api/sync/backfill", json={"days": 1})

        assert resp.status_code == 200
        data = resp.json()
        assert data["start_date"] == "2026-04-11"
        assert data["end_date"] == "2026-04-11"

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

    @pytest.mark.asyncio
    async def test_backfill_cancel_when_not_running(self, async_session):
        """Cancel should return 400 when no backfill is running."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.post("/api/sync/backfill/cancel")
        assert resp.status_code == 400
        assert "No backfill is currently running" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_backfill_logs_environment_status_per_day(self, async_session, monkeypatch):
        class FakeSessionMaker:
            def __call__(self):
                return self

            async def __aenter__(self):
                return async_session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSyncService:
            async def sync_day(self, target_date, session):
                return {
                    "date": target_date.isoformat(),
                    "garmin": {
                        "date": target_date.isoformat(),
                        "success": True,
                        "errors": [],
                        "counts": {},
                    },
                    "environment": {
                        "date": target_date.isoformat(),
                        "success": True,
                        "errors": [],
                        "counts": {"environmental_metrics": 4},
                    },
                    "overall_success": True,
                }

        monkeypatch.setattr("app.api.sync._get_sync_service", AsyncMock(return_value=FakeSyncService()))
        monkeypatch.setattr("app.api.sync.async_session_maker", FakeSessionMaker())
        monkeypatch.setattr("app.api.sync.asyncio.sleep", AsyncMock())

        from app.api.sync import _run_backfill_in_background

        await _run_backfill_in_background(date(2025, 1, 28), date(2025, 1, 28))

        result = await async_session.execute(select(SyncLog))
        log = result.scalar_one()
        assert log.sync_type == "backfill"
        assert log.details["environment"]["counts"]["environmental_metrics"] == 4
        assert log.details["overall_success"] is True
