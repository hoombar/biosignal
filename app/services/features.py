"""Computed features engine - derives features from raw time-series data."""

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.database import (
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


def _datetime_in_tz(dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert datetime to timezone-aware datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _time_to_datetime(target_date: date, t: time, tz: ZoneInfo) -> datetime:
    """Combine date and time into a naive-UTC datetime for SQLite comparison."""
    aware = datetime.combine(target_date, t, tzinfo=tz)
    return aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _closest_value(samples: list, target_time: datetime, window_minutes: int = 30) -> Optional[float]:
    """Find the sample closest to target time within a window."""
    if not samples:
        return None

    window = timedelta(minutes=window_minutes)
    closest = None
    min_delta = None

    for sample in samples:
        delta = abs(sample.timestamp - target_time)
        if delta <= window:
            if min_delta is None or delta < min_delta:
                min_delta = delta
                closest = sample

    return getattr(closest, 'body_battery', None) if closest else None


async def _get_samples_in_range(
    session: AsyncSession,
    model_class,
    start: datetime,
    end: datetime
) -> list:
    """Get samples within a time range."""
    result = await session.execute(
        select(model_class)
        .where(model_class.timestamp >= start)
        .where(model_class.timestamp < end)
        .order_by(model_class.timestamp)
    )
    return result.scalars().all()


async def compute_sleep_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute sleep-related features."""
    result = await session.execute(
        select(SleepSession).where(SleepSession.date == target_date)
    )
    sleep = result.scalar_one_or_none()

    if not sleep or not sleep.total_sleep_seconds:
        return {}

    total = sleep.total_sleep_seconds
    features = {
        "sleep_hours": total / 3600,
        "sleep_score": sleep.sleep_score,
    }

    if total > 0:
        if sleep.deep_sleep_seconds:
            features["deep_sleep_pct"] = (sleep.deep_sleep_seconds / total) * 100
        if sleep.rem_sleep_seconds:
            features["rem_sleep_pct"] = (sleep.rem_sleep_seconds / total) * 100

    # Sleep efficiency
    if sleep.sleep_start and sleep.sleep_end:
        time_in_bed = (sleep.sleep_end - sleep.sleep_start).total_seconds()
        if time_in_bed > 0:
            features["sleep_efficiency"] = (total / time_in_bed) * 100

    return features


async def compute_hrv_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute HRV features."""
    # Get sleep session to determine overnight window
    result = await session.execute(
        select(SleepSession).where(SleepSession.date == target_date)
    )
    sleep = result.scalar_one_or_none()

    if not sleep or not sleep.sleep_start or not sleep.sleep_end:
        return {}

    # Get HRV samples during sleep
    hrv_samples = await _get_samples_in_range(
        session, HrvSample, sleep.sleep_start, sleep.sleep_end
    )

    if not hrv_samples:
        return {}

    hrv_values = [s.hrv_value for s in hrv_samples]
    features = {
        "hrv_overnight_avg": np.mean(hrv_values),
        "hrv_overnight_min": np.min(hrv_values),
    }

    # Compute slope if we have enough samples
    if len(hrv_values) >= 3:
        x = np.arange(len(hrv_values))
        slope = np.polyfit(x, hrv_values, 1)[0]
        features["hrv_rmssd_slope"] = float(slope)

    return features


async def compute_spo2_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute SpO2 (blood oxygen) features from overnight readings."""
    # Get sleep session to determine overnight window
    result = await session.execute(
        select(SleepSession).where(SleepSession.date == target_date)
    )
    sleep = result.scalar_one_or_none()

    if not sleep or not sleep.sleep_start or not sleep.sleep_end:
        return {}

    # Get SpO2 samples during sleep
    spo2_samples = await _get_samples_in_range(
        session, Spo2Sample, sleep.sleep_start, sleep.sleep_end
    )

    if not spo2_samples:
        return {}

    spo2_values = [s.spo2_value for s in spo2_samples]

    features = {
        "spo2_overnight_avg": float(np.mean(spo2_values)),
        "spo2_overnight_min": int(np.min(spo2_values)),
        "spo2_overnight_max": int(np.max(spo2_values)),
        "spo2_dips_below_94": sum(1 for v in spo2_values if v < 94),
    }

    return features


async def compute_heart_rate_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute heart rate features."""
    day_start = _time_to_datetime(target_date, time(0, 0), tz)
    day_end = day_start + timedelta(days=1)

    hr_samples = await _get_samples_in_range(session, HeartRateSample, day_start, day_end)

    if not hr_samples:
        return {}

    hr_values = [s.heart_rate for s in hr_samples if s.heart_rate > 0]

    if not hr_values:
        return {}

    features = {"hr_max_24h": max(hr_values)}

    # Morning average (6am-12pm)
    morning_start = _time_to_datetime(target_date, time(6, 0), tz)
    morning_end = _time_to_datetime(target_date, time(12, 0), tz)
    morning_hrs = [s.heart_rate for s in hr_samples if morning_start <= s.timestamp < morning_end and s.heart_rate > 0]
    if morning_hrs:
        features["hr_morning_avg"] = np.mean(morning_hrs)

    # Afternoon average (12pm-6pm)
    afternoon_start = _time_to_datetime(target_date, time(12, 0), tz)
    afternoon_end = _time_to_datetime(target_date, time(18, 0), tz)
    afternoon_hrs = [s.heart_rate for s in hr_samples if afternoon_start <= s.timestamp < afternoon_end and s.heart_rate > 0]
    if afternoon_hrs:
        features["hr_afternoon_avg"] = np.mean(afternoon_hrs)

    # 2pm window (1pm-4pm)
    window_start = _time_to_datetime(target_date, time(13, 0), tz)
    window_end = _time_to_datetime(target_date, time(16, 0), tz)
    window_hrs = [s.heart_rate for s in hr_samples if window_start <= s.timestamp < window_end and s.heart_rate > 0]
    if window_hrs:
        features["hr_2pm_window"] = np.mean(window_hrs)

    # Resting HR - lowest 30-minute rolling average
    if len(hr_samples) >= 2:
        window_size = 2  # ~30 mins with 15-min samples
        rolling_avgs = [
            np.mean([s.heart_rate for s in hr_samples[i:i+window_size] if s.heart_rate > 0])
            for i in range(len(hr_samples) - window_size + 1)
        ]
        if rolling_avgs:
            features["resting_hr"] = int(min(rolling_avgs))

    return features


async def compute_body_battery_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute body battery features."""
    day_start = _time_to_datetime(target_date, time(0, 0), tz)
    day_end = day_start + timedelta(days=1)

    bb_samples = await _get_samples_in_range(session, BodyBatterySample, day_start, day_end)

    if not bb_samples:
        return {}

    features = {}

    # Get sleep session for wakeup time
    result = await session.execute(
        select(SleepSession).where(SleepSession.date == target_date)
    )
    sleep = result.scalar_one_or_none()

    if sleep and sleep.sleep_end:
        wakeup_bb = _closest_value(bb_samples, sleep.sleep_end)
        if wakeup_bb is not None:
            features["bb_wakeup"] = wakeup_bb

    # Specific times
    time_9am = _time_to_datetime(target_date, time(9, 0), tz)
    bb_9am = _closest_value(bb_samples, time_9am)
    if bb_9am is not None:
        features["bb_9am"] = bb_9am

    time_12pm = _time_to_datetime(target_date, time(12, 0), tz)
    bb_12pm = _closest_value(bb_samples, time_12pm)
    if bb_12pm is not None:
        features["bb_12pm"] = bb_12pm

    time_2pm = _time_to_datetime(target_date, time(14, 0), tz)
    bb_2pm = _closest_value(bb_samples, time_2pm)
    if bb_2pm is not None:
        features["bb_2pm"] = bb_2pm

    time_6pm = _time_to_datetime(target_date, time(18, 0), tz)
    bb_6pm = _closest_value(bb_samples, time_6pm)
    if bb_6pm is not None:
        features["bb_6pm"] = bb_6pm

    # Drain rates
    if "bb_wakeup" in features and "bb_12pm" in features:
        wakeup_time = sleep.sleep_end if sleep else time_9am
        hours = (time_12pm - wakeup_time).total_seconds() / 3600
        if hours > 0:
            features["bb_morning_drain_rate"] = (features["bb_12pm"] - features["bb_wakeup"]) / hours

    if "bb_12pm" in features and "bb_6pm" in features:
        hours = 6
        features["bb_afternoon_drain_rate"] = (features["bb_6pm"] - features["bb_12pm"]) / hours

    # Daily min
    bb_values = [s.body_battery for s in bb_samples]
    if bb_values:
        features["bb_daily_min"] = min(bb_values)

    return features


async def compute_stress_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute stress features."""
    day_start = _time_to_datetime(target_date, time(0, 0), tz)
    day_end = day_start + timedelta(days=1)

    stress_samples = await _get_samples_in_range(session, StressSample, day_start, day_end)

    if not stress_samples:
        return {}

    # Filter out rest/unmeasured (-1, -2)
    valid_stress = [s for s in stress_samples if s.stress_level > 0]

    if not valid_stress:
        return {}

    features = {}

    # Morning average (6am-12pm)
    morning_start = _time_to_datetime(target_date, time(6, 0), tz)
    morning_end = _time_to_datetime(target_date, time(12, 0), tz)
    morning_stress = [s.stress_level for s in valid_stress if morning_start <= s.timestamp < morning_end]
    if morning_stress:
        features["stress_morning_avg"] = np.mean(morning_stress)

    # Afternoon average (12pm-6pm)
    afternoon_start = _time_to_datetime(target_date, time(12, 0), tz)
    afternoon_end = _time_to_datetime(target_date, time(18, 0), tz)
    afternoon_stress = [s.stress_level for s in valid_stress if afternoon_start <= s.timestamp < afternoon_end]
    if afternoon_stress:
        features["stress_afternoon_avg"] = np.mean(afternoon_stress)

    # 2pm window (1pm-4pm)
    window_start = _time_to_datetime(target_date, time(13, 0), tz)
    window_end = _time_to_datetime(target_date, time(16, 0), tz)
    window_stress = [s.stress_level for s in valid_stress if window_start <= s.timestamp < window_end]
    if window_stress:
        features["stress_2pm_window"] = np.mean(window_stress)

    # Peak stress
    all_stress = [s.stress_level for s in valid_stress]
    if all_stress:
        features["stress_peak"] = max(all_stress)

    # High stress minutes
    high_stress_count = sum(1 for s in valid_stress if s.stress_level > 60)
    features["high_stress_minutes"] = high_stress_count * 15  # Assuming 15-min intervals

    return features


async def compute_activity_features(
    session: AsyncSession,
    target_date: date,
    tz: ZoneInfo
) -> dict:
    """Compute activity and steps features."""
    day_start = _time_to_datetime(target_date, time(0, 0), tz)
    day_end = day_start + timedelta(days=1)

    features = {}

    # Steps
    steps_samples = await _get_samples_in_range(session, StepsSample, day_start, day_end)
    if steps_samples:
        features["steps_total"] = sum(s.steps for s in steps_samples)

        morning_end = _time_to_datetime(target_date, time(12, 0), tz)
        morning_steps = sum(s.steps for s in steps_samples if s.timestamp < morning_end)
        features["steps_morning"] = morning_steps

    # Activities
    result = await session.execute(
        select(Activity)
        .where(Activity.start_time >= day_start)
        .where(Activity.start_time < day_end)
        .order_by(Activity.start_time)
    )
    activities = result.scalars().all()

    if activities:
        # Take the main activity of the day (or most intense)
        main_activity = max(activities, key=lambda a: a.avg_hr or 0)

        features["had_training"] = True
        features["training_type"] = main_activity.activity_type
        features["training_duration_min"] = (main_activity.duration_seconds or 0) / 60
        features["training_avg_hr"] = main_activity.avg_hr

        # Classify intensity
        avg_hr = main_activity.avg_hr or 0
        max_hr = 190  # Default, could be user-specific
        hr_pct = (avg_hr / max_hr) * 100 if max_hr > 0 else 0

        if hr_pct < 70:
            intensity = "low"
        elif hr_pct < 85:
            intensity = "medium"
        else:
            intensity = "high"

        features["training_intensity"] = intensity

        # Hours since training to 2pm
        time_2pm = _time_to_datetime(target_date, time(14, 0), tz)
        hours_diff = (time_2pm - main_activity.end_time).total_seconds() / 3600
        features["hours_since_training"] = hours_diff
    else:
        features["had_training"] = False

    return features


async def compute_habit_features(
    session: AsyncSession,
    target_date: date
) -> dict:
    """Compute habit features as a list of habit objects."""
    result = await session.execute(
        select(DailyHabit).where(DailyHabit.date == target_date)
    )
    habits = result.scalars().all()

    habit_list = []

    for habit in habits:
        # Convert value based on type
        if habit.habit_type == "boolean":
            value = 1 if habit.habit_value.lower() == "true" else 0
        elif habit.habit_type == "counter":
            value = int(habit.habit_value) if habit.habit_value else 0
        else:
            value = int(habit.habit_value) if habit.habit_value.isdigit() else 0

        habit_list.append({
            "name": habit.habit_name,
            "value": value,
            "type": habit.habit_type or "counter"
        })

    return {"habits": habit_list}


async def compute_daily_features(
    session: AsyncSession,
    target_date: date,
    timezone: str = "Europe/London"
) -> dict:
    """
    Compute all features for a single day.

    Returns:
        Dict with all computed features.
    """
    tz = ZoneInfo(timezone)
    features = {"date": target_date.isoformat()}

    # Compute each category
    sleep_features = await compute_sleep_features(session, target_date, tz)
    features.update(sleep_features)

    hrv_features = await compute_hrv_features(session, target_date, tz)
    features.update(hrv_features)

    spo2_features = await compute_spo2_features(session, target_date, tz)
    features.update(spo2_features)

    hr_features = await compute_heart_rate_features(session, target_date, tz)
    features.update(hr_features)

    bb_features = await compute_body_battery_features(session, target_date, tz)
    features.update(bb_features)

    stress_features = await compute_stress_features(session, target_date, tz)
    features.update(stress_features)

    activity_features = await compute_activity_features(session, target_date, tz)
    features.update(activity_features)

    habit_features = await compute_habit_features(session, target_date)
    features.update(habit_features)

    logger.debug(f"Computed {len(features)} features for {target_date}")
    return features


async def compute_features_range(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    timezone: str = "Europe/London"
) -> list[dict]:
    """
    Compute features for a date range.

    Returns:
        List of feature dicts, one per day.
    """
    results = []
    current = start_date

    while current <= end_date:
        features = await compute_daily_features(session, current, timezone)
        results.append(features)
        current += timedelta(days=1)

    return results
