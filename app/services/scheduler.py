"""APScheduler setup for daily sync jobs."""

import logging
from datetime import date, datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.services.garmin import GarminClient
from app.services.sync import SyncService
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


async def run_scheduled_sync():
    """Run the daily Garmin sync job."""
    settings = get_settings()
    logger.info("Starting scheduled sync job")

    garmin = GarminClient(
        settings.garmin_email,
        settings.garmin_password,
        settings.garmin_token_dir,
    )
    sync_service = SyncService(garmin, settings.tz)

    try:
        await garmin.connect()
    except Exception as e:
        logger.error(f"Failed to connect to Garmin: {e}")
        return

    async with async_session_maker() as session:
        try:
            result = await sync_service.run_daily_garmin_sync(session)

            sync_log = SyncLog(
                sync_type="garmin",
                date_synced=date.fromisoformat(result["date"]),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="success" if result["success"] else "failed",
                details=result,
            )
            session.add(sync_log)
            await session.commit()

            logger.info(f"Scheduled sync completed: {result}")
        except Exception as e:
            logger.error(f"Scheduled sync failed: {e}")

            sync_log = SyncLog(
                sync_type="garmin",
                date_synced=datetime.now().date(),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="failed",
                error_message=str(e),
            )
            session.add(sync_log)
            await session.commit()


async def run_scheduled_environment_sync():
    """Run the daily deterministic environmental sync job."""
    settings = get_settings()
    logger.info("Starting scheduled environment sync job")

    garmin = GarminClient(
        settings.garmin_email,
        settings.garmin_password,
        settings.garmin_token_dir,
    )
    sync_service = SyncService(garmin, settings.tz)

    async with async_session_maker() as session:
        try:
            result = await sync_service.run_daily_environment_sync(session)

            sync_log = SyncLog(
                sync_type="environment",
                date_synced=date.fromisoformat(result["date"]),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="success" if result["success"] else "failed",
                details=result,
                error_message="; ".join(result["errors"]) if result.get("errors") else None,
            )
            session.add(sync_log)
            await session.commit()

            logger.info(f"Scheduled environment sync completed: {result}")
        except Exception as e:
            logger.error(f"Scheduled environment sync failed: {e}")

            sync_log = SyncLog(
                sync_type="environment",
                date_synced=datetime.now().date(),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="failed",
                error_message=str(e),
            )
            session.add(sync_log)
            await session.commit()


def start_scheduler():
    """Start the APScheduler."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already started")
        return

    settings = get_settings()
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_scheduled_sync,
        CronTrigger(hour=settings.sync_hour, minute=settings.sync_minute_garmin),
        id="daily_sync",
        name="Daily Garmin sync",
        replace_existing=True,
    )

    scheduler.add_job(
        run_scheduled_environment_sync,
        CronTrigger(hour=settings.sync_hour, minute=settings.sync_minute_environment),
        id="daily_environment_sync",
        name="Daily environment sync",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started - Garmin sync at "
        f"{settings.sync_hour}:{settings.sync_minute_garmin:02d}; "
        "environment sync at "
        f"{settings.sync_hour}:{settings.sync_minute_environment:02d}"
    )


def stop_scheduler():
    """Stop the APScheduler."""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler stopped")
