from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.models.database import (
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
)
from app.services.home_assistant import HomeAssistantClient, HomeAssistantSyncService


def _client_factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        return httpx.AsyncClient(transport=transport, **kwargs)

    return factory


@pytest.mark.asyncio
async def test_client_discovers_entities_and_uses_bearer_token():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert request.url.path == "/api/states"
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "sensor.bedroom_temperature",
                    "state": "19.5",
                    "attributes": {
                        "friendly_name": "Bedroom temperature",
                        "device_class": "temperature",
                        "unit_of_measurement": "°C",
                    },
                },
                {
                    "entity_id": "light.bedroom",
                    "state": "off",
                    "attributes": {"friendly_name": "Bedroom light"},
                },
            ],
        )

    client = HomeAssistantClient(
        "http://homeassistant.local:8123/",
        "secret-token",
        client_factory=_client_factory(handler),
    )

    entities = await client.discover_entities()

    assert entities == [
        {
            "entity_id": "sensor.bedroom_temperature",
            "display_name": "Bedroom temperature",
            "device_class": "temperature",
            "unit": "°C",
            "state": "19.5",
        }
    ]


@pytest.mark.asyncio
async def test_history_sync_is_idempotent_and_advances_watermark(async_session):
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        assert request.url.path.startswith("/api/history/period/")
        assert request.url.params["filter_entity_id"] == "sensor.bedroom_temperature"
        assert "minimal_response" in request.url.params
        assert "no_attributes" in request.url.params
        return httpx.Response(
            200,
            json=[
                [
                    {
                        "entity_id": "sensor.bedroom_temperature",
                        "state": "19.5",
                        "last_changed": "2026-09-19T22:00:00+00:00",
                        "attributes": {"unit_of_measurement": "°C"},
                    },
                    {
                        "state": "19.0",
                        "last_changed": "2026-09-20T01:00:00+00:00",
                    },
                    {
                        "state": "unavailable",
                        "last_changed": "2026-09-20T02:00:00+00:00",
                    },
                ]
            ],
        )

    connection = HomeAssistantConnection(
        name="Home",
        base_url="http://homeassistant.local:8123",
        encrypted_token="encrypted-token",
        enabled=True,
    )
    async_session.add(connection)
    await async_session.flush()
    entity = HomeAssistantEntity(
        connection_id=connection.id,
        entity_id="sensor.bedroom_temperature",
        display_name="Bedroom temperature",
        device_class="temperature",
        source_unit="°C",
        role="bedroom_temperature",
        enabled=True,
    )
    async_session.add(entity)
    await async_session.commit()

    service = HomeAssistantSyncService(
        client_factory=_client_factory(handler),
        decrypt_token=lambda value: "secret-token",
    )
    start = datetime(2026, 9, 19, 21, tzinfo=timezone.utc)
    end = datetime(2026, 9, 20, 6, tzinfo=timezone.utc)

    first = await service.sync_connection(async_session, connection.id, start=start, end=end)
    second = await service.sync_connection(async_session, connection.id, start=start, end=end)

    count = await async_session.scalar(select(func.count(HomeAssistantObservation.id)))
    unavailable = await async_session.scalar(
        select(HomeAssistantObservation).where(HomeAssistantObservation.state == "unavailable")
    )
    await async_session.refresh(connection)

    assert first["observations"] == 3
    assert second["observations"] == 3
    assert count == 3
    assert unavailable.numeric_value is None
    assert connection.last_successful_sync_at == end.replace(tzinfo=None)
    assert len(requests) == 2


def test_client_rejects_urls_with_embedded_credentials():
    with pytest.raises(ValueError, match="URL"):
        HomeAssistantClient("http://admin:password@homeassistant.local:8123", "token")
