from datetime import date, datetime, timezone

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.models.database import (
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
)
from app.models.sync_log import SyncLog


def _make_test_app(session):
    from app.api.home_assistant import router

    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.mark.asyncio
async def test_connection_setup_encrypts_token_and_never_returns_it(
    async_session, monkeypatch
):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", key)
    get_settings.cache_clear()

    async def fake_config(self):
        return {"time_zone": "Europe/London", "location_name": "Home"}

    monkeypatch.setattr("app.api.home_assistant.HomeAssistantClient.config", fake_config)
    app = _make_test_app(async_session)
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/home-assistant/connection",
                json={
                    "name": "Home",
                    "base_url": "http://homeassistant.local:8123/",
                    "token": "long-lived-token",
                },
            )

        assert response.status_code == 200
        assert response.json()["base_url"] == "http://homeassistant.local:8123"
        assert response.json()["token_configured"] is True
        assert "token" not in response.json()

        connection = await async_session.scalar(select(HomeAssistantConnection))
        assert connection.encrypted_token != "long-lived-token"
        assert connection.ha_timezone == "Europe/London"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_discovery_and_entity_selection(async_session, monkeypatch):
    connection = HomeAssistantConnection(
        name="Home",
        base_url="http://homeassistant.local:8123",
        encrypted_token="encrypted",
        enabled=True,
    )
    async_session.add(connection)
    await async_session.commit()

    monkeypatch.setattr(
        "app.api.home_assistant.decrypt_secret", lambda value: "decrypted-token"
    )

    async def fake_discovery(self):
        assert self.token == "decrypted-token"
        return [
            {
                "entity_id": "sensor.bedroom_temperature",
                "display_name": "Bedroom temperature",
                "device_class": "temperature",
                "unit": "°C",
                "state": "19.5",
            }
        ]

    monkeypatch.setattr(
        "app.api.home_assistant.HomeAssistantClient.discover_entities", fake_discovery
    )
    app = _make_test_app(async_session)

    with TestClient(app) as client:
        discovered = client.get("/api/home-assistant/entities/discover")
        saved = client.put(
            "/api/home-assistant/entities",
            json={
                "entities": [
                    {
                        "entity_id": "sensor.bedroom_temperature",
                        "display_name": "Bedroom temperature",
                        "device_class": "temperature",
                        "source_unit": "°C",
                        "role": "bedroom_temperature",
                    }
                ]
            },
        )

    assert discovered.status_code == 200
    assert discovered.json()[0]["entity_id"] == "sensor.bedroom_temperature"
    assert saved.status_code == 200
    assert saved.json()[0]["role"] == "bedroom_temperature"
    entity = await async_session.scalar(select(HomeAssistantEntity))
    assert entity.enabled is True


def test_backfill_date_starts_at_midnight_in_app_timezone(monkeypatch):
    from app.api.home_assistant import _sync_start

    monkeypatch.setenv("TZ", "America/New_York")
    get_settings.cache_clear()
    try:
        assert _sync_start(date(2026, 7, 1)) == datetime(
            2026, 7, 1, 4, tzinfo=timezone.utc
        )
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_manual_sync_records_service_log(async_session, monkeypatch):
    connection = HomeAssistantConnection(
        name="Home",
        base_url="http://homeassistant.local:8123",
        encrypted_token="encrypted",
        enabled=True,
    )
    async_session.add(connection)
    await async_session.commit()

    async def fake_sync(self, session, connection_id, start=None, end=None):
        return {
            "connection_id": connection_id,
            "start": "2026-09-20T00:00:00Z",
            "end": "2026-09-20T06:10:00Z",
            "entities": 2,
            "observations": 12,
        }

    monkeypatch.setattr(
        "app.api.home_assistant.HomeAssistantSyncService.sync_connection", fake_sync
    )
    app = _make_test_app(async_session)
    with TestClient(app) as client:
        response = client.post("/api/home-assistant/sync", json={})

    assert response.status_code == 200
    log = await async_session.scalar(select(SyncLog))
    assert log.sync_type == "home_assistant"
    assert log.status == "success"
    assert log.details["observations"] == 12


