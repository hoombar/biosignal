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
import zipfile
import pytest
from datetime import date, datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.export import router
from app.core.config import get_settings
from app.core.database import get_db
from app.models.database import EnvironmentalMetric, HomeAssistantConnection, HomeAssistantEntity, HomeAssistantObservation, SleepSession, DailyHabit, HabitDisplayConfig, SupplementLog, SupplementPlanVersion
from app.services.environmental import location_key


def _make_test_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def utc_dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute)


def configured_environment_location_key() -> str:
    settings = get_settings()
    if settings.environment_latitude is None or settings.environment_longitude is None:
        return "51.5074,-0.1278"
    return location_key(settings.environment_latitude, settings.environment_longitude)


class TestExportFeatures:

    @pytest.mark.asyncio
    async def test_full_export_returns_zip_download(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/full")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")
        assert "attachment" in resp.headers["content-disposition"]
        assert "biosignal_full_export_" in resp.headers["content-disposition"]
        assert resp.headers["cache-control"] == "no-store"
        with zipfile.ZipFile(io.BytesIO(resp.content)) as bundle:
            assert "manifest.json" in bundle.namelist()

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

    @pytest.mark.asyncio
    async def test_csv_export_flattens_habit_values(self, async_session):
        """CSV export should expose habit values as stable numeric columns."""
        from tests.conftest import log_habit

        await log_habit(async_session, "coffee", date(2025, 1, 28), 4, habit_type="counter")
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
        assert "habit_coffee" in rows[0]
        assert rows[0]["habit_coffee"] == "4"

    @pytest.mark.asyncio
    async def test_json_export_preserves_nested_habits_and_adds_flat_values(self, async_session):
        """JSON export should keep existing nested habits while adding habit_* analysis columns."""
        from tests.conftest import log_habit

        await log_habit(async_session, "coffee", date(2025, 1, 28), 4, habit_type="counter")
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "json", "start": "2025-01-28", "end": "2025-01-28"}
            )

        row = resp.json()["data"][0]
        assert row["habit_coffee"] == 4
        assert row["habits"] == [{"name": "coffee", "value": 4, "type": "counter"}]

    @pytest.mark.asyncio
    async def test_json_export_includes_weather_metrics(self, async_session):
        async_session.add(EnvironmentalMetric(
            date=date(2025, 1, 28),
            source="open_meteo_weather",
            metric_key="temperature_2m_avg",
            location_key=configured_environment_location_key(),
            value=18.5,
            unit="degC",
            category="Weather",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "json", "start": "2025-01-28", "end": "2025-01-28"}
            )

        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["temperature_2m_avg"] == 18.5

    @pytest.mark.asyncio
    async def test_csv_export_includes_weather_metrics(self, async_session):
        async_session.add(EnvironmentalMetric(
            date=date(2025, 1, 28),
            source="open_meteo_weather",
            metric_key="wind_speed_10m_max",
            location_key=configured_environment_location_key(),
            value=31.0,
            unit="km/h",
            category="Weather",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "csv", "start": "2025-01-28", "end": "2025-01-28"}
            )

        reader = csv.DictReader(io.StringIO(resp.text))
        row = list(reader)[0]
        assert row["wind_speed_10m_max"] == "31.0"

    @pytest.mark.asyncio
    async def test_json_export_includes_sustained_exposure_features(self, async_session):
        target_date = date(2025, 1, 28)
        rows = []
        for offset, pollen, daytime, overnight in (
            (3, 10.0, 24.0, 14.0),
            (2, 20.0, 27.0, 16.0),
            (1, 30.0, 30.0, 18.0),
        ):
            for metric_key, value, unit, category in (
                ("grass_pollen_avg", pollen, "grains/m3", "Pollen"),
                ("temperature_2m_daytime_max", daytime, "degC", "Weather"),
                ("temperature_2m_overnight_mean", overnight, "degC", "Weather"),
            ):
                rows.append(EnvironmentalMetric(
                    date=target_date - timedelta(days=offset),
                    source="open_meteo",
                    metric_key=metric_key,
                    location_key=configured_environment_location_key(),
                    value=value,
                    unit=unit,
                    category=category,
                ))
        async_session.add_all(rows)
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get(
                "/api/export",
                params={"format": "json", "start": target_date, "end": target_date},
            )

        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["grass_pollen_prior_3d_avg"] == 20.0
        assert row["overall_pollen_prior_3d_avg"] == 20.0
        assert row["temperature_daytime_max_prior_3d_avg"] == 27.0
        assert row["temperature_overnight_mean_prior_3d_avg"] == 16.0


