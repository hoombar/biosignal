from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.models.database import (
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
)
from app.services.features import compute_home_assistant_features


async def _add_entity(async_session, entity_id, name, device_class, unit, observations):
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
        entity_id=entity_id,
        display_name=name,
        device_class=device_class,
        source_unit=unit,
        role=None,
        enabled=True,
    )
    async_session.add(entity)
    await async_session.flush()
    async_session.add_all([
        HomeAssistantObservation(
            entity_id=entity.id,
            observed_at=timestamp,
            state=str(value),
            numeric_value=value if isinstance(value, (int, float)) else None,
            source_unit=unit,
        )
        for timestamp, value in observations
    ])


@pytest.mark.asyncio
async def test_summarizes_arbitrary_entities_over_dst_local_day(async_session):
    await _add_entity(
        async_session,
        "sensor.attic_temperature",
        "Attic temperature",
        None,
        "°F",
        [
            (datetime(2026, 3, 28, 23), 50.0),
            (datetime(2026, 3, 29, 11), 68.0),
        ],
    )
    await _add_entity(
        async_session,
        "binary_sensor.garage_door",
        "Garage door",
        "door",
        None,
        [
            (datetime(2026, 3, 28, 23), "off"),
            (datetime(2026, 3, 29, 10, 30), "on"),
        ],
    )
    await async_session.commit()

    result = await compute_home_assistant_features(
        async_session, date(2026, 3, 29), ZoneInfo("Europe/London")
    )

    by_selector = {item["selector"]: item for item in result["home_assistant_metrics"]}
    temperature = by_selector["home_assistant:sensor.attic_temperature"]
    assert temperature["value"] == pytest.approx((10 * 11 + 20 * 12) / 23)
    assert temperature["min"] == 10.0
    assert temperature["max"] == 20.0
    assert temperature["coverage_pct"] == 100.0
    assert temperature["unit"] == "degC"
    door = by_selector["home_assistant:binary_sensor.garage_door"]
    assert door["value"] == pytest.approx(12.5 / 23)
    assert door["min"] == 0.0
    assert door["max"] == 1.0


@pytest.mark.asyncio
async def test_daily_summary_reports_partial_coverage_and_carries_forward(async_session):
    await _add_entity(
        async_session,
        "sensor.water_tank",
        "Water tank",
        None,
        "L",
        [
            (datetime(2026, 9, 20, 6), 100.0),
            (datetime(2026, 9, 20, 18), "unavailable"),
        ],
    )
    await async_session.commit()

    result = await compute_home_assistant_features(
        async_session, date(2026, 9, 20), ZoneInfo("UTC")
    )

    metric = result["home_assistant_metrics"][0]
    assert metric["value"] == 100.0
    assert metric["coverage_pct"] == 50.0
    assert metric["unit"] == "L"
