"""Sync API endpoints."""

from datetime import date, datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.config import get_settings
from app.services.garmin import GarminClient, GarminMfaRequiredError
from app.services.habitsync import HabitSyncClient
from app.services.sync import SyncService
from app.models.sync_log import SyncLog

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncResponse(BaseModel):
    message: str
    date: str


class SyncStatusResponse(BaseModel):
    garmin_last_sync: datetime | None
    garmin_status: str
    habitsync_last_sync: datetime | None
    habitsync_status: str
    last_sync_date: str | None


async def _get_sync_service() -> SyncService:
    """Create a sync service instance."""
    settings = get_settings()

    garmin = GarminClient(
        settings.garmin_email,
        settings.garmin_password,
        settings.garmin_token_dir
    )
    await garmin.connect()

    habitsync = HabitSyncClient(
        settings.habitsync_url,
        settings.habitsync_api_key
    )

    return SyncService(garmin, habitsync, settings.tz)


async def _run_sync_in_background(
    sync_type: str,
    target_date: date,
    session: AsyncSession
):
    """Background task to run sync."""
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

    started_at = datetime.utcnow()

    try:
        if sync_type == "garmin":
            result = await sync_service.sync_garmin_day(target_date, session)
        elif sync_type == "habitsync":
            result = await sync_service.sync_habitsync_day(target_date, session)
        else:  # "all"
            result = await sync_service.sync_day(target_date, session)

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


@router.post("/garmin", response_model=SyncResponse)
async def sync_garmin(
    background_tasks: BackgroundTasks,
    date_param: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Trigger manual Garmin sync."""
    target_date = date.fromisoformat(date_param) if date_param else date.today()

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


@router.post("/habitsync", response_model=SyncResponse)
async def sync_habitsync(
    background_tasks: BackgroundTasks,
    date_param: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Trigger manual HabitSync sync."""
    target_date = date.fromisoformat(date_param) if date_param else date.today()

    background_tasks.add_task(
        _run_sync_in_background,
        "habitsync",
        target_date,
        db
    )

    return SyncResponse(
        message="HabitSync sync started",
        date=target_date.isoformat()
    )


@router.post("/all", response_model=SyncResponse)
async def sync_all(
    background_tasks: BackgroundTasks,
    date_param: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Trigger full sync (both Garmin and HabitSync)."""
    target_date = date.fromisoformat(date_param) if date_param else date.today()

    background_tasks.add_task(
        _run_sync_in_background,
        "all",
        target_date,
        db
    )

    return SyncResponse(
        message="Full sync started",
        date=target_date.isoformat()
    )


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(db: AsyncSession = Depends(get_db)):
    """Get sync status - last sync times and statuses."""

    # Get last Garmin sync
    garmin_result = await db.execute(
        select(SyncLog)
        .where(SyncLog.sync_type.in_(["garmin", "all"]))
        .order_by(desc(SyncLog.completed_at))
        .limit(1)
    )
    garmin_log = garmin_result.scalar_one_or_none()

    # Get last HabitSync sync
    habitsync_result = await db.execute(
        select(SyncLog)
        .where(SyncLog.sync_type.in_(["habitsync", "all"]))
        .order_by(desc(SyncLog.completed_at))
        .limit(1)
    )
    habitsync_log = habitsync_result.scalar_one_or_none()

    return SyncStatusResponse(
        garmin_last_sync=garmin_log.completed_at if garmin_log else None,
        garmin_status=garmin_log.status if garmin_log else "never_synced",
        habitsync_last_sync=habitsync_log.completed_at if habitsync_log else None,
        habitsync_status=habitsync_log.status if habitsync_log else "never_synced",
        last_sync_date=garmin_log.date_synced.isoformat() if garmin_log else None
    )
