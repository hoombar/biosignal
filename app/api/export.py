"""Export API endpoints."""

import csv
import io
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.models.database import Habit
from app.services.habit_config import list_habit_display_entries
from app.services.supplements import list_supplement_items
from app.services.features import compute_features_range

router = APIRouter(prefix="/api/export", tags=["export"])


# Feature metadata for documentation
FEATURE_METADATA = {
    # Sleep features
    "sleep_hours": {"description": "Total sleep duration", "unit": "hours", "category": "Sleep"},
    "deep_sleep_pct": {"description": "Deep sleep percentage", "unit": "%", "category": "Sleep"},
    "rem_sleep_pct": {"description": "REM sleep percentage", "unit": "%", "category": "Sleep"},
    "sleep_efficiency": {"description": "Time asleep / time in bed", "unit": "%", "category": "Sleep"},
    "sleep_score": {"description": "Garmin sleep score", "unit": "0-100", "category": "Sleep"},

    # HRV features
    "hrv_overnight_avg": {"description": "Average overnight HRV", "unit": "ms", "category": "HRV"},
    "hrv_overnight_min": {"description": "Minimum overnight HRV", "unit": "ms", "category": "HRV"},
    "hrv_rmssd_slope": {"description": "HRV trend overnight (slope)", "unit": "ms/reading", "category": "HRV"},

    # SpO2 features
    "spo2_overnight_avg": {"description": "Average overnight blood oxygen", "unit": "%", "category": "SpO2"},
    "spo2_overnight_min": {"description": "Minimum overnight blood oxygen", "unit": "%", "category": "SpO2"},
    "spo2_overnight_max": {"description": "Maximum overnight blood oxygen", "unit": "%", "category": "SpO2"},
    "spo2_dips_below_94": {"description": "SpO2 readings below 94%", "unit": "count", "category": "SpO2"},

    # Heart rate features
    "resting_hr": {"description": "Resting heart rate (lowest 30-min avg)", "unit": "bpm", "category": "Heart Rate"},
    "hr_morning_avg": {"description": "Average HR 6am-12pm", "unit": "bpm", "category": "Heart Rate"},
    "hr_afternoon_avg": {"description": "Average HR 12pm-6pm", "unit": "bpm", "category": "Heart Rate"},
    "hr_2pm_window": {"description": "Average HR 1pm-4pm", "unit": "bpm", "category": "Heart Rate"},
    "hr_max_24h": {"description": "Maximum HR in 24h", "unit": "bpm", "category": "Heart Rate"},
    "hr_recovery_slope": {"description": "HR recovery rate after training", "unit": "bpm/min", "category": "Heart Rate"},

    # Body Battery features
    "bb_wakeup": {"description": "Body Battery at wake time", "unit": "0-100", "category": "Body Battery"},
    "bb_morning_drain_rate": {"description": "BB change per hour 6am-12pm", "unit": "points/hour", "category": "Body Battery"},
    "bb_afternoon_drain_rate": {"description": "BB change per hour 12pm-6pm", "unit": "points/hour", "category": "Body Battery"},
    "bb_daily_min": {"description": "Minimum BB of the day", "unit": "0-100", "category": "Body Battery"},

    # Stress features
    "stress_morning_avg": {"description": "Average stress 6am-12pm", "unit": "0-100", "category": "Stress"},
    "stress_afternoon_avg": {"description": "Average stress 12pm-6pm", "unit": "0-100", "category": "Stress"},
    "stress_2pm_window": {"description": "Average stress 1pm-4pm", "unit": "0-100", "category": "Stress"},
    "stress_peak": {"description": "Maximum stress level", "unit": "0-100", "category": "Stress"},
    "high_stress_minutes": {"description": "Minutes with stress > 60", "unit": "minutes", "category": "Stress"},

    # Activity features
    "steps_total": {"description": "Total daily steps", "unit": "steps", "category": "Activity"},
    "steps_morning": {"description": "Steps before 12pm", "unit": "steps", "category": "Activity"},
    "steps_peak_hour": {"description": "Highest hourly step count", "unit": "steps", "category": "Activity"},
    "steps_active_hours": {"description": "Hours with at least 500 steps", "unit": "hours", "category": "Activity"},
    "steps_walking_hours": {"description": "Hours with at least 2500 steps", "unit": "hours", "category": "Activity"},
    "steps_peak_hour_share": {"description": "Share of daily steps in the peak hour", "unit": "ratio", "category": "Activity"},
    "steps_peak_30min": {"description": "Highest 30-minute step count", "unit": "steps", "category": "Activity"},
    "steps_walking_30min_blocks": {"description": "30-minute blocks with sustained walking-like steps", "unit": "blocks", "category": "Activity"},
    "steps_peak_30min_share": {"description": "Share of daily steps in the peak 30-minute block", "unit": "ratio", "category": "Activity"},
    "walk_peak_30min_avg_hr": {"description": "Average HR during the highest-step walking block", "unit": "bpm", "category": "Activity"},
    "walk_peak_30min_hr_delta": {"description": "Peak walking block HR above daily resting HR", "unit": "bpm", "category": "Activity"},
    "walk_hr_elevated_30min_blocks": {"description": "Walking blocks with HR at least 20 bpm above resting", "unit": "blocks", "category": "Activity"},
    "steps_peak_45min": {"description": "Highest rolling 45-minute step count", "unit": "steps", "category": "Activity"},
    "steps_walking_45min_windows": {"description": "Rolling 45-minute windows with at least 3000 sustained steps", "unit": "windows", "category": "Activity"},
    "steps_peak_45min_share": {"description": "Share of daily steps in the peak 45-minute window", "unit": "ratio", "category": "Activity"},
    "walk_peak_45min_avg_hr": {"description": "Average HR during the highest-step 45-minute walking window", "unit": "bpm", "category": "Activity"},
    "walk_peak_45min_hr_delta": {"description": "Peak 45-minute walking window HR above daily resting HR", "unit": "bpm", "category": "Activity"},
    "walk_hr_elevated_45min_windows": {"description": "3000-step 45-minute windows with HR at least 20 bpm above resting", "unit": "windows", "category": "Activity"},
    "had_likely_walk": {"description": "At least one sustained 30-minute walking-like step block (step-only)", "unit": "boolean", "category": "Activity"},
    "had_likely_brisk_walk": {"description": "Preferred walk signal: sustained 45-minute step window with elevated HR", "unit": "boolean", "category": "Activity"},
    "active_minutes": {"description": "Minutes of moderate+ activity", "unit": "minutes", "category": "Activity"},
    "had_training": {"description": "Training session occurred", "unit": "boolean", "category": "Activity"},
    "training_type": {"description": "Type of training", "unit": "text", "category": "Activity"},
    "training_duration_min": {"description": "Training duration", "unit": "minutes", "category": "Activity"},
    "training_avg_hr": {"description": "Average HR during training", "unit": "bpm", "category": "Activity"},
    "training_intensity": {"description": "Training intensity classification", "unit": "low/medium/high", "category": "Activity"},
    "hours_since_training": {"description": "Hours from training end to 2pm", "unit": "hours", "category": "Activity"},

    # Environmental features
    "daylight_minutes": {"description": "Minutes between local sunrise and sunset", "unit": "minutes", "category": "Light"},
    "sunrise_minutes_after_midnight": {"description": "Local sunrise time as minutes after midnight", "unit": "minutes", "category": "Light"},
    "sunset_minutes_after_midnight": {"description": "Local sunset time as minutes after midnight", "unit": "minutes", "category": "Light"},
    "solar_noon_minutes_after_midnight": {"description": "Approximate local solar noon as minutes after midnight", "unit": "minutes", "category": "Light"},

    # Pollen features
    "alder_pollen_avg": {"description": "Daily average alder pollen", "unit": "grains/m3", "category": "Pollen"},
    "alder_pollen_max": {"description": "Daily maximum alder pollen", "unit": "grains/m3", "category": "Pollen"},
    "birch_pollen_avg": {"description": "Daily average birch pollen", "unit": "grains/m3", "category": "Pollen"},
    "birch_pollen_max": {"description": "Daily maximum birch pollen", "unit": "grains/m3", "category": "Pollen"},
    "grass_pollen_avg": {"description": "Daily average grass pollen", "unit": "grains/m3", "category": "Pollen"},
    "grass_pollen_max": {"description": "Daily maximum grass pollen", "unit": "grains/m3", "category": "Pollen"},
    "mugwort_pollen_avg": {"description": "Daily average mugwort pollen", "unit": "grains/m3", "category": "Pollen"},
    "mugwort_pollen_max": {"description": "Daily maximum mugwort pollen", "unit": "grains/m3", "category": "Pollen"},
    "olive_pollen_avg": {"description": "Daily average olive pollen", "unit": "grains/m3", "category": "Pollen"},
    "olive_pollen_max": {"description": "Daily maximum olive pollen", "unit": "grains/m3", "category": "Pollen"},
    "ragweed_pollen_avg": {"description": "Daily average ragweed pollen", "unit": "grains/m3", "category": "Pollen"},
    "ragweed_pollen_max": {"description": "Daily maximum ragweed pollen", "unit": "grains/m3", "category": "Pollen"},

    # Weather features
    "temperature_2m_avg": {"description": "Daily average outdoor temperature at 2m", "unit": "degC", "category": "Weather"},
    "temperature_2m_min": {"description": "Daily minimum outdoor temperature at 2m", "unit": "degC", "category": "Weather"},
    "temperature_2m_max": {"description": "Daily maximum outdoor temperature at 2m", "unit": "degC", "category": "Weather"},
    "apparent_temperature_avg": {"description": "Daily average apparent temperature", "unit": "degC", "category": "Weather"},
    "apparent_temperature_max": {"description": "Daily maximum apparent temperature", "unit": "degC", "category": "Weather"},
    "relative_humidity_2m_avg": {"description": "Daily average relative humidity at 2m", "unit": "%", "category": "Weather"},
    "relative_humidity_2m_max": {"description": "Daily maximum relative humidity at 2m", "unit": "%", "category": "Weather"},
    "dew_point_2m_avg": {"description": "Daily average dew point at 2m", "unit": "degC", "category": "Weather"},
    "precipitation_sum": {"description": "Daily total precipitation", "unit": "mm", "category": "Weather"},
    "precipitation_hours": {"description": "Hours with measurable precipitation", "unit": "hours", "category": "Weather"},
    "rain_sum": {"description": "Daily total rain", "unit": "mm", "category": "Weather"},
    "wind_speed_10m_max": {"description": "Daily maximum wind speed at 10m", "unit": "km/h", "category": "Weather"},
    "cloud_cover_avg": {"description": "Daily average cloud cover", "unit": "%", "category": "Weather"},

    # Gym features
    "gym_had_session": {"description": "Gym session logged", "unit": "boolean", "category": "Gym"},
    "gym_session_completed": {"description": "Gym session marked finished", "unit": "boolean", "category": "Gym"},
    "gym_completed_activity_count": {"description": "Completed gym activities", "unit": "count", "category": "Gym"},
    "gym_planned_activity_count": {"description": "Planned gym activities", "unit": "count", "category": "Gym"},
    "gym_completion_ratio": {"description": "Completed / planned gym activities", "unit": "ratio", "category": "Gym"},
    "gym_strength_volume_kg": {"description": "Completed strength volume", "unit": "kg-reps", "category": "Gym"},
    "gym_easy_activity_count": {"description": "Gym activities rated easy", "unit": "count", "category": "Gym"},
    "gym_normal_activity_count": {"description": "Gym activities rated normal", "unit": "count", "category": "Gym"},
    "gym_hard_activity_count": {"description": "Gym activities rated hard", "unit": "count", "category": "Gym"},
    "gym_template_name": {"description": "Gym template used", "unit": "text", "category": "Gym"},

}


