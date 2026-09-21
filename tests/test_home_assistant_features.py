from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.models.database import (
    EnvironmentalMetric,
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
    SleepSession,
)
from app.services.features import compute_daily_features, compute_home_assistant_features


async def _add_sensor(async_session, role, unit, observations):
    connection = await async_session.get(HomeAssistantConnection, 1)
    if connection is None:
        connection = HomeAssistantConnection(
            name="Home",
            base_url="http://homeassistant.local:8123",
            encrypted_token="encrypted",
            enabled=True,
        )
        async_session.add(connection)
        await async_session.flush()
    entity = HomeAssistantEntity(
        connection_id=connection.id,
        entity_id=f"sensor.{role}",
        display_name=role.replace("_", " ").title(),
        device_class="temperature" if "temperature" in role else "humidity",
        source_unit=unit,
        role=role,
        enabled=True,
    )
    async_session.add(entity)
    await async_session.flush()
    async_session.add_all(
        [
            HomeAssistantObservation(
                entity_id=entity.id,
                observed_at=timestamp,
                state=str(value),
                numeric_value=value if isinstance(value, (int, float)) else None,
                source_unit=unit,
            )
            for timestamp, value in observations
        ]
    )


@pytest.mark.asyncio
async def test_duration_weights_bedroom_readings_over_exact_sleep_window(async_session):
    target_date = date(2026, 9, 20)
    async_session.add(
        SleepSession(
            date=target_date,
            sleep_start=datetime(2026, 9, 19, 22),
            sleep_end=datetime(2026, 9, 20, 6),
            total_sleep_seconds=8 * 3600,
        )
    )
    await _add_sensor(
        async_session,
        "bedroom_temperature",
        "°C",
        [
            (datetime(2026, 9, 19, 21), 20.0),
            (datetime(2026, 9, 19, 23), 18.0),
            (datetime(2026, 9, 20, 3), 19.0),
            (datetime(2026, 9, 20, 7), 21.0),
        ],
    )
    await _add_sensor(
        async_session,
        "bedroom_humidity",
        "%",
        [
            (datetime(2026, 9, 19, 21), 50.0),
            (datetime(2026, 9, 20, 2), 60.0),
        ],
    )
    await async_session.commit()

    result = await compute_home_assistant_features(
        async_session, target_date, ZoneInfo("Europe/London")
    )

    assert result["bedroom_temperature_sleep_avg"] == pytest.approx(18.625)
    assert result["bedroom_temperature_sleep_min"] == 18.0
    assert result["bedroom_temperature_sleep_max"] == 20.0
    assert result["bedroom_temperature_sleep_range"] == 2.0
    assert result["bedroom_temperature_sleep_coverage_pct"] == 100.0
    assert result["bedroom_humidity_sleep_avg"] == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_omits_exposure_below_minimum_coverage(async_session):
    target_date = date(2026, 9, 20)
    async_session.add(
        SleepSession(
            date=target_date,
            sleep_start=datetime(2026, 9, 19, 22),
            sleep_end=datetime(2026, 9, 20, 6),
            total_sleep_seconds=8 * 3600,
        )
    )
    await _add_sensor(
        async_session,
        "bedroom_temperature",
        "°C",
        [
            (datetime(2026, 9, 19, 21), 20.0),
            (datetime(2026, 9, 19, 23), "unavailable"),
            (datetime(2026, 9, 20, 1), 18.0),
            (datetime(2026, 9, 20, 5), "unavailable"),
        ],
    )
    await async_session.commit()

    result = await compute_home_assistant_features(
        async_session, target_date, ZoneInfo("Europe/London")
    )

    assert result["bedroom_temperature_sleep_coverage_pct"] == 62.5
    assert "bedroom_temperature_sleep_avg" not in result


@pytest.mark.asyncio
async def test_daily_features_include_indoor_outdoor_sleep_temperature_delta(
    async_session, monkeypatch
):
    target_date = date(2026, 9, 20)
    async_session.add(
        SleepSession(
            date=target_date,
            sleep_start=datetime(2026, 9, 19, 22),
            sleep_end=datetime(2026, 9, 20, 6),
            total_sleep_seconds=8 * 3600,
        )
    )
    await _add_sensor(
        async_session,
        "bedroom_temperature",
        "°C",
        [(datetime(2026, 9, 19, 21), 19.0)],
    )
    async_session.add(
        EnvironmentalMetric(
            date=target_date,
            source="open_meteo",
            metric_key="temperature_2m_overnight_mean",
            location_key="51.5000,-0.1000",
            value=24.0,
            unit="degC",
            category="Weather",
        )
    )
    await async_session.commit()

    monkeypatch.setenv("ENVIRONMENT_LATITUDE", "51.5")
    monkeypatch.setenv("ENVIRONMENT_LONGITUDE", "-0.1")
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        result = await compute_daily_features(
            async_session, target_date, "Europe/London"
        )
    finally:
        get_settings.cache_clear()

    assert result["bedroom_temperature_sleep_avg"] == 19.0
    assert result["bedroom_outdoor_sleep_temperature_delta"] == -5.0
