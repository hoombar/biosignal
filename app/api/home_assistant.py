"""Home Assistant connection, discovery, selection, and sync endpoints."""

from datetime import date, datetime, time, timezone
import logging
from typing import Literal, NoReturn
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.models.database import (
    HomeAssistantConnection,
    HomeAssistantEntity,
    HomeAssistantObservation,
)
from app.models.sync_log import SyncLog
from app.services.home_assistant import (
    HomeAssistantClient,
    HomeAssistantSyncService,
    normalize_base_url,
)
from app.services.secrets import decrypt_secret, encrypt_secret


router = APIRouter(prefix="/api/home-assistant", tags=["home-assistant"])
logger = logging.getLogger(__name__)

HomeAssistantRole = Literal["bedroom_temperature", "bedroom_humidity"]


class ConnectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    token: str | None = Field(default=None, min_length=1)
    enabled: bool = True


class ConnectionResponse(BaseModel):
    id: int
    name: str
    base_url: str
    enabled: bool
    ha_timezone: str | None
    last_successful_sync_at: datetime | None
    token_configured: bool


class DiscoveredEntity(BaseModel):
    entity_id: str
    display_name: str
    device_class: str | None
    unit: str | None
    state: str | None


class EntitySelection(BaseModel):
    entity_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    device_class: str | None = None
    source_unit: str | None = None
    role: HomeAssistantRole


class EntitySelections(BaseModel):
    entities: list[EntitySelection]


class EntityResponse(EntitySelection):
    id: int
    enabled: bool


class SyncInput(BaseModel):
    start_date: date | None = None


def _sync_start(start_date: date) -> datetime:
    local_start = datetime.combine(
        start_date, time.min, tzinfo=ZoneInfo(get_settings().tz)
    )
    return local_start.astimezone(timezone.utc)


