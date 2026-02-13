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
        """Upsert time-series samples using SQLite INSERT OR IGNORE."""
        if not samples:
            return 0

        table = model_class.__table__
        for sample in samples:
            # Build dict of non-PK column values from the ORM object
            data = {}
            for col in table.columns:
                if col.name != "id":
                    data[col.name] = getattr(sample, col.name, None)

            stmt = insert(table).values(**data).on_conflict_do_update(
                index_elements=[unique_column],
                set_={k: v for k, v in data.items() if k != unique_column},
            )
            await session.execute(stmt)

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

            # Store raw responses (upsert by date+endpoint)
            for endpoint, response in raw_data.items():
                if response is not None:
                    existing = await session.execute(
                        select(RawGarminResponse).where(
                            RawGarminResponse.date == target_date,
                            RawGarminResponse.endpoint == endpoint,
                        )
                    )
                    existing_record = existing.scalar_one_or_none()
                    if existing_record:
                        existing_record.response = response
                        existing_record.fetched_at = datetime.utcnow()
                    else:
                        session.add(RawGarminResponse(
                            date=target_date,
                            endpoint=endpoint,
                            response=response,
                            fetched_at=datetime.utcnow()
                        ))

            # Parse and store each data type
            parse_tasks = [
                ("heart_rate", lambda d: parsers.parse_heart_rate(d, target_date), HeartRateSample),
                ("body_battery", lambda d: parsers.parse_body_battery(d, target_date), BodyBatterySample),
                ("stress", lambda d: parsers.parse_stress(d, target_date), StressSample),
                ("hrv", lambda d: parsers.parse_hrv(d, target_date), HrvSample),
                ("spo2", lambda d: parsers.parse_spo2(d, target_date), Spo2Sample),
                ("steps", lambda d: parsers.parse_steps(d, target_date), StepsSample),
            ]

            for key, parse_fn, model_class in parse_tasks:
                if raw_data.get(key):
                    try:
                        samples = parse_fn(raw_data[key])
                        count = await self._upsert_samples(session, model_class, samples)
                        status["counts"][key] = count
                    except Exception as e:
                        logger.error(f"Failed to parse {key} for {date_str}: {e} (data type: {type(raw_data[key]).__name__})")
                        status["errors"].append(f"{key}: {e}")
                        await session.rollback()

            if raw_data.get("sleep"):
                try:
                    sleep_session = parsers.parse_sleep(raw_data["sleep"], target_date)
                    if sleep_session:
                        # Upsert sleep by date
                        sleep_data = {}
                        for col in SleepSession.__table__.columns:
                            if col.name != "id":
                                sleep_data[col.name] = getattr(sleep_session, col.name, None)
                        stmt = insert(SleepSession.__table__).values(**sleep_data).on_conflict_do_update(
                            index_elements=["date"],
                            set_={k: v for k, v in sleep_data.items() if k != "date"},
                        )
                        await session.execute(stmt)
                        status["counts"]["sleep"] = 1
                except Exception as e:
                    logger.error(f"Failed to parse sleep for {date_str}: {e} (data type: {type(raw_data['sleep']).__name__})")
                    status["errors"].append(f"sleep: {e}")
                    await session.rollback()

            if raw_data.get("activities"):
                try:
                    activities = parsers.parse_activities(raw_data["activities"])
                    for activity in activities:
                        # Upsert activity by garmin_activity_id
                        activity_data = {}
                        for col in Activity.__table__.columns:
                            if col.name != "id":
                                activity_data[col.name] = getattr(activity, col.name, None)
                        stmt = insert(Activity.__table__).values(**activity_data).on_conflict_do_update(
                            index_elements=["garmin_activity_id"],
                            set_={k: v for k, v in activity_data.items() if k != "garmin_activity_id"},
                        )
                        await session.execute(stmt)
                    status["counts"]["activities"] = len(activities)
                except Exception as e:
                    logger.error(f"Failed to parse activities for {date_str}: {e}")
                    status["errors"].append(f"activities: {e}")
                    await session.rollback()

            if status["errors"]:
                status["success"] = False

            await session.commit()
            logger.info(f"Garmin sync completed for {date_str}: {status['counts']}"
                        + (f" (errors: {status['errors']})" if status["errors"] else ""))

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

            # Store raw response (upsert by date)
            existing = await session.execute(
                select(RawHabitSyncResponse).where(RawHabitSyncResponse.date == target_date)
            )
            existing_record = existing.scalar_one_or_none()
            if existing_record:
                existing_record.response = habits_data
                existing_record.fetched_at = datetime.utcnow()
            else:
                session.add(RawHabitSyncResponse(
                    date=target_date,
                    response=habits_data,
                    fetched_at=datetime.utcnow()
                ))

            # Parse and store habits (upsert by date+habit_name)
            habit_rows = parse_habitsync_response(habits_data, target_date)
            for habit in habit_rows:
                stmt = insert(DailyHabit).values(
                    date=habit.date,
                    habit_name=habit.habit_name,
                    habit_value=habit.habit_value,
                    habit_type=habit.habit_type,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "habit_name"],
                    set_={"habit_value": stmt.excluded.habit_value, "habit_type": stmt.excluded.habit_type},
                )
                await session.execute(stmt)

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

        # Consider day successful if Garmin succeeds (HabitSync is supplementary)
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "garmin": garmin_status,
            "habitsync": habitsync_status,
            "overall_success": garmin_status["success"]
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
