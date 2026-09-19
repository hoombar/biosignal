#!/usr/bin/env python3
"""Backfill pollen and day/night heat summaries for sustained-exposure analysis."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.models.database import (
    Activity,
    BodyBatterySample,
    ContextEvent,
    DailyHabit,
    EnvironmentalMetric,
    GymSessionLog,
    Habit,
    HeartRateSample,
    HrvSample,
    SleepSession,
    Spo2Sample,
    StepsSample,
    StressSample,
    SupplementLog,
)
from app.services.environmental import (
    EnvironmentalMetricValue,
    OpenMeteoPollenProvider,
    OpenMeteoWeatherProvider,
    location_key,
)


logger = logging.getLogger("backfill_environment_exposure")
HEAT_SUMMARY_KEYS = {
    "temperature_2m_daytime_max",
    "temperature_2m_overnight_mean",
}


async def default_backfill_start(session: AsyncSession) -> date | None:
    """Return seven days before the earliest observed or manually logged data."""
    columns = (
        SleepSession.date,
        Habit.tracking_start_date,
        DailyHabit.date,
        GymSessionLog.date,
        SupplementLog.date,
        ContextEvent.start_date,
        Activity.start_time,
        HeartRateSample.timestamp,
        BodyBatterySample.timestamp,
        StressSample.timestamp,
        HrvSample.timestamp,
        Spo2Sample.timestamp,
        StepsSample.timestamp,
    )
    earliest: list[date] = []
    for column in columns:
        value = await session.scalar(select(func.min(column)))
        if value is not None:
            earliest.append(value.date() if isinstance(value, datetime) else value)
    return min(earliest) - timedelta(days=7) if earliest else None


async def _upsert_metrics(
    session: AsyncSession,
    target_date: date,
    metrics: list[EnvironmentalMetricValue],
    loc_key: str,
) -> None:
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
        statement = insert(EnvironmentalMetric.__table__).values(**data).on_conflict_do_update(
            index_elements=["date", "source", "metric_key", "location_key"],
            set_={
                key: value
                for key, value in data.items()
                if key not in {"date", "source", "metric_key", "location_key"}
            },
        )
        await session.execute(statement)


async def backfill_environment_exposure(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    tz: ZoneInfo,
    latitude: float,
    longitude: float,
    pollen_provider: OpenMeteoPollenProvider | None = None,
    weather_provider: OpenMeteoWeatherProvider | None = None,
    delay_seconds: float = 0,
) -> dict:
    """Backfill source metrics without replacing existing daily weather aggregates."""
    pollen_provider = pollen_provider or OpenMeteoPollenProvider()
    weather_provider = weather_provider or OpenMeteoWeatherProvider(
        base_url=OpenMeteoWeatherProvider.archive_url
    )
    loc_key = location_key(latitude, longitude)
    failures: list[str] = []
    metric_count = 0
    day_count = 0
    current = start_date

    while current <= end_date:
        day_count += 1
        metrics: list[EnvironmentalMetricValue] = []
        try:
            metrics.extend(
                await pollen_provider.daily_metrics(current, tz, latitude, longitude)
            )
        except Exception as exc:
            failures.append(f"{current.isoformat()} pollen: {exc}")
            logger.warning("Pollen backfill failed for %s: %s", current, exc)

        try:
            weather = await weather_provider.daily_metrics(
                current, tz, latitude, longitude
            )
            metrics.extend(
                metric for metric in weather if metric.metric_key in HEAT_SUMMARY_KEYS
            )
        except Exception as exc:
            failures.append(f"{current.isoformat()} weather: {exc}")
            logger.warning("Weather backfill failed for %s: %s", current, exc)

        try:
            await _upsert_metrics(session, current, metrics, loc_key)
            await session.commit()
            metric_count += len(metrics)
        except Exception:
            await session.rollback()
            raise

        logger.info("Backfilled %s: %d metrics", current, len(metrics))
        current += timedelta(days=1)
        if delay_seconds > 0 and current <= end_date:
            await asyncio.sleep(delay_seconds)

    return {"days": day_count, "metrics": metric_count, "failures": failures}


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


async def _run(start: date | None, end: date | None) -> int:
    settings = get_settings()
    if settings.environment_latitude is None or settings.environment_longitude is None:
        raise RuntimeError("ENVIRONMENT_LATITUDE and ENVIRONMENT_LONGITUDE must be set")

    tz = ZoneInfo(settings.tz)
    resolved_end = end or (datetime.now(tz).date() - timedelta(days=1))
    async with async_session_maker() as session:
        resolved_start = start or await default_backfill_start(session)
        if resolved_start is None:
            raise RuntimeError("No tracked data found; pass --from explicitly")
        if resolved_start > resolved_end:
            raise ValueError("--from must be on or before --to")

        logger.info("Backfilling environmental exposure from %s through %s", resolved_start, resolved_end)
        result = await backfill_environment_exposure(
            session,
            resolved_start,
            resolved_end,
            tz,
            settings.environment_latitude,
            settings.environment_longitude,
            delay_seconds=0.25,
        )

    logger.info(
        "Backfill complete: %d days, %d metrics, %d provider failures",
        result["days"],
        result["metrics"],
        len(result["failures"]),
    )
    return 1 if result["failures"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", type=_parse_date)
    parser.add_argument("--to", dest="end", type=_parse_date)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(asyncio.run(_run(args.start, args.end)))


if __name__ == "__main__":
    main()
