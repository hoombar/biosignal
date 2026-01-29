"""Sync orchestration - coordinates data fetching and storage."""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from app.services.garmin import GarminClient
from app.services.habitsync import HabitSyncClient, parse_habitsync_response
from app.services import parsers
from app.models.database import (
    RawGarminResponse,
    RawHabitSyncResponse,
    HeartRateSample,
    BodyBatterySample,
    StressSample,
    HrvSample,
    Spo2Sample,
    StepsSample,
    SleepSession,
    Activity,
    DailyHabit,
)

logger = logging.getLogger(__name__)


class SyncService:
    """Orchestrates syncing data from Garmin and HabitSync."""

    def __init__(self, garmin: GarminClient, habitsync: HabitSyncClient, timezone: str):
        self.garmin = garmin
        self.habitsync = habitsync
        self.timezone = timezone

    async def _upsert_samples(
        self,
        session: AsyncSession,
        model_class,
        samples: list,
        unique_column: str = "timestamp"
    ):
        """Upsert time-series samples using SQLite INSERT OR REPLACE."""
        if not samples:
            return 0

        for sample in samples:
            # Use merge for upsert behavior
            await session.merge(sample)

        return len(samples)

    async def sync_garmin_day(self, target_date: date, session: AsyncSession) -> dict[str, Any]:
        """
        Sync Garmin data for a specific day.

        Returns:
            Status dict with counts of rows inserted per table.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        logger.info(f"Syncing Garmin data for {date_str}")

        status = {
            "date": date_str,
            "success": True,
            "errors": [],
            "counts": {}
        }

        try:
            # Fetch all data for the date
            raw_data = await self.garmin.fetch_all_for_date(date_str)

            # Store raw responses
            for endpoint, response in raw_data.items():
                if response is not None:
                    raw_record = RawGarminResponse(
                        date=target_date,
                        endpoint=endpoint,
                        response=response,
                        fetched_at=datetime.utcnow()
                    )
                    await session.merge(raw_record)

            # Parse and store each data type
            if raw_data.get("heart_rate"):
                hr_samples = parsers.parse_heart_rate(raw_data["heart_rate"], target_date)
                count = await self._upsert_samples(session, HeartRateSample, hr_samples)
                status["counts"]["heart_rate"] = count

            if raw_data.get("body_battery"):
                bb_samples = parsers.parse_body_battery(raw_data["body_battery"], target_date)
                count = await self._upsert_samples(session, BodyBatterySample, bb_samples)
                status["counts"]["body_battery"] = count

            if raw_data.get("stress"):
                stress_samples = parsers.parse_stress(raw_data["stress"], target_date)
                count = await self._upsert_samples(session, StressSample, stress_samples)
                status["counts"]["stress"] = count

            if raw_data.get("hrv"):
                hrv_samples = parsers.parse_hrv(raw_data["hrv"], target_date)
                count = await self._upsert_samples(session, HrvSample, hrv_samples)
                status["counts"]["hrv"] = count

            if raw_data.get("spo2"):
                spo2_samples = parsers.parse_spo2(raw_data["spo2"], target_date)
                count = await self._upsert_samples(session, Spo2Sample, spo2_samples)
                status["counts"]["spo2"] = count

            if raw_data.get("steps"):
                steps_samples = parsers.parse_steps(raw_data["steps"], target_date)
                count = await self._upsert_samples(session, StepsSample, steps_samples)
                status["counts"]["steps"] = count

            if raw_data.get("sleep"):
                sleep_session = parsers.parse_sleep(raw_data["sleep"], target_date)
                if sleep_session:
                    await session.merge(sleep_session)
                    status["counts"]["sleep"] = 1

            await session.commit()
            logger.info(f"Garmin sync completed for {date_str}: {status['counts']}")

        except Exception as e:
            logger.error(f"Garmin sync failed for {date_str}: {e}")
            status["success"] = False
            status["errors"].append(str(e))
            await session.rollback()

        return status

    async def sync_habitsync_day(self, target_date: date, session: AsyncSession) -> dict[str, Any]:
        """
        Sync HabitSync data for a specific day.

        Returns:
            Status dict with counts.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        logger.info(f"Syncing HabitSync data for {date_str}")

        status = {
            "date": date_str,
            "success": True,
            "errors": [],
            "counts": {}
        }

        try:
            # Fetch all habits for the date
            habits_data = await self.habitsync.fetch_all_for_date(target_date, self.timezone)

            # Store raw response
            raw_record = RawHabitSyncResponse(
                date=target_date,
                response=habits_data,
                fetched_at=datetime.utcnow()
            )
            await session.merge(raw_record)

            # Parse and store habits
            habit_rows = parse_habitsync_response(habits_data, target_date)
            for habit in habit_rows:
                await session.merge(habit)

            status["counts"]["habits"] = len(habit_rows)

            await session.commit()
            logger.info(f"HabitSync sync completed for {date_str}: {status['counts']}")

        except Exception as e:
            logger.error(f"HabitSync sync failed for {date_str}: {e}")
            status["success"] = False
            status["errors"].append(str(e))
            await session.rollback()

        return status

    async def sync_day(self, target_date: date, session: AsyncSession) -> dict[str, Any]:
        """
        Sync both Garmin and HabitSync data for a specific day.

        Returns:
            Combined status dict.
        """
        logger.info(f"Syncing all data for {target_date}")

        garmin_status = await self.sync_garmin_day(target_date, session)
        habitsync_status = await self.sync_habitsync_day(target_date, session)

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "garmin": garmin_status,
            "habitsync": habitsync_status,
            "overall_success": garmin_status["success"] and habitsync_status["success"]
        }

    async def sync_date_range(
        self,
        start_date: date,
        end_date: date,
        session: AsyncSession,
        delay_seconds: float = 2.0
    ) -> list[dict[str, Any]]:
        """
        Sync a range of dates.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            session: Database session
            delay_seconds: Delay between days to avoid rate limiting
        """
        import asyncio

        results = []
        current = start_date

        while current <= end_date:
            result = await self.sync_day(current, session)
            results.append(result)

            # Add delay between days to avoid rate limiting
            if current < end_date:
                await asyncio.sleep(delay_seconds)

            current += timedelta(days=1)

        return results

    async def run_daily_sync(self, session: AsyncSession) -> dict[str, Any]:
        """
        Run daily sync for yesterday's data.
        This is called by the scheduler.
        """
        from zoneinfo import ZoneInfo

        # Get yesterday in the configured timezone
        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        yesterday = (now - timedelta(days=1)).date()

        logger.info(f"Running daily sync for {yesterday}")
        return await self.sync_day(yesterday, session)