async def _build_feature_metadata(db: AsyncSession) -> dict[str, dict]:
    """Return metadata including dynamic habit entries from settings/data."""
    features = {k: v.copy() for k, v in FEATURE_METADATA.items()}
    habits = (await db.execute(
        select(Habit).where(Habit.source == "manual")
    )).scalars().all()
    habit_by_name = {habit.name: habit for habit in habits}

    for entry in await list_habit_display_entries(db):
        habit_name = entry["habit_name"]
        label = entry["display_name"] or habit_name.replace("_", " ")
        habit = habit_by_name.get(habit_name)
        habit_meta = {
            "description": f"Tracked habit: {label}",
            "unit": "count",
            "category": "Habits",
        }
        if habit is not None:
            habit_meta.update({
                "habit_type": habit.habit_type,
                "target_value": habit.target_value,
                "is_negative": habit.is_negative,
                "period": habit.period,
            })
        features[habit_name] = habit_meta.copy()
        features[f"habit_{habit_name}"] = habit_meta

    for item in await list_supplement_items(db):
        features[f"supplement:{item['key']}"] = {
            "description": f"Supplement: {item['name']}",
            "unit": "boolean",
            "category": "Supplements",
        }

    return features


def _with_flattened_habit_values(features: dict) -> dict:
    """Add stable habit_* numeric columns while preserving nested habit data."""
    row = dict(features)
    for habit in row.get("habits", []) or []:
        name = habit.get("name")
        if name:
            row[f"habit_{name}"] = habit.get("value")
    return row