@pytest.mark.asyncio
async def test_changing_connection_url_requires_new_token(async_session, monkeypatch):
    connection = HomeAssistantConnection(
        name="Home",
        base_url="http://homeassistant.local:8123",
        encrypted_token="encrypted",
        enabled=True,
    )
    async_session.add(connection)
    await async_session.commit()
    app = _make_test_app(async_session)

    with TestClient(app) as client:
        response = client.put(
            "/api/home-assistant/connection",
            json={"name": "Home", "base_url": "https://attacker.example"},
        )

    assert response.status_code == 422
    assert "new token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_replace_instance_or_sensor_mapping_after_history_import(
    async_session, monkeypatch
):
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
        entity_id="sensor.bedroom_temperature",
        display_name="Bedroom temperature",
        device_class="temperature",
        source_unit="°C",
        role="bedroom_temperature",
        enabled=True,
    )
    async_session.add(entity)
    await async_session.flush()
    async_session.add(
        HomeAssistantObservation(
            entity_id=entity.id,
            observed_at=datetime(2026, 9, 20, 1),
            state="19",
            numeric_value=19,
            source_unit="°C",
        )
    )
    await async_session.commit()

    async def fake_config(self):
        return {"time_zone": "Europe/London"}

    monkeypatch.setattr("app.api.home_assistant.HomeAssistantClient.config", fake_config)
    monkeypatch.setattr("app.api.home_assistant.encrypt_secret", lambda value: "new-encrypted")
    app = _make_test_app(async_session)
    with TestClient(app) as client:
        changed_instance = client.put(
            "/api/home-assistant/connection",
            json={
                "name": "Other",
                "base_url": "http://other-home-assistant.local:8123",
                "token": "new-token",
            },
        )
        changed_mapping = client.put(
            "/api/home-assistant/entities", json={"entities": []}
        )

    assert changed_instance.status_code == 409
    assert changed_mapping.status_code == 409


@pytest.mark.asyncio
async def test_entity_selection_rejects_duplicate_ids(async_session):
    async_session.add(
        HomeAssistantConnection(
            name="Home",
            base_url="http://homeassistant.local:8123",
            encrypted_token="encrypted",
            enabled=True,
        )
    )
    await async_session.commit()
    app = _make_test_app(async_session)
    duplicate = {
        "entity_id": "sensor.shared",
        "display_name": "Shared",
        "device_class": "temperature",
        "source_unit": "°C",
    }
    with TestClient(app) as client:
        response = client.put(
            "/api/home-assistant/entities",
            json={
                "entities": [
                    {**duplicate, "role": "bedroom_temperature"},
                    {**duplicate, "role": "bedroom_humidity"},
                ]
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_connection_setup_reports_rejected_token(async_session, monkeypatch):
    async def rejected_config(self):
        request = httpx.Request("GET", "http://homeassistant.local:8123/api/config")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("app.api.home_assistant.HomeAssistantClient.config", rejected_config)
    app = _make_test_app(async_session)
    with TestClient(app) as client:
        response = client.put(
            "/api/home-assistant/connection",
            json={
                "name": "Home",
                "base_url": "http://homeassistant.local:8123",
                "token": "invalid-token",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Home Assistant rejected the access token"


@pytest.mark.asyncio
async def test_connection_setup_reports_unreachable_host(async_session, monkeypatch):
    async def failed_config(self):
        request = httpx.Request("GET", "http://homeassistant.local:8123/api/config")
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr("app.api.home_assistant.HomeAssistantClient.config", failed_config)
    app = _make_test_app(async_session)
    with TestClient(app) as client:
        response = client.put(
            "/api/home-assistant/connection",
            json={
                "name": "Home",
                "base_url": "http://homeassistant.local:8123",
                "token": "token",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not connect to Home Assistant; check the URL and network"
