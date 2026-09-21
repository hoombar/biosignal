from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.database import (
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
)


@pytest.mark.asyncio
async def test_home_assistant_observations_are_unique_per_entity_timestamp(async_session):
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

    observed_at = datetime(2026, 9, 20, 1, 30)
    async_session.add_all(
        [
            HomeAssistantObservation(
                entity_id=entity.id,
                observed_at=observed_at,
                state="19.5",
                numeric_value=19.5,
                source_unit="°C",
            ),
            HomeAssistantObservation(
                entity_id=entity.id,
                observed_at=observed_at,
                state="20.0",
                numeric_value=20.0,
                source_unit="°C",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        await async_session.commit()


def test_home_assistant_token_encryption_round_trip(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import get_settings
    from app.services.secrets import decrypt_secret, encrypt_secret

    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()

    try:
        encrypted = encrypt_secret("long-lived-access-token")

        assert encrypted != "long-lived-access-token"
        assert "long-lived-access-token" not in encrypted
        assert decrypt_secret(encrypted) == "long-lived-access-token"
    finally:
        get_settings.cache_clear()


def test_home_assistant_token_encryption_requires_key(monkeypatch):
    from app.core.config import get_settings
    from app.services.secrets import encrypt_secret

    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="INTEGRATION_ENCRYPTION_KEY"):
            encrypt_secret("token")
    finally:
        get_settings.cache_clear()
