"""Sync orchestration - coordinates data fetching and storage."""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.services.garmin import GarminClient
from app.services import parsers
from app.services.environmental import (
    AstronomyProvider,
    EnvironmentalMetricValue,
    OpenMeteoPollenProvider,
    location_key,
)
from app.models.database import (
    RawGarminResponse,
    EnvironmentalMetric,
    HeartRateSample,
    BodyBatterySample,
    StressSample,
    HrvSample,
    Spo2Sample,
    StepsSample,
    SleepSession,
    Activity,
)

logger = logging.getLogger(__name__)


class SyncService:
    """Orchestrates syncing Garmin biometric data."""

    def __init__(self, garmin: GarminClient, timezone: str):
        self.garmin = garmin
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

    async def sync_environment_day(self, target_date: date, session: AsyncSession) -> dict[str, Any]:
        """
        Compute and upsert environmental metrics for a specific day.

        Local astronomy metrics are deterministic. Pollen metrics are fetched
        from Open-Meteo and failures are reported without dropping light rows.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        logger.info(f"Syncing environmental metrics for {date_str}")

        status = {
            "date": date_str,
            "success": True,
            "skipped": False,
            "errors": [],
            "counts": {"environmental_metrics": 0},
        }

        settings = get_settings()
        latitude = settings.environment_latitude
        longitude = settings.environment_longitude

        if latitude is None or longitude is None:
            status["success"] = False
            status["skipped"] = True
            status["errors"].append("ENVIRONMENT_LATITUDE and ENVIRONMENT_LONGITUDE must be set")
            logger.info(f"Environmental sync skipped for {date_str}: location is not configured")
            return status

        try:
            tz = ZoneInfo(self.timezone)
            metrics: list[EnvironmentalMetricValue] = []
            metrics.extend(AstronomyProvider().daily_metrics(target_date, tz, latitude, longitude))

            try:
                metrics.extend(await OpenMeteoPollenProvider().daily_metrics(target_date, tz, latitude, longitude))
            except Exception as e:
                logger.error(f"Open-Meteo pollen sync failed for {date_str}: {e}")
                status["success"] = False
                status["errors"].append(f"pollen: {e}")

            loc_key = location_key(latitude, longitude)
            fetched_at = datetime.utcnow()

            for metric in metrics:
                data = {
                    "date": target_date,
                    "source": metric.source,
                    "metric_key": metric.metric_key,
                    "location_key": loc_key,
                    "value": metric.value,
                    "unit": metric.unit,
                    "category": metric.category,
                    "raw_metadata": metric.raw_metadata,
                    "fetched_at": fetched_at,
                }
                stmt = insert(EnvironmentalMetric.__table__).values(**data).on_conflict_do_update(
                    index_elements=["date", "source", "metric_key", "location_key"],
                    set_={
                        k: v
                        for k, v in data.items()
                        if k not in {"date", "source", "metric_key", "location_key"}
                    },
                )
                await session.execute(stmt)

            status["counts"]["environmental_metrics"] = len(metrics)
            if not metrics:
                status["success"] = False
                status["errors"].append("No environmental metrics produced for configured location/date")

            await session.commit()
            logger.info(f"Environmental sync completed for {date_str}: {status['counts']}")

        except Exception as e:
            logger.error(f"Environmental sync failed for {date_str}: {e}")
            status["success"] = False
            status["errors"].append(str(e))
            await session.rollback()

        return status

    async def sync_day(self, target_date: date, session: AsyncSession) -> dict[str, Any]:
        """Sync Garmin and environmental data for a specific day."""
        garmin_status = await self.sync_garmin_day(target_date, session)
        environment_status = await self.sync_environment_day(target_date, session)
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "garmin": garmin_status,
            "environment": environment_status,
            "overall_success": garmin_status["success"] and environment_status["success"],
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

    async def run_daily_garmin_sync(self, session: AsyncSession) -> dict[str, Any]:
        """Run scheduled Garmin sync for yesterday's data."""
        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        yesterday = (now - timedelta(days=1)).date()

        logger.info(f"Running daily Garmin sync for {yesterday}")
        return await self.sync_garmin_day(yesterday, session)

    async def run_daily_environment_sync(self, session: AsyncSession) -> dict[str, Any]:
        """Run scheduled environmental sync for yesterday's data."""
        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        yesterday = (now - timedelta(days=1)).date()

        logger.info(f"Running daily environmental sync for {yesterday}")
        return await self.sync_environment_day(yesterday, session)
