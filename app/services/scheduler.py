"""APScheduler setup for daily sync jobs."""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.services.garmin import GarminClient
from app.services.habitsync import HabitSyncClient
from app.services.sync import SyncService
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


async def run_scheduled_sync():
    """Run the daily sync job."""
    settings = get_settings()
    logger.info("Starting scheduled sync job")

    # Create clients
    garmin = GarminClient(
        settings.garmin_email,
        settings.garmin_password,
        settings.garmin_token_dir
    )
    habitsync = HabitSyncClient(
        settings.habitsync_url,
        settings.habitsync_api_key
    )

    # Create sync service
    sync_service = SyncService(garmin, habitsync, settings.tz)

    # Connect to Garmin
    try:
        await garmin.connect()
    except Exception as e:
        logger.error(f"Failed to connect to Garmin: {e}")
        return

    # Run sync
    async with async_session_maker() as session:
        try:
            result = await sync_service.run_daily_sync(session)

            # Log the sync
            sync_log = SyncLog(
                sync_type="all",
                date_synced=datetime.now().date(),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="success" if result["overall_success"] else "failed",
                details=result
            )
            session.add(sync_log)
            await session.commit()

            logger.info(f"Scheduled sync completed: {result}")
        except Exception as e:
            logger.error(f"Scheduled sync failed: {e}")

            # Log the failure
            sync_log = SyncLog(
                sync_type="all",
                date_synced=datetime.now().date(),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="failed",
                error_message=str(e)
            )
            session.add(sync_log)
            await session.commit()
        finally:
            await habitsync.close()


def start_scheduler():
    """Start the APScheduler."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already started")
        return

    settings = get_settings()
    scheduler = AsyncIOScheduler()

    # Add daily sync job at configured hour
    scheduler.add_job(
        run_scheduled_sync,
        CronTrigger(hour=settings.sync_hour, minute=0),
        id="daily_sync",
        name="Daily Garmin and HabitSync sync",
        replace_existing=True
    )

    scheduler.start()
    logger.info(f"Scheduler started - daily sync at {settings.sync_hour}:00")


def stop_scheduler():
    """Stop the APScheduler."""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler stopped")
