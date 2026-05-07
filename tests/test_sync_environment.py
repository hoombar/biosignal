from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models.database import EnvironmentalMetric
from app.services.garmin import GarminClient
from app.services.sync import SyncService


def _sync_service(monkeypatch, latitude: str | None = "51.5074", longitude: str | None = "-0.1278") -> SyncService:
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    if latitude is None:
        monkeypatch.delenv("ENVIRONMENT_LATITUDE", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT_LATITUDE", latitude)
    if longitude is None:
        monkeypatch.delenv("ENVIRONMENT_LONGITUDE", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT_LONGITUDE", longitude)
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.sync.get_settings",
        lambda: Settings(
            garmin_email="user@example.com",
            garmin_password="secret",
            environment_latitude=float(latitude) if latitude is not None else None,
            environment_longitude=float(longitude) if longitude is not None else None,
            _env_file=None,
        ),
    )

    garmin = GarminClient("user@example.com", "secret", "/tmp/tokens")
    return SyncService(garmin, "Europe/London")


class TestEnvironmentSync:
    @pytest.mark.asyncio
    async def test_environment_sync_writes_light_rows_for_configured_location(self, async_session, monkeypatch):
        service = _sync_service(monkeypatch)

        result = await service.sync_environment_day(date(2026, 5, 1), async_session)

        assert result["date"] == "2026-05-01"
        assert result["success"] is True
        assert result["errors"] == []
        assert result["counts"]["environmental_metrics"] == 4

        rows = (
            await async_session.execute(
                select(EnvironmentalMetric).where(EnvironmentalMetric.date == date(2026, 5, 1))
            )
        ).scalars().all()

        assert len(rows) == 4
        assert {row.category for row in rows} == {"Light"}
        assert {row.metric_key for row in rows} == {
            "daylight_minutes",
            "sunrise_minutes_after_midnight",
            "sunset_minutes_after_midnight",
            "solar_noon_minutes_after_midnight",
        }

    @pytest.mark.asyncio
    async def test_environment_sync_is_idempotent_for_same_day(self, async_session, monkeypatch):
        service = _sync_service(monkeypatch)

        first = await service.sync_environment_day(date(2026, 5, 1), async_session)
        second = await service.sync_environment_day(date(2026, 5, 1), async_session)

        rows = (
            await async_session.execute(
                select(EnvironmentalMetric).where(EnvironmentalMetric.date == date(2026, 5, 1))
            )
        ).scalars().all()

        assert first["counts"]["environmental_metrics"] == 4
        assert second["counts"]["environmental_metrics"] == 4
        assert len(rows) == 4

    @pytest.mark.asyncio
    async def test_environment_sync_skips_cleanly_without_location(self, async_session, monkeypatch):
        service = _sync_service(monkeypatch, latitude=None, longitude=None)

        result = await service.sync_environment_day(date(2026, 5, 1), async_session)

        assert result["date"] == "2026-05-01"
        assert result["success"] is False
        assert result["skipped"] is True
        assert result["errors"] == ["ENVIRONMENT_LATITUDE and ENVIRONMENT_LONGITUDE must be set"]
        assert result["counts"]["environmental_metrics"] == 0
