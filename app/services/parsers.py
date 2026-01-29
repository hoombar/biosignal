"""Parsers to convert raw Garmin/HabitSync JSON into ORM models."""

from datetime import datetime, date, timezone
from typing import Optional
import logging

from app.models.database import (
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


def _timestamp_to_datetime(ts_ms: int) -> datetime:
    """Convert epoch milliseconds to UTC datetime."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def _iso_to_datetime(iso_str: str) -> datetime:
    """Convert ISO 8601 string to datetime."""
    # Handle format like "2025-01-28T22:00:00.0"
    if iso_str.endswith('.0'):
        iso_str = iso_str[:-2]
    return datetime.fromisoformat(iso_str).replace(tzinfo=timezone.utc)


def parse_heart_rate(raw: dict, date: date) -> list[HeartRateSample]:
    """Parse heart rate JSON into HeartRateSample objects."""
    samples = []

    hr_values = raw.get("heartRateValues", [])
    for entry in hr_values:
        if len(entry) >= 2:
            ts_ms, hr_value = entry[0], entry[1]
            if hr_value is not None and hr_value > 0:
                samples.append(HeartRateSample(
                    timestamp=_timestamp_to_datetime(ts_ms),
                    heart_rate=hr_value
                ))

    logger.debug(f"Parsed {len(samples)} heart rate samples for {date}")
    return samples


def parse_body_battery(raw: list | dict, date: date) -> list[BodyBatterySample]:
    """Parse body battery JSON into BodyBatterySample objects."""
    samples = []

    # Handle list response
    data_list = raw if isinstance(raw, list) else [raw]

    for day_data in data_list:
        bb_values = day_data.get("bodyBatteryValuesArray", [])
        for entry in bb_values:
            if len(entry) >= 2:
                ts_ms, bb_level = entry[0], entry[1]
                if bb_level is not None:
                    samples.append(BodyBatterySample(
                        timestamp=_timestamp_to_datetime(ts_ms),
                        body_battery=bb_level
                    ))

    logger.debug(f"Parsed {len(samples)} body battery samples for {date}")
    return samples


def parse_stress(raw: dict, date: date) -> list[StressSample]:
    """Parse stress JSON into StressSample objects."""
    samples = []

    stress_values = raw.get("stressValuesArray", [])
    start_ts = raw.get("startTimestampGMT") or raw.get("startTimestampLocal")

    if start_ts:
        for entry in stress_values:
            if len(entry) >= 2:
                offset_ms, stress_level = entry[0], entry[1]
                timestamp = _timestamp_to_datetime(start_ts + offset_ms)
                # Store all values including -1/-2 (rest/unmeasured)
                samples.append(StressSample(
                    timestamp=timestamp,
                    stress_level=stress_level
                ))

    logger.debug(f"Parsed {len(samples)} stress samples for {date}")
    return samples


def parse_hrv(raw: Optional[dict], date: date) -> list[HrvSample]:
    """Parse HRV JSON into HrvSample objects."""
    if raw is None:
        return []

    samples = []

    # Try different HRV structures
    hrv_readings = raw.get("hrvReadings", [])
    for reading in hrv_readings:
        ts_ms = reading.get("timestampGMT")
        hrv_value = reading.get("hrv")
        if ts_ms and hrv_value:
            samples.append(HrvSample(
                timestamp=_timestamp_to_datetime(ts_ms),
                hrv_value=float(hrv_value),
                reading_type="overnight"
            ))

    # Also check for summary values
    summary = raw.get("hrvSummary", {})
    if summary.get("lastNightAvg"):
        # Use end timestamp as the reading time
        end_ts = raw.get("endTimestampGMT")
        if end_ts:
            samples.append(HrvSample(
                timestamp=_timestamp_to_datetime(end_ts),
                hrv_value=float(summary["lastNightAvg"]),
                reading_type="overnight_avg"
            ))

    logger.debug(f"Parsed {len(samples)} HRV samples for {date}")
    return samples


def parse_spo2(raw: Optional[dict], date: date) -> list[Spo2Sample]:
    """Parse SpO2 JSON into Spo2Sample objects."""
    if raw is None:
        return []

    samples = []

    spo2_values = raw.get("spO2ValueDescriptorDTOList", [])
    for entry in spo2_values:
        ts_ms = entry.get("readingTimestampGMT")
        spo2_value = entry.get("spO2Value")
        if ts_ms and spo2_value:
            samples.append(Spo2Sample(
                timestamp=_timestamp_to_datetime(ts_ms),
                spo2_value=spo2_value
            ))

    logger.debug(f"Parsed {len(samples)} SpO2 samples for {date}")
    return samples


def parse_steps(raw: dict, date: date) -> list[StepsSample]:
    """Parse steps JSON into StepsSample objects."""
    samples = []

    steps_per_hour = raw.get("stepsPerHour", [])
    for entry in steps_per_hour:
        start_gmt = entry.get("startGMT")
        steps = entry.get("steps")
        if start_gmt and steps is not None:
            timestamp = _iso_to_datetime(start_gmt)
            samples.append(StepsSample(
                timestamp=timestamp,
                steps=steps,
                duration_seconds=3600  # Hourly intervals
            ))

    logger.debug(f"Parsed {len(samples)} steps samples for {date}")
    return samples


def parse_sleep(raw: dict, date: date) -> Optional[SleepSession]:
    """Parse sleep JSON into SleepSession object."""
    sleep_dto = raw.get("dailySleepDTO", {})

    if not sleep_dto:
        return None

    # Extract timestamps
    sleep_start_ms = sleep_dto.get("sleepStartTimestampGMT")
    sleep_end_ms = sleep_dto.get("sleepEndTimestampGMT")

    # Extract sleep score
    sleep_scores = sleep_dto.get("sleepScores", {})
    overall_score = sleep_scores.get("overall", {}).get("value")

    session = SleepSession(
        date=date,
        sleep_start=_timestamp_to_datetime(sleep_start_ms) if sleep_start_ms else None,
        sleep_end=_timestamp_to_datetime(sleep_end_ms) if sleep_end_ms else None,
        total_sleep_seconds=sleep_dto.get("sleepTimeSeconds"),
        deep_sleep_seconds=sleep_dto.get("deepSleepSeconds"),
        light_sleep_seconds=sleep_dto.get("lightSleepSeconds"),
        rem_sleep_seconds=sleep_dto.get("remSleepSeconds"),
        awake_seconds=sleep_dto.get("awakeSleepSeconds"),
        sleep_score=overall_score,
        avg_overnight_spo2=sleep_dto.get("averageSpO2Value"),
        avg_overnight_rr=sleep_dto.get("averageRespirationValue"),
        raw_sleep_levels=sleep_dto.get("sleepLevels")
    )

    logger.debug(f"Parsed sleep session for {date}")
    return session


def parse_activities(raw: list) -> list[Activity]:
    """Parse activities JSON into Activity objects."""
    activities = []

    for activity_data in raw:
        activity_id = str(activity_data.get("activityId"))
        activity_type_data = activity_data.get("activityType", {})
        activity_type = activity_type_data.get("typeKey", "unknown")

        start_time_str = activity_data.get("startTimeGMT")
        if start_time_str:
            start_time = _iso_to_datetime(start_time_str)
            duration = activity_data.get("duration", 0)
            end_time = datetime.fromtimestamp(
                start_time.timestamp() + duration,
                tz=timezone.utc
            )

            activities.append(Activity(
                garmin_activity_id=activity_id,
                activity_type=activity_type,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                avg_hr=activity_data.get("averageHR"),
                max_hr=activity_data.get("maxHR"),
                min_hr=activity_data.get("minHR"),
                calories=activity_data.get("calories"),
                avg_stress=activity_data.get("avgStress"),
                training_effect_aerobic=activity_data.get("trainingEffect"),
                training_effect_anaerobic=activity_data.get("anaerobicTrainingEffect"),
                hr_zones_json=activity_data.get("hrTimeInZones"),
                raw_data=activity_data
            ))

    logger.debug(f"Parsed {len(activities)} activities")
    return activities