class TestExportMetadata:

    @pytest.mark.asyncio
    async def test_metadata_includes_selected_home_assistant_entities(self, async_session):
        connection = HomeAssistantConnection(
            name="Home", base_url="http://homeassistant.local:8123",
            encrypted_token="encrypted", enabled=True,
        )
        async_session.add(connection)
        await async_session.flush()
        async_session.add(HomeAssistantEntity(
            connection_id=connection.id, entity_id="sensor.air_quality",
            display_name="Air quality", device_class="aqi", source_unit="AQI",
            role=None, enabled=True,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        metadata = resp.json()["features"]["home_assistant:sensor.air_quality"]
        assert metadata == {
            "description": "Air quality",
            "unit": "AQI",
            "category": "Home Assistant",
            "entity_id": "sensor.air_quality",
            "device_class": "aqi",
        }

    @pytest.mark.asyncio
    async def test_csv_flattens_home_assistant_daily_values(self, async_session):
        connection = HomeAssistantConnection(
            name="Home", base_url="http://homeassistant.local:8123",
            encrypted_token="encrypted", enabled=True,
        )
        async_session.add(connection)
        await async_session.flush()
        entity = HomeAssistantEntity(
            connection_id=connection.id, entity_id="sensor.air_quality",
            display_name="Air quality", device_class="aqi", source_unit="AQI",
            role=None, enabled=True,
        )
        async_session.add(entity)
        await async_session.flush()
        async_session.add(HomeAssistantObservation(
            entity_id=entity.id, observed_at=datetime(2025, 1, 27, 23),
            state="40", numeric_value=40, source_unit="AQI",
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export", params={
                "format": "csv", "start": "2025-01-28", "end": "2025-01-28"
            })

        row = list(csv.DictReader(io.StringIO(resp.text)))[0]
        assert row["home_assistant:sensor.air_quality"] == "40.0"

    @pytest.mark.asyncio
    async def test_metadata_includes_surface_pressure_and_condition(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        assert resp.status_code == 200
        features = resp.json()["features"]
        assert "surface_pressure_avg" in features
        assert "surface_pressure_min" in features
        assert "surface_pressure_max" in features
        assert "weather_code_mode" in features

    @pytest.mark.asyncio
    async def test_metadata_includes_sustained_pollen_and_heat_features(self, async_session):
        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        assert resp.status_code == 200
        features = resp.json()["features"]
        assert features["grass_pollen_prior_3d_avg"]["category"] == "Pollen"
        assert features["overall_pollen_prior_7d_avg"]["unit"] == "grains/m3"
        assert features["temperature_daytime_max_prior_3d_avg"]["category"] == "Weather"
        assert features["temperature_overnight_mean_prior_7d_avg"]["unit"] == "degC"

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
        assert "daylight_minutes" in features
        assert "grass_pollen_avg" in features
        assert "temperature_2m_avg" in features
        assert "relative_humidity_2m_avg" in features
        assert "gym_had_session" in features
        assert features["daylight_minutes"]["category"] == "Light"
        assert features["grass_pollen_avg"]["category"] == "Pollen"
        assert features["temperature_2m_avg"]["category"] == "Weather"
        assert features["gym_had_session"]["category"] == "Gym"

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

    @pytest.mark.asyncio
    async def test_metadata_includes_dynamic_habit_features(self, async_session):
        """Habit feature metadata should be generated from configured habits."""
        from tests.conftest import ensure_habit
        habit = await ensure_habit(async_session, "custom_focus", habit_type="counter")
        habit.is_negative = True
        habit.target_value = 3
        habit.period = "day"
        async_session.add(HabitDisplayConfig(
            habit_name="custom_focus",
            display_name="Focus Session",
            color="#4488ff",
            sort_order=1,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        assert resp.status_code == 200
        features = resp.json()["features"]
        assert "custom_focus" in features
        assert "habit_custom_focus" in features
        assert features["custom_focus"]["category"] == "Habits"
        assert "Focus Session" in features["custom_focus"]["description"]
        assert features["habit_custom_focus"]["target_value"] == 3
        assert features["habit_custom_focus"]["is_negative"] is True
        assert features["habit_custom_focus"]["period"] == "day"

    @pytest.mark.asyncio
    async def test_metadata_includes_dynamic_supplement_features(self, async_session):
        """Supplement metadata should be generated per supplement item."""
        plan = SupplementPlanVersion(
            slot="morning",
            version=1,
            items=[{"name": "Vitamin D", "dose": None, "notes": None}],
        )
        async_session.add(plan)
        await async_session.flush()
        async_session.add(SupplementLog(
            date=date(2026, 5, 1),
            slot="morning",
            plan_version_id=plan.id,
            completed=True,
            snapshot=plan.items,
        ))
        await async_session.commit()

        app = _make_test_app(async_session)
        with TestClient(app) as client:
            resp = client.get("/api/export/metadata")

        assert resp.status_code == 200
        features = resp.json()["features"]
        assert "supplement:vitamin_d" in features
        assert features["supplement:vitamin_d"]["category"] == "Supplements"
        assert features["supplement:vitamin_d"]["description"] == "Supplement: Vitamin D"
