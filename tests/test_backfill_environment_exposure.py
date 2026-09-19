from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.models.database import EnvironmentalMetric, SleepSession
from app.services.environmental import EnvironmentalMetricValue
from scripts.backfill_environment_exposure import (
    backfill_environment_exposure,
    default_backfill_start,
)


class FakePollenProvider:
    async def daily_metrics(self, target_date, tz, latitude, longitude):
        return [EnvironmentalMetricValue(
            source="open_meteo_air_quality",
            metric_key="grass_pollen_avg",
            value=float(target_date.day),
            unit="grains/m3",
            category="Pollen",
        )]


class FakeWeatherProvider:
    async def daily_metrics(self, target_date, tz, latitude, longitude):
        return [
            EnvironmentalMetricValue(
                source="open_meteo_weather",
                metric_key="temperature_2m_avg",
                value=99.0,
                unit="degC",
                category="Weather",
            ),
            EnvironmentalMetricValue(
                source="open_meteo_weather",
                metric_key="temperature_2m_daytime_max",
                value=25.0,
                unit="degC",
                category="Weather",
                raw_metadata={"provider_url": "archive"},
            ),
            EnvironmentalMetricValue(
                source="open_meteo_weather",
                metric_key="temperature_2m_overnight_mean",
                value=15.0,
                unit="degC",
                category="Weather",
                raw_metadata={"provider_url": "archive"},
            ),
        ]


@pytest.mark.asyncio
async def test_default_backfill_start_precedes_earliest_tracked_date(async_session):
    async_session.add(SleepSession(
        date=date(2025, 1, 10),
        sleep_start=datetime(2025, 1, 9, 23),
        sleep_end=datetime(2025, 1, 10, 7),
    ))
    await async_session.commit()

    assert await default_backfill_start(async_session) == date(2025, 1, 3)


@pytest.mark.asyncio
async def test_backfill_is_idempotent_and_does_not_replace_daily_weather_metrics(
    async_session,
):
    kwargs = {
        "session": async_session,
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 2),
        "tz": ZoneInfo("Europe/London"),
        "latitude": 51.5074,
        "longitude": -0.1278,
        "pollen_provider": FakePollenProvider(),
        "weather_provider": FakeWeatherProvider(),
    }

    first = await backfill_environment_exposure(**kwargs)
    second = await backfill_environment_exposure(**kwargs)

    rows = (await async_session.execute(select(EnvironmentalMetric))).scalars().all()
    count = await async_session.scalar(select(func.count()).select_from(EnvironmentalMetric))
    assert first == {"days": 2, "metrics": 6, "failures": []}
    assert second == first
    assert count == 6
    assert "temperature_2m_avg" not in {row.metric_key for row in rows}
    assert {row.raw_metadata.get("provider_url") for row in rows if row.category == "Weather"} == {"archive"}
