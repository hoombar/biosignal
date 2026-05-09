"""Sync API endpoints."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from zoneinfo import ZoneInfo

from app.core.database import get_db, async_session_maker
from app.core.config import get_settings
from app.services.garmin import GarminClient, GarminMfaRequiredError
from app.services.sync import SyncService
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncResponse(BaseModel):
    message: str
    date: str


class ServiceSyncStatus(BaseModel):
    service: str
    label: str
    last_sync: datetime | None
    status: str
    last_sync_date: str | None
    error: str | None = None


class SyncStatusResponse(BaseModel):
    garmin_last_sync: datetime | None
    garmin_status: str
    last_sync_date: str | None
    environment_last_sync: datetime | None
    environment_status: str
    environment_last_sync_date: str | None
    environment_error: str | None = None
    services: list[ServiceSyncStatus]


class BackfillRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    days: int | None = None

    @field_validator("days")
    @classmethod
    def validate_days(cls, v):
        if v is not None and (v < 1 or v > 365):
            raise ValueError("days must be between 1 and 365")
        return v


class BackfillResponse(BaseModel):
    message: str
    start_date: str
    end_date: str
    total_days: int


class BackfillStatusResponse(BaseModel):
    is_running: bool
    start_date: str | None = None
    end_date: str | None = None
    total_days: int | None = None
    days_completed: int | None = None
    days_failed: int | None = None
    started_at: datetime | None = None


@dataclass
class _BackfillState:
    is_running: bool = False
    cancel_requested: bool = False
    start_date: date | None = None
    end_date: date | None = None
    total_days: int = 0
    days_completed: int = 0
    days_failed: int = 0
    started_at: datetime | None = None


_backfill_state = _BackfillState()


def _today_in_app_timezone() -> date:
    """Return today's date in the configured application timezone."""
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.tz)).date()


async def _get_sync_service() -> SyncService:
    """Create a sync service instance."""
    settings = get_settings()

    garmin = GarminClient(
        settings.garmin_email,
        settings.garmin_password,
        settings.garmin_token_dir
    )
    await garmin.connect()

    return SyncService(garmin, settings.tz)


def _get_environment_sync_service() -> SyncService:
    """Create a sync service instance for local environmental metrics."""
    settings = get_settings()
    garmin = GarminClient(
        settings.garmin_email,
        settings.garmin_password,
        settings.garmin_token_dir,
    )
    return SyncService(garmin, settings.tz)


async def _run_sync_in_background(
    sync_type: str,
    target_date: date,
    session: AsyncSession
):
    """Background task to run sync."""
    started_at = datetime.utcnow()

    try:
        sync_service = await _get_sync_service()
    except GarminMfaRequiredError:
        sync_log = SyncLog(
            sync_type=sync_type,
            date_synced=target_date,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            status="failed",
            error_message="Garmin authentication not set up. Visit /setup/garmin to configure."
        )
        session.add(sync_log)
        await session.commit()
        return

    try:
        # "garmin" and "all" both run the Garmin sync; "all" is kept as a
        # back-compat alias for any existing UI/scripts.
        result = await sync_service.sync_garmin_day(target_date, session)

        # Log success
        sync_log = SyncLog(
            sync_type=sync_type,
            date_synced=target_date,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            status="success",
            details=result
        )
        session.add(sync_log)
        await session.commit()

    except Exception as e:
        # Log failure
        sync_log = SyncLog(
            sync_type=sync_type,
            date_synced=target_date,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            status="failed",
            error_message=str(e)
        )
        session.add(sync_log)
        await session.commit()


async def _run_environment_sync_in_background(
    target_date: date,
    session: AsyncSession,
):
    """Background task to run deterministic environmental sync."""
    started_at = datetime.utcnow()
    sync_service = _get_environment_sync_service()

    try:
        result = await sync_service.sync_environment_day(target_date, session)
        metric_count = result.get("counts", {}).get("environmental_metrics", 0)
        log_status = "success" if result["success"] else "partial" if metric_count > 0 else "failed"

        sync_log = SyncLog(
            sync_type="environment",
            date_synced=target_date,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            status=log_status,
            details=result,
            error_message="; ".join(result["errors"]) if result.get("errors") else None,
        )
        session.add(sync_log)
        await session.commit()

    except Exception as e:
        sync_log = SyncLog(
            sync_type="environment",
            date_synced=target_date,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            status="failed",
            error_message=str(e),
        )
        session.add(sync_log)
        await session.commit()


