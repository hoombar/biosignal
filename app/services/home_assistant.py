"""Home Assistant discovery and timestamped state ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
)
from app.services.secrets import decrypt_secret


ClientFactory = Callable[..., httpx.AsyncClient]


def normalize_base_url(value: str) -> str:
    """Validate and normalize a user-provided Home Assistant base URL."""
    parsed = urlparse(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Home Assistant URL must be an HTTP(S) base URL without credentials")
    return value.strip().rstrip("/")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_timestamp(value: str) -> datetime:
    return _utc_naive(datetime.fromisoformat(value.replace("Z", "+00:00")))


class HomeAssistantClient:
    """Small read-only client for the Home Assistant REST API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client_factory: ClientFactory = httpx.AsyncClient,
    ):
        self.base_url = normalize_base_url(base_url)
        self.token = token
        self.client_factory = client_factory

    def _client(self) -> httpx.AsyncClient:
        return self.client_factory(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
        )

    async def config(self) -> dict:
        async with self._client() as client:
            response = await client.get("/api/config")
            response.raise_for_status()
            return response.json()

    async def discover_entities(self) -> list[dict]:
        async with self._client() as client:
            response = await client.get("/api/states")
            response.raise_for_status()
            states = response.json()

        entities = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith(("sensor.", "binary_sensor.")):
                continue
            attributes = state.get("attributes") or {}
            entities.append(
                {
                    "entity_id": entity_id,
                    "display_name": attributes.get("friendly_name") or entity_id,
                    "device_class": attributes.get("device_class"),
                    "unit": attributes.get("unit_of_measurement"),
                    "state": state.get("state"),
                }
            )
        return sorted(entities, key=lambda item: (item["display_name"].lower(), item["entity_id"]))

    async def history(self, entity_id: str, start: datetime, end: datetime) -> list[dict]:
        start_value = start.astimezone(timezone.utc).isoformat()
        end_value = end.astimezone(timezone.utc).isoformat()
        async with self._client() as client:
            response = await client.get(
                f"/api/history/period/{start_value}",
                params={
                    "end_time": end_value,
                    "filter_entity_id": entity_id,
                    "minimal_response": "",
                    "no_attributes": "",
                },
            )
            response.raise_for_status()
            groups = response.json()
        return groups[0] if groups else []


class HomeAssistantSyncService:
    """Import selected Home Assistant entity history into timestamped storage."""

    def __init__(
        self,
        *,
        client_factory: ClientFactory = httpx.AsyncClient,
        decrypt_token: Callable[[str], str] = decrypt_secret,
    ):
        self.client_factory = client_factory
        self.decrypt_token = decrypt_token

    async def sync_connection(
        self,
        session: AsyncSession,
        connection_id: int,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        connection = await session.get(HomeAssistantConnection, connection_id)
        if connection is None:
            raise ValueError("Home Assistant connection not found")
        if not connection.enabled:
            raise ValueError("Home Assistant connection is disabled")

        now = end or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if start is None:
            if connection.last_successful_sync_at:
                start = connection.last_successful_sync_at.replace(tzinfo=timezone.utc) - timedelta(hours=1)
            else:
                start = now - timedelta(days=1)
        elif start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start >= now:
            raise ValueError("Home Assistant sync start must be before end")

        result = await session.execute(
            select(HomeAssistantEntity)
            .where(HomeAssistantEntity.connection_id == connection.id)
            .where(HomeAssistantEntity.enabled.is_(True))
            .order_by(HomeAssistantEntity.id)
        )
        entities = list(result.scalars())
        if not entities:
            raise ValueError("No Home Assistant entities are selected")

        client = HomeAssistantClient(
            connection.base_url,
            self.decrypt_token(connection.encrypted_token),
            client_factory=self.client_factory,
        )
        observation_count = 0
        for entity in entities:
            window_start = start
            while window_start < now:
                window_end = min(window_start + timedelta(days=1), now)
                history = await client.history(entity.entity_id, window_start, window_end)
                for item in history:
                    timestamp = item.get("last_updated") or item.get("last_changed")
                    state = item.get("state")
                    if not timestamp or state is None:
                        continue
                    try:
                        numeric_value = float(state)
                    except (TypeError, ValueError):
                        numeric_value = {"off": 0.0, "on": 1.0}.get(str(state).lower())
                    source_unit = (item.get("attributes") or {}).get(
                        "unit_of_measurement", entity.source_unit
                    )
                    statement = insert(HomeAssistantObservation).values(
                        entity_id=entity.id,
                        observed_at=_parse_timestamp(timestamp),
                        state=str(state),
                        numeric_value=numeric_value,
                        source_unit=source_unit,
                        fetched_at=datetime.utcnow(),
                    )
                    statement = statement.on_conflict_do_update(
                        index_elements=["entity_id", "observed_at"],
                        set_={
                            "state": statement.excluded.state,
                            "numeric_value": statement.excluded.numeric_value,
                            "source_unit": statement.excluded.source_unit,
                            "fetched_at": statement.excluded.fetched_at,
                        },
                    )
                    await session.execute(statement)
                    observation_count += 1
                window_start = window_end

        connection.last_successful_sync_at = _utc_naive(now)
        await session.commit()
        return {
            "connection_id": connection.id,
            "start": _utc_naive(start).isoformat() + "Z",
            "end": _utc_naive(now).isoformat() + "Z",
            "entities": len(entities),
            "observations": observation_count,
        }
