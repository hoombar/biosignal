"""Tests for export API endpoints.

Seeds in-memory DB with known data, tests:
- GET /api/export?format=csv → valid CSV with date column
- GET /api/export?format=json → valid JSON array
- GET /api/export/metadata → feature definitions present
- Date range filtering works
"""

import csv
import io
import json
import pytest
from datetime import date, datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.export import router
from app.core.database import get_db
from app.models.database import SleepSession


def _make_test_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def utc_dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute)


class TestExportFeatures:

    @pytest.mark.asyncio
    async def test_csv_export_has_date_column(self, async_session):
        """CSV export should have a 'date' column."""
        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            sleep_start=utc_dt(2025, 1, 28, 0, 0),
            sleep_end=utc_dt(2025, 1, 28, 7, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=78,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "csv", "start": "2025-01-28", "end": "2025-01-28"}
            )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1
        assert "date" in rows[0]
        assert rows[0]["date"] == "2025-01-28"

    @pytest.mark.asyncio
    async def test_csv_includes_sleep_features(self, async_session):
        """CSV export should include computed sleep features when data exists."""
        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            sleep_start=utc_dt(2025, 1, 28, 0, 0),
            sleep_end=utc_dt(2025, 1, 28, 8, 0),
            total_sleep_seconds=7 * 3600,
            sleep_score=80,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "csv", "start": "2025-01-28", "end": "2025-01-28"}
            )

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1
        assert "sleep_hours" in rows[0]
        assert rows[0]["sleep_hours"] != ""
        assert float(rows[0]["sleep_hours"]) == pytest.approx(7.0)

    @pytest.mark.asyncio
    async def test_json_export_returns_array(self, async_session):
        """JSON export should return a list of dicts."""
        async_session.add(SleepSession(
            date=date(2025, 1, 27),
            total_sleep_seconds=7 * 3600,
            sleep_score=75,
        ))
        async_session.add(SleepSession(
            date=date(2025, 1, 28),
            total_sleep_seconds=8 * 3600,
            sleep_score=82,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "json", "start": "2025-01-27", "end": "2025-01-28"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        dates = {d["date"] for d in data}
        assert "2025-01-27" in dates
        assert "2025-01-28" in dates

    @pytest.mark.asyncio
    async def test_date_range_filtering(self, async_session):
        """Export should only return data within the specified date range."""
        for d, score in [(date(2025, 1, 26), 70), (date(2025, 1, 27), 75), (date(2025, 1, 28), 80)]:
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=7 * 3600,
                sleep_score=score,
            ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "json", "start": "2025-01-27", "end": "2025-01-28"}
            )

        body = resp.json()
        data = body["data"]
        assert len(data) == 2
        assert all(d["date"] in ("2025-01-27", "2025-01-28") for d in data)

    @pytest.mark.asyncio
    async def test_csv_content_disposition_header(self, async_session):
        """CSV export should set Content-Disposition for download."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "csv", "start": "2025-01-28", "end": "2025-01-28"}
            )
        assert "attachment" in resp.headers.get("content-disposition", "")


class TestExportMetadata:

    @pytest.mark.asyncio
    async def test_metadata_returns_feature_definitions(self, async_session):
        """Metadata endpoint returns feature definitions."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        assert resp.status_code == 200
        data = resp.json()
        assert "features" in data
        features = data["features"]
        assert "sleep_hours" in features
        assert "stress_morning_avg" in features
        assert "bb_daily_min" in features  # bb_2pm was removed (phantom field not in DailySummary)

    @pytest.mark.asyncio
    async def test_metadata_feature_has_required_fields(self, async_session):
        """Each feature definition should have description, unit, category."""
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        data = resp.json()
        sleep_hours = data["features"]["sleep_hours"]
        assert "description" in sleep_hours
        assert "unit" in sleep_hours
        assert "category" in sleep_hours