@router.get("")
async def export_features(
    format: str = Query("csv", pattern="^(csv|json)$"),
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
    include_metadata: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Export computed features for all days.

    Args:
        format: Output format (csv or json)
        days: Last N days (alternative to start/end)
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        include_metadata: Include metadata header (CSV only)
    """
    settings = get_settings()
    metadata = await _build_feature_metadata(db)

    # Determine date range
    if start and end:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    elif days:
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
    else:
        # Default: all available data (up to 1 year)
        end_date = date.today()
        start_date = end_date - timedelta(days=365)

    # Compute features
    features_list = await compute_features_range(
        db,
        start_date,
        end_date,
        timezone=settings.tz
    )
    export_rows = [_with_flattened_habit_values(row) for row in features_list]

    if format == "json":
        return {
            "data": export_rows,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "count": len(export_rows)
        }

    # CSV format
    if not export_rows:
        return StreamingResponse(
            iter(["date\n"]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=energy_tracker_export_{start_date}_{end_date}.csv"}
        )

    # Create CSV
    output = io.StringIO()

    # Get all possible columns across rows and metadata
    all_columns = set()
    for row in export_rows:
        all_columns.update(row.keys())

    # Order columns logically
    ordered_columns = ["date"]

    # Add known columns by category
    for category in ["Sleep", "HRV", "SpO2", "Heart Rate", "Body Battery", "Stress", "Activity", "Gym", "Light", "Pollen", "Weather", "Habits", "Supplements"]:
        for col, meta in metadata.items():
            if meta["category"] == category and col in all_columns:
                ordered_columns.append(col)

    # Add any remaining columns
    for col in all_columns:
        if col not in ordered_columns:
            ordered_columns.append(col)

    writer = csv.DictWriter(output, fieldnames=ordered_columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(export_rows)

    # Get CSV content
    csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=energy_tracker_export_{start_date}_{end_date}.csv"}
    )


@router.get("/timeseries")
async def export_timeseries(
    type: str = Query(..., pattern="^(heart_rate|body_battery|stress|hrv|spo2|steps)$"),
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Export raw time-series data.

    Args:
        type: Data type to export
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
    """
    from datetime import datetime
    from sqlalchemy import select
    from app.models.database import (
        HeartRateSample,
        BodyBatterySample,
        StressSample,
        HrvSample,
        Spo2Sample,
        StepsSample,
    )

    start_date = datetime.fromisoformat(start + "T00:00:00")
    end_date = datetime.fromisoformat(end + "T23:59:59")

    # Select appropriate model
    model_map = {
        "heart_rate": (HeartRateSample, "heart_rate"),
        "body_battery": (BodyBatterySample, "body_battery"),
        "stress": (StressSample, "stress_level"),
        "hrv": (HrvSample, "hrv_value"),
        "spo2": (Spo2Sample, "spo2_value"),
        "steps": (StepsSample, "steps"),
    }

    model_class, value_field = model_map[type]

    # Query samples
    result = await db.execute(
        select(model_class)
        .where(model_class.timestamp >= start_date)
        .where(model_class.timestamp <= end_date)
        .order_by(model_class.timestamp)
    )
    samples = result.scalars().all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "value"])

    for sample in samples:
        writer.writerow([
            sample.timestamp.isoformat(),
            getattr(sample, value_field)
        ])

    csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={type}_{start}_{end}.csv"}
    )


@router.get("/metadata")
async def get_metadata(db: AsyncSession = Depends(get_db)):
    """Get feature metadata including definitions and units."""
    features = await _build_feature_metadata(db)
    return {
        "features": features,
        "suggested_analysis_prompts": [
            "Analyze correlations between sleep metrics and a selected habit outcome",
            "Identify which tracked habits and physiology metrics best predict your selected target",
            "Compare body battery trends between positive and negative target days",
            "Determine whether training intensity or timing affects your selected target",
            "Find the sleep duration and quality range associated with better target outcomes",
        ],
        "data_completeness_note": "Some features may have null values if data was not available for that day"
    }