@router.post("/garmin", response_model=SyncResponse)
async def sync_garmin(
    background_tasks: BackgroundTasks,
    date_param: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Trigger manual Garmin sync."""
    target_date = date.fromisoformat(date_param) if date_param else _today_in_app_timezone()

    background_tasks.add_task(
        _run_sync_in_background,
        "garmin",
        target_date,
        db
    )

    return SyncResponse(
        message="Garmin sync started",
        date=target_date.isoformat()
    )


@router.post("/all", response_model=SyncResponse)
async def sync_all(
    background_tasks: BackgroundTasks,
    date_param: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Back-compat alias for ``/api/sync/garmin``.

    Habits are now logged natively in biosignal, so "sync all" is just
    "sync Garmin." Kept so any existing UI buttons or scripts pointing
    at /api/sync/all keep working.
    """
    target_date = date.fromisoformat(date_param) if date_param else _today_in_app_timezone()

    background_tasks.add_task(
        _run_sync_in_background,
        "all",
        target_date,
        db,
    )

    return SyncResponse(
        message="Garmin sync started",
        date=target_date.isoformat(),
    )


@router.post("/environment", response_model=SyncResponse)
async def sync_environment(
    background_tasks: BackgroundTasks,
    date_param: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger manual deterministic environmental sync."""
    target_date = date.fromisoformat(date_param) if date_param else _today_in_app_timezone()

    background_tasks.add_task(
        _run_environment_sync_in_background,
        target_date,
        db,
    )

    return SyncResponse(
        message="Environment sync started",
        date=target_date.isoformat(),
    )


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(db: AsyncSession = Depends(get_db)):
    """Get sync status by external service."""
    garmin_result = await db.execute(
        select(SyncLog)
        .where(SyncLog.sync_type.in_(["garmin", "all", "backfill"]))
        .order_by(desc(SyncLog.completed_at))
        .limit(1)
    )
    garmin_log = garmin_result.scalar_one_or_none()

    environment_result = await db.execute(
        select(SyncLog)
        .where(SyncLog.sync_type == "environment")
        .order_by(desc(SyncLog.completed_at))
        .limit(1)
    )
    environment_log = environment_result.scalar_one_or_none()

    services = [
        ServiceSyncStatus(
            service="garmin",
            label="Garmin",
            last_sync=garmin_log.completed_at if garmin_log else None,
            status=garmin_log.status if garmin_log else "never_synced",
            last_sync_date=garmin_log.date_synced.isoformat() if garmin_log else None,
            error=garmin_log.error_message if garmin_log else None,
        ),
        ServiceSyncStatus(
            service="environment",
            label="Environment / Pollen",
            last_sync=environment_log.completed_at if environment_log else None,
            status=environment_log.status if environment_log else "never_synced",
            last_sync_date=environment_log.date_synced.isoformat() if environment_log else None,
            error=environment_log.error_message if environment_log else None,
        ),
    ]

    return SyncStatusResponse(
        garmin_last_sync=garmin_log.completed_at if garmin_log else None,
        garmin_status=garmin_log.status if garmin_log else "never_synced",
        last_sync_date=garmin_log.date_synced.isoformat() if garmin_log else None,
        environment_last_sync=environment_log.completed_at if environment_log else None,
        environment_status=environment_log.status if environment_log else "never_synced",
        environment_last_sync_date=environment_log.date_synced.isoformat() if environment_log else None,
        environment_error=environment_log.error_message if environment_log else None,
        services=services,
    )


async def _run_backfill_in_background(start_date: date, end_date: date):
    """Background task to backfill a date range."""
    _backfill_state.is_running = True
    _backfill_state.cancel_requested = False
    _backfill_state.start_date = start_date
    _backfill_state.end_date = end_date
    _backfill_state.total_days = (end_date - start_date).days + 1
    _backfill_state.days_completed = 0
    _backfill_state.days_failed = 0
    _backfill_state.started_at = datetime.utcnow()

    try:
        sync_service = await _get_sync_service()
    except GarminMfaRequiredError:
        logger.error("Backfill failed: Garmin auth not set up")
        _backfill_state.is_running = False
        return

    current = start_date
    while current <= end_date:
        # Check for cancellation
        if _backfill_state.cancel_requested:
            logger.info("Backfill cancelled by user")
            break

        async with async_session_maker() as session:
            started_at = datetime.utcnow()
            try:
                result = await sync_service.sync_day(current, session)

                sync_log = SyncLog(
                    sync_type="backfill",
                    date_synced=current,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    status="success" if result.get("overall_success") else "partial",
                    details=result,
                )
                session.add(sync_log)
                await session.commit()

                if result.get("overall_success"):
                    _backfill_state.days_completed += 1
                else:
                    _backfill_state.days_failed += 1

            except Exception as e:
                logger.error(f"Backfill failed for {current}: {e}")
                _backfill_state.days_failed += 1

                sync_log = SyncLog(
                    sync_type="backfill",
                    date_synced=current,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    status="failed",
                    error_message=str(e),
                )
                session.add(sync_log)
                await session.commit()

        done = _backfill_state.days_completed + _backfill_state.days_failed
        logger.info(f"Backfill {current}: {done}/{_backfill_state.total_days}")

        if current < end_date:
            await asyncio.sleep(2.0)
        current += timedelta(days=1)

    cancelled = _backfill_state.cancel_requested
    _backfill_state.is_running = False
    _backfill_state.cancel_requested = False

    if cancelled:
        logger.info(
            f"Backfill cancelled: {_backfill_state.days_completed} succeeded, "
            f"{_backfill_state.days_failed} failed out of {_backfill_state.total_days}"
        )
    else:
        logger.info(
            f"Backfill complete: {_backfill_state.days_completed} succeeded, "
            f"{_backfill_state.days_failed} failed out of {_backfill_state.total_days}"
        )


@router.get("/backfill/status", response_model=BackfillStatusResponse)
async def backfill_status():
    """Get the current backfill progress."""
    return BackfillStatusResponse(
        is_running=_backfill_state.is_running,
        start_date=_backfill_state.start_date.isoformat() if _backfill_state.start_date else None,
        end_date=_backfill_state.end_date.isoformat() if _backfill_state.end_date else None,
        total_days=_backfill_state.total_days or None,
        days_completed=_backfill_state.days_completed,
        days_failed=_backfill_state.days_failed,
        started_at=_backfill_state.started_at,
    )


@router.post("/backfill/cancel")
async def cancel_backfill():
    """Cancel a running backfill."""
    if not _backfill_state.is_running:
        raise HTTPException(status_code=400, detail="No backfill is currently running")

    _backfill_state.cancel_requested = True
    return {"message": "Backfill cancellation requested"}


@router.post("/backfill", response_model=BackfillResponse)
async def sync_backfill(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a backfill sync for a date range.

    Provide either `days` (last N days ending yesterday) or both
    `start_date` and `end_date`.
    """
    if _backfill_state.is_running:
        raise HTTPException(
            status_code=409,
            detail="A backfill is already running. Check /api/sync/backfill/status for progress.",
        )

    today = _today_in_app_timezone()

    if request.days is not None:
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=request.days - 1)
    elif request.start_date is not None and request.end_date is not None:
        start_date = request.start_date
        end_date = request.end_date
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'days' or both 'start_date' and 'end_date'.",
        )

    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date")
    if end_date > today:
        raise HTTPException(status_code=422, detail="end_date cannot be in the future")

    total_days = (end_date - start_date).days + 1
    if total_days > 365:
        raise HTTPException(status_code=422, detail=f"Date range too large ({total_days} days). Maximum is 365.")

    background_tasks.add_task(_run_backfill_in_background, start_date, end_date)

    return BackfillResponse(
        message=f"Backfill started for {total_days} days",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_days=total_days,
    )