def _home_assistant_error(exc: httpx.HTTPError) -> tuple[int, str]:
    """Return a useful error without exposing request headers or credentials."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return 401, "Home Assistant rejected the access token"
        if status == 404:
            return 502, "Home Assistant API was not found at that URL"
        return 502, f"Home Assistant returned HTTP {status}"
    if isinstance(exc, httpx.TimeoutException):
        return 504, "Home Assistant did not respond before the connection timed out"
    if isinstance(exc, httpx.ConnectError):
        if "CERTIFICATE_VERIFY_FAILED" in str(exc).upper():
            return 502, "Home Assistant TLS certificate validation failed"
        return 502, "Could not connect to Home Assistant; check the URL and network"
    return 502, "Home Assistant returned an invalid response"


def _raise_home_assistant_error(exc: httpx.HTTPError) -> NoReturn:
    status_code, detail = _home_assistant_error(exc)
    response_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    logger.warning(
        "Home Assistant connection check failed: error_type=%s status=%s",
        type(exc).__name__,
        response_status,
    )
    raise HTTPException(status_code=status_code, detail=detail) from exc


def _connection_response(connection: HomeAssistantConnection) -> ConnectionResponse:
    return ConnectionResponse(
        id=connection.id,
        name=connection.name,
        base_url=connection.base_url,
        enabled=connection.enabled,
        ha_timezone=connection.ha_timezone,
        last_successful_sync_at=connection.last_successful_sync_at,
        token_configured=bool(connection.encrypted_token),
    )


async def _get_connection(db: AsyncSession) -> HomeAssistantConnection:
    connection = await db.scalar(select(HomeAssistantConnection).order_by(HomeAssistantConnection.id))
    if connection is None:
        raise HTTPException(status_code=404, detail="Home Assistant is not configured")
    return connection


async def _observation_count(db: AsyncSession, connection_id: int) -> int:
    count = await db.scalar(
        select(func.count(HomeAssistantObservation.id))
        .select_from(HomeAssistantObservation)
        .join(HomeAssistantEntity, HomeAssistantObservation.entity_id == HomeAssistantEntity.id)
        .where(HomeAssistantEntity.connection_id == connection_id)
    )
    return count or 0


@router.get("/connection", response_model=ConnectionResponse | None)
async def get_connection(db: AsyncSession = Depends(get_db)):
    connection = await db.scalar(select(HomeAssistantConnection).order_by(HomeAssistantConnection.id))
    return _connection_response(connection) if connection else None


@router.put("/connection", response_model=ConnectionResponse)
async def put_connection(body: ConnectionInput, db: AsyncSession = Depends(get_db)):
    try:
        base_url = normalize_base_url(body.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    connection = await db.scalar(select(HomeAssistantConnection).order_by(HomeAssistantConnection.id))
    if connection is None and not body.token:
        raise HTTPException(status_code=422, detail="A token is required for initial setup")
    url_changed = connection is not None and connection.base_url != base_url
    if url_changed and not body.token:
        raise HTTPException(
            status_code=422,
            detail="Changing the Home Assistant URL requires a new token",
        )
    if url_changed and connection is not None and await _observation_count(db, connection.id):
        raise HTTPException(
            status_code=409,
            detail="A Home Assistant instance cannot be replaced after sensor history is imported",
        )

    encrypted_token = connection.encrypted_token if connection else ""
    if body.token:
        try:
            config = await HomeAssistantClient(base_url, body.token).config()
        except httpx.HTTPError as exc:
            _raise_home_assistant_error(exc)
        try:
            encrypted_token = encrypt_secret(body.token)
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="Integration credential encryption is not configured correctly",
            ) from exc
    else:
        try:
            config = await HomeAssistantClient(
                base_url, decrypt_secret(encrypted_token)
            ).config()
        except httpx.HTTPError as exc:
            _raise_home_assistant_error(exc)
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="The saved integration credential could not be decrypted",
            ) from exc

    if connection is None:
        connection = HomeAssistantConnection(
            name=body.name,
            base_url=base_url,
            encrypted_token=encrypted_token,
            enabled=body.enabled,
        )
        db.add(connection)
    else:
        connection.name = body.name
        connection.base_url = base_url
        connection.encrypted_token = encrypted_token
        connection.enabled = body.enabled
        if url_changed:
            connection.last_successful_sync_at = None
            result = await db.execute(
                select(HomeAssistantEntity).where(
                    HomeAssistantEntity.connection_id == connection.id
                )
            )
            for entity in result.scalars():
                entity.enabled = False
    connection.ha_timezone = config.get("time_zone")
    await db.commit()
    await db.refresh(connection)
    return _connection_response(connection)


@router.get("/entities/discover", response_model=list[DiscoveredEntity])
async def discover_entities(db: AsyncSession = Depends(get_db)):
    connection = await _get_connection(db)
    try:
        client = HomeAssistantClient(
            connection.base_url, decrypt_secret(connection.encrypted_token)
        )
        return await client.discover_entities()
    except httpx.HTTPError as exc:
        _raise_home_assistant_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=500, detail="The saved integration credential could not be decrypted"
        ) from exc


@router.get("/entities", response_model=list[EntityResponse])
async def get_entities(db: AsyncSession = Depends(get_db)):
    connection = await _get_connection(db)
    result = await db.execute(
        select(HomeAssistantEntity)
        .where(HomeAssistantEntity.connection_id == connection.id)
        .where(HomeAssistantEntity.enabled.is_(True))
        .order_by(HomeAssistantEntity.display_name)
    )
    return list(result.scalars())


@router.put("/entities", response_model=list[EntityResponse])
async def put_entities(body: EntitySelections, db: AsyncSession = Depends(get_db)):
    connection = await _get_connection(db)
    roles = [entity.role for entity in body.entities]
    if len(roles) != len(set(roles)):
        raise HTTPException(status_code=422, detail="Each Home Assistant role can be selected once")
    entity_ids = [entity.entity_id for entity in body.entities]
    if len(entity_ids) != len(set(entity_ids)):
        raise HTTPException(status_code=422, detail="Each Home Assistant entity can be selected once")
    for entity in body.entities:
        expected_class = "temperature" if entity.role == "bedroom_temperature" else "humidity"
        if entity.device_class != expected_class:
            raise HTTPException(
                status_code=422,
                detail=f"{entity.role} requires a {expected_class} entity",
            )

    result = await db.execute(
        select(HomeAssistantEntity).where(HomeAssistantEntity.connection_id == connection.id)
    )
    existing = {entity.entity_id: entity for entity in result.scalars()}
    current_selection = {
        (entity.entity_id, entity.role) for entity in existing.values() if entity.enabled
    }
    requested_selection = {(entity.entity_id, entity.role) for entity in body.entities}
    if not current_selection.issubset(requested_selection) and await _observation_count(
        db, connection.id
    ):
        raise HTTPException(
            status_code=409,
            detail="Sensor assignments cannot be replaced after history is imported",
        )
    for entity in existing.values():
        entity.enabled = False

    selected = []
    for item in body.entities:
        entity = existing.get(item.entity_id)
        if entity is None:
            entity = HomeAssistantEntity(
                connection_id=connection.id,
                entity_id=item.entity_id,
                display_name=item.display_name,
            )
            db.add(entity)
        entity.display_name = item.display_name
        entity.device_class = item.device_class
        entity.source_unit = item.source_unit
        entity.role = item.role
        entity.enabled = True
        selected.append(entity)

    await db.commit()
    for entity in selected:
        await db.refresh(entity)
    return selected


@router.post("/sync")
async def sync_home_assistant(body: SyncInput, db: AsyncSession = Depends(get_db)):
    connection = await _get_connection(db)
    start = _sync_start(body.start_date) if body.start_date else None
    started_at = datetime.utcnow()
    try:
        result = await HomeAssistantSyncService().sync_connection(
            db, connection.id, start=start
        )
        db.add(
            SyncLog(
                sync_type="home_assistant",
                date_synced=datetime.now(ZoneInfo(get_settings().tz)).date(),
                started_at=started_at,
                completed_at=datetime.utcnow(),
                status="success",
                details=result,
            )
        )
        await db.commit()
        return result
    except (httpx.HTTPError, ValueError) as exc:
        await db.rollback()
        db.add(
            SyncLog(
                sync_type="home_assistant",
                date_synced=datetime.now(ZoneInfo(get_settings().tz)).date(),
                started_at=started_at,
                completed_at=datetime.utcnow(),
                status="failed",
                error_message=str(exc),
            )
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
