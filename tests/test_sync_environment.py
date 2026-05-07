from datetime import date

import pytest
from sqlalchemy import select
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.models.database import EnvironmentalMetric
from app.services.environmental import EnvironmentalMetricValue, OpenMeteoPollenProvider
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

        async def no_pollen(*args, **kwargs):
            return []

        monkeypatch.setattr(OpenMeteoPollenProvider, "daily_metrics", no_pollen)

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
        pollen_metrics = [
            EnvironmentalMetricValue(
                source="open_meteo_air_quality",
                metric_key="grass_pollen_avg",
                value=2.5,
                unit="grains/m3",
                category="Pollen",
            ),
            EnvironmentalMetricValue(
                source="open_meteo_air_quality",
                metric_key="grass_pollen_max",
                value=4.0,
                unit="grains/m3",
                category="Pollen",
            ),
        ]

        async def get_pollen(*args, **kwargs):
            return pollen_metrics

        monkeypatch.setattr(OpenMeteoPollenProvider, "daily_metrics", get_pollen)

        first = await service.sync_environment_day(date(2026, 5, 1), async_session)
        second = await service.sync_environment_day(date(2026, 5, 1), async_session)

        rows = (
            await async_session.execute(
                select(EnvironmentalMetric).where(EnvironmentalMetric.date == date(2026, 5, 1))
            )
        ).scalars().all()

        assert first["counts"]["environmental_metrics"] == 6
        assert second["counts"]["environmental_metrics"] == 6
        assert len(rows) == 6

    @pytest.mark.asyncio
    async def test_environment_sync_skips_cleanly_without_location(self, async_session, monkeypatch):
        service = _sync_service(monkeypatch, latitude=None, longitude=None)

        result = await service.sync_environment_day(date(2026, 5, 1), async_session)

        assert result["date"] == "2026-05-01"
        assert result["success"] is False
        assert result["skipped"] is True
        assert result["errors"] == ["ENVIRONMENT_LATITUDE and ENVIRONMENT_LONGITUDE must be set"]
        assert result["counts"]["environmental_metrics"] == 0

    @pytest.mark.asyncio
    async def test_environment_sync_writes_light_and_pollen_rows(self, async_session, monkeypatch):
        service = _sync_service(monkeypatch)
        pollen_metrics = [
            EnvironmentalMetricValue(
                source="open_meteo_air_quality",
                metric_key="grass_pollen_avg",
                value=2.5,
                unit="grains/m3",
                category="Pollen",
            ),
            EnvironmentalMetricValue(
                source="open_meteo_air_quality",
                metric_key="grass_pollen_max",
                value=4.0,
                unit="grains/m3",
                category="Pollen",
            ),
        ]

        async def get_pollen(*args, **kwargs):
            return pollen_metrics

        monkeypatch.setattr(OpenMeteoPollenProvider, "daily_metrics", get_pollen)

        result = await service.sync_environment_day(date(2026, 5, 1), async_session)

        rows = (
            await async_session.execute(
                select(EnvironmentalMetric).where(EnvironmentalMetric.date == date(2026, 5, 1))
            )
        ).scalars().all()

        assert result["success"] is True
        assert result["errors"] == []
        assert result["counts"]["environmental_metrics"] == 6
        assert {row.category for row in rows} == {"Light", "Pollen"}
        assert "grass_pollen_avg" in {row.metric_key for row in rows}

    @pytest.mark.asyncio
    async def test_environment_sync_keeps_light_rows_when_pollen_fails(self, async_session, monkeypatch):
        service = _sync_service(monkeypatch)

        async def fail_pollen(*args, **kwargs):
            raise RuntimeError("Open-Meteo unavailable")

        monkeypatch.setattr(OpenMeteoPollenProvider, "daily_metrics", fail_pollen)

        result = await service.sync_environment_day(date(2026, 5, 1), async_session)

        rows = (
            await async_session.execute(
                select(EnvironmentalMetric).where(EnvironmentalMetric.date == date(2026, 5, 1))
            )
        ).scalars().all()

        assert result["success"] is False
        assert result["errors"] == ["pollen: Open-Meteo unavailable"]
        assert result["counts"]["environmental_metrics"] == 4
        assert len(rows) == 4
        assert {row.category for row in rows} == {"Light"}


class TestOpenMeteoPollenProvider:
    @pytest.mark.asyncio
    async def test_parses_hourly_response_into_daily_avg_and_max(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "latitude": 51.5,
                    "longitude": -0.1,
                    "timezone": "Europe/London",
                    "hourly_units": {"grass_pollen": "grains/m3"},
                    "hourly": {
                        "time": ["2026-05-01T00:00", "2026-05-01T01:00", "2026-05-01T02:00"],
                        "grass_pollen": [1.0, 2.0, 4.0],
                        "birch_pollen": [None, 3.0, None],
                    },
                }

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, params):
                captured["url"] = url
                captured["params"] = params
                return FakeResponse()

        provider = OpenMeteoPollenProvider(client_factory=lambda: FakeClient())

        metrics = await provider.daily_metrics(date(2026, 5, 1), ZoneInfo("Europe/London"), 51.5074, -0.1278)

        by_key = {metric.metric_key: metric for metric in metrics}
        assert by_key["grass_pollen_avg"].value == pytest.approx(7 / 3, abs=0.0001)
        assert by_key["grass_pollen_max"].value == 4.0
        assert by_key["birch_pollen_avg"].value == 3.0
        assert by_key["birch_pollen_max"].value == 3.0
        assert by_key["grass_pollen_avg"].raw_metadata["provider_params"] == captured["params"]
        assert by_key["grass_pollen_avg"].raw_metadata["hourly_unit"] == "grains/m3"

    @pytest.mark.asyncio
    async def test_omits_all_null_pollen_series(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "latitude": 51.5,
                    "longitude": -0.1,
                    "timezone": "Europe/London",
                    "hourly_units": {"grass_pollen": "grains/m3"},
                    "hourly": {
                        "time": ["2026-05-01T00:00", "2026-05-01T01:00"],
                        "grass_pollen": [None, None],
                        "birch_pollen": [None, None],
                    },
                }

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, params):
                return FakeResponse()

        provider = OpenMeteoPollenProvider(client_factory=lambda: FakeClient())

        metrics = await provider.daily_metrics(date(2026, 5, 1), ZoneInfo("Europe/London"), 51.5074, -0.1278)

        assert metrics == []
