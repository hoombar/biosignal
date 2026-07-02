"""Correlation and pattern analysis engine."""

import logging
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
import numpy as np
from scipy import stats
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    BodyBatterySample,
    ContextEvent,
    DailyHabit,
    EnvironmentalMetric,
    Habit,
    SleepSession,
    StressSample,
    SupplementLog,
)
from app.services.habit_config import get_default_habit_name
from app.services.features import compute_features_range
from app.services.supplements import supplement_feature_name

logger = logging.getLogger(__name__)


def _day_boundary(target_date: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(target_date, time(0, 0), tzinfo=tz).astimezone(dt_timezone.utc).replace(tzinfo=None)


def _to_numeric(value) -> float | None:
    """Convert value to numeric, handling booleans and None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _get_habit_value(features: dict, habit_name: str) -> float | None:
    """Extract a habit value from the habits list."""
    habits = features.get("habits", [])
    for h in habits:
        if h["name"] == habit_name:
            return _to_numeric(h["value"])
    return None


def _get_supplement_value(features: dict, supplement_name: str) -> float | None:
    """Extract an individual supplement item value from flattened supplement entries."""
    for item in features.get("supplement_items", []):
        if item["key"] == supplement_name:
            return _to_numeric(item["value"])
    return None


def _flatten_habits(features: dict, exclude_habit: str | None = None) -> dict:
    """Flatten habits list into individual feature fields."""
    result = {}
    habits = features.get("habits", [])
    for h in habits:
        if exclude_habit and h["name"] == exclude_habit:
            continue
        result[f"habit_{h['name']}"] = _to_numeric(h["value"])
    return result


def _parse_correlation_target(
    target: str | None,
    target_habit: str | None,
) -> tuple[str, str]:
    """Resolve target selector into kind+name.

    Returns:
        ("habit", "<habit_name>") for habit targets
        ("metric", "<metric_key>") for top-level numeric metric targets
        ("supplement", "<supplement_key>") for supplement item targets
    """
    if target:
        target = target.strip()
        if target.startswith("habit:"):
            return "habit", target[6:]
        if target.startswith("supplement:"):
            return "supplement", target[11:]
        return "metric", target

    if target_habit:
        return "habit", target_habit

    raise ValueError("Either target or target_habit must be provided")


def _get_target_value(features: dict, target_kind: str, target_name: str) -> float | None:
    """Extract target value from either habits list or top-level metric field."""
    if target_kind == "habit":
        return _get_habit_value(features, target_name)
    if target_kind == "supplement":
        return _get_supplement_value(features, target_name)
    return _to_numeric(features.get(target_name))


def _target_selector(target_kind: str, target_name: str) -> str:
    if target_kind == "habit":
        return f"habit:{target_name}"
    if target_kind == "supplement":
        return f"supplement:{target_name}"
    return target_name


def _target_feature_name(target_kind: str, target_name: str) -> str:
    if target_kind == "habit":
        return f"habit_{target_name}"
    if target_kind == "supplement":
        return f"supplement_{target_name}"
    return target_name


def _target_label(target_kind: str, target_name: str) -> str:
    return target_name.replace("_", " ")


def _snapshot_category(feature_name: str) -> str:
    name = feature_name
    is_habit = False
    if name.startswith("supplement_"):
        return "supplement"
    if name.startswith("habit_"):
        is_habit = True
        name = name[6:]

    if name.startswith(("sleep_", "deep_sleep", "rem_sleep")):
        return "sleep"
    if name.startswith("hrv_"):
        return "hrv"
    if name.startswith("spo2_"):
        return "spo2"
    if name.startswith(("hr_", "resting_hr")):
        return "heart_rate"
    if name.startswith("bb_"):
        return "body_battery"
    if name.startswith(("stress_", "high_stress")):
        return "stress"
    if name.startswith(("steps_", "walk_", "training_", "active_", "had_training")):
        return "activity"
    if any(token in name for token in ("daylight", "sunrise", "sunset", "solar_noon")):
        return "light"
    if "pollen" in name:
        return "pollen"
    if any(token in name for token in (
        "temperature",
        "humidity",
        "dew_point",
        "precipitation",
        "rain",
        "wind_speed",
        "cloud_cover",
    )):
        return "weather"
    if is_habit:
        return "habit"
    return "metric"


def _snapshot_tokens(feature_name: str) -> set[str]:
    name = feature_name.replace("habit_", "", 1).replace("supplement_", "", 1)
    return {token for token in name.split("_") if token not in {"avg", "max", "min", "pct", "share"}}


def _is_symptom_like_habit(feature_name: str) -> bool:
    if not feature_name.startswith("habit_"):
        return False
    return bool(_snapshot_tokens(feature_name) & {
        "anxiety",
        "energy",
        "fatigue",
        "fog",
        "headache",
        "insomnia",
        "migraine",
        "mood",
        "nausea",
        "pain",
        "reflux",
        "sleep",
        "slump",
    })


def _is_snapshot_target_candidate(target_kind: str, target_name: str) -> bool:
    if target_kind in {"habit", "supplement"}:
        return True
    return target_name in {
        "sleep_hours",
        "sleep_efficiency",
        "sleep_score",
        "hrv_overnight_avg",
        "hrv_overnight_min",
        "bb_wakeup",
        "bb_daily_min",
        "stress_morning_avg",
        "stress_afternoon_avg",
        "stress_2pm_window",
        "stress_peak",
        "high_stress_minutes",
    }


def _is_obvious_snapshot_pair(target_feature: str, metric: str) -> bool:
    target_category = _snapshot_category(target_feature)
    metric_category = _snapshot_category(metric)
    derived_metric_categories = {
        "activity",
        "body_battery",
        "heart_rate",
        "hrv",
        "light",
        "pollen",
        "weather",
        "sleep",
        "spo2",
        "stress",
    }
    if target_category == metric_category and target_category in derived_metric_categories:
        return True

    target_tokens = _snapshot_tokens(target_feature)
    metric_tokens = _snapshot_tokens(metric)
    if target_tokens & metric_tokens & {"steps", "walk", "walking", "peak", "daylight", "sunrise", "sunset", "pollen", "temperature", "humidity", "rain"}:
        return True

    if {target_category, metric_category} == {"heart_rate", "stress"}:
        return True

    categories = {target_category, metric_category}
    if "body_battery" in categories and categories & {"heart_rate", "hrv", "sleep", "stress"}:
        return True

    if {target_category, metric_category} == {"habit", "light"}:
        habit_feature = target_feature if target_category == "habit" else metric
        if not _is_symptom_like_habit(habit_feature):
            return True

    return False


def _feature_label(feature_name: str) -> str:
    name = feature_name
    if name.startswith("habit_"):
        name = name[6:]
    if name.endswith("_prev_day"):
        name = name[:-9]
    if name.startswith("supplement_slot_"):
        return f"{name[16:].replace('_', ' ')} supplements"
    if name.startswith("supplement_"):
        name = name[11:]
    return name.replace("_", " ")


def _signal_confidence(coefficient: float, n: int) -> str:
    abs_r = abs(coefficient)
    if n >= 30 and abs_r >= 0.5:
        return "high"
    if n >= 14 and abs_r >= 0.65:
        return "high"
    if n >= 14 and abs_r >= 0.4:
        return "medium"
    return "low"


def _feature_value(features: dict, key: str) -> float | None:
    if key.startswith("habit_"):
        return _get_habit_value(features, key[6:])
    if key.startswith("supplement_slot_"):
        slot = key[16:]
        values = [
            1.0 if row.get("completed") else 0.0
            for row in features.get("supplements", [])
            if row.get("slot") == slot
        ]
        return max(values) if values else None
    if key.startswith("supplement_"):
        return _get_supplement_value(features, key[11:])
    if key == "overall_pollen_avg":
        values = [
            _to_numeric(value)
            for name, value in features.items()
            if name.endswith("_pollen_avg")
        ]
        values = [value for value in values if value is not None]
        return float(sum(values)) if values else None
    return _to_numeric(features.get(key))


def _is_baseline_day(features: dict) -> bool:
    """Return False for days explicitly marked as non-baseline context."""
    return not bool(features.get("baseline_excluded"))


def _available_signal_keys(features_list: list[dict]) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {
        "habits": set(),
        "supplement_slots": set(),
        "supplements": set(),
        "pollen": set(),
        "weather": set(),
    }
    for features in features_list:
        for habit in features.get("habits", []):
            if _to_numeric(habit.get("value")) is not None:
                keys["habits"].add(f"habit_{habit['name']}")
        for row in features.get("supplements", []):
            if row.get("slot"):
                keys["supplement_slots"].add(f"supplement_slot_{row['slot']}")
        for item in features.get("supplement_items", []):
            if _to_numeric(item.get("value")) is not None:
                keys["supplements"].add(f"supplement_{item['key']}")
        for key, value in features.items():
            if _to_numeric(value) is None:
                continue
            if key.endswith("_pollen_avg"):
                keys["pollen"].add(key)
            if _snapshot_category(key) == "weather":
                keys["weather"].add(key)
    if keys["pollen"]:
        keys["pollen"].add("overall_pollen_avg")
    return keys


def _signal_summary(bucket: str, target: str, predictor: str, coefficient: float) -> str:
    target_label = _feature_label(target)
    predictor_label = _feature_label(predictor)
    higher_lower = "higher" if coefficient > 0 else "lower"
    more_less = "more" if coefficient > 0 else "less"

    if bucket == "prior_day_habit_sleep":
        return f"Your {target_label} is {higher_lower} after you log {predictor_label} the day before"
    if bucket == "habit_stress":
        return f"Your {target_label} is {higher_lower} when you log {predictor_label} more"
    if bucket == "pollen_habit":
        return f"You log {target_label} {more_less} when {predictor_label} is higher"
    if bucket == "supplement_sleep":
        return f"Your {target_label} is {higher_lower} when {predictor_label} are logged"
    if bucket == "prior_day_habit_body_battery":
        return f"Your {target_label} is {higher_lower} after you log {predictor_label} the day before"
    if bucket == "pollen_sleep":
        return f"Your {target_label} is {higher_lower} when {predictor_label} is higher"
    if bucket == "weather_sleep":
        return f"Your {target_label} is {higher_lower} when {predictor_label} is higher"
    if bucket == "sunrise_wake":
        return f"Your wake time tracks {predictor_label}"
    return f"{target_label} is {higher_lower} when {predictor_label} is higher"


def _correlate_signal(
    features_list: list[dict],
    bucket: str,
    target: str,
    predictor: str,
    lag_days: int,
    min_days: int,
    min_abs: float,
) -> dict | None:
    pairs = []
    for idx, features in enumerate(features_list):
        source_idx = idx - lag_days
        if source_idx < 0:
            continue
        target_value = _feature_value(features, target)
        predictor_value = _feature_value(features_list[source_idx], predictor)
        if target_value is not None and predictor_value is not None:
            pairs.append((target_value, predictor_value))

    if len(pairs) < min_days:
        return None

    target_vals, predictor_vals = zip(*pairs)
    if np.std(target_vals) == 0 or np.std(predictor_vals) == 0:
        return None

    try:
        r, p_value = stats.pearsonr(target_vals, predictor_vals)
    except Exception as e:
        logger.warning(f"Bucketed correlation failed for {target} vs {predictor}: {e}")
        return None

    if abs(r) < min_abs:
        return None

    abs_r = abs(r)
    strength = "strong" if abs_r > 0.5 else "moderate" if abs_r > 0.3 else "weak"
    metric = f"{predictor}_prev_day" if lag_days else predictor
    target_kind = "habit" if target.startswith("habit_") else "metric"
    return {
        "metric": metric,
        "coefficient": float(r),
        "p_value": float(p_value),
        "n": len(pairs),
        "strength": strength,
        "target": f"habit:{target[6:]}" if target_kind == "habit" else target,
        "target_label": _feature_label(target),
        "target_kind": target_kind,
        "target_feature": target,
        "bucket": bucket,
        "confidence": _signal_confidence(float(r), len(pairs)),
        "summary": _signal_summary(bucket, target, metric, float(r)),
    }


def _compute_bucketed_correlation_signals(
    features_list: list[dict],
    min_days: int = 14,
    min_abs: float = 0.3,
    limit: int = 5,
) -> list[dict]:
    """Compute curated overview signals from common interesting health buckets."""
    features_list = sorted(features_list, key=lambda row: row.get("date"))
    keys = _available_signal_keys(features_list)
    candidates: list[tuple[str, str, str, int]] = []

    sleep_targets = ["sleep_score", "deep_sleep_pct"]
    stress_targets = ["stress_2pm_window", "stress_afternoon_avg", "high_stress_minutes"]
    body_battery_targets = ["bb_wakeup", "bb_morning_drain_rate"]

    for habit in sorted(keys["habits"]):
        for target in sleep_targets:
            candidates.append(("prior_day_habit_sleep", target, habit, 1))
        for target in stress_targets:
            candidates.append(("habit_stress", target, habit, 0))
        for target in body_battery_targets:
            candidates.append(("prior_day_habit_body_battery", target, habit, 1))
        for pollen in sorted(keys["pollen"]):
            candidates.append(("pollen_habit", habit, pollen, 0))

    for supplement in sorted(keys["supplement_slots"] | keys["supplements"]):
        for target in sleep_targets:
            candidates.append(("supplement_sleep", target, supplement, 0))

    for pollen in sorted(keys["pollen"]):
        for target in sleep_targets:
            candidates.append(("pollen_sleep", target, pollen, 0))

    for weather in sorted(keys["weather"]):
        for target in sleep_targets:
            candidates.append(("weather_sleep", target, weather, 0))

    signals = []
    for bucket, target, predictor, lag_days in candidates:
        signal = _correlate_signal(features_list, bucket, target, predictor, lag_days, min_days, min_abs)
        if signal is not None:
            signals.append(signal)

    bucket_priority = {
        "prior_day_habit_sleep": 7,
        "supplement_sleep": 7,
        "prior_day_habit_body_battery": 6,
        "pollen_sleep": 6,
        "weather_sleep": 6,
        "habit_stress": 5,
        "pollen_habit": 5,
    }
    signals.sort(
        key=lambda row: (
            bucket_priority.get(row["bucket"], 0),
            row["confidence"] == "high",
            abs(row["coefficient"]),
            row["n"],
        ),
        reverse=True,
    )

    selected = []
    used_buckets = set()
    used_predictors = set()

    def predictor_key(signal: dict) -> str:
        return signal["metric"].removesuffix("_prev_day")

    for signal in signals:
        if signal["bucket"] in used_buckets:
            continue
        if predictor_key(signal) in used_predictors:
            continue
        selected.append(signal)
        used_buckets.add(signal["bucket"])
        used_predictors.add(predictor_key(signal))
        if len(selected) >= limit:
            return selected

    for signal in signals:
        if signal in selected:
            continue
        if predictor_key(signal) in used_predictors:
            continue
        selected.append(signal)
        used_predictors.add(predictor_key(signal))
        if len(selected) >= limit:
            return selected

    return selected


async def _load_bucketed_signal_features(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    timezone: str,
) -> list[dict]:
    """Load only fields needed for overview signal buckets using bulk queries."""
    tz = ZoneInfo(timezone)
    features_by_date = {
        (start_date + timedelta(days=offset)): {"date": (start_date + timedelta(days=offset)).isoformat()}
        for offset in range((end_date - start_date).days + 1)
    }

    excluded_context_rows = (await session.execute(
        select(ContextEvent)
        .where(ContextEvent.exclude_from_baseline.is_(True))
        .where(ContextEvent.start_date <= end_date)
        .where(ContextEvent.end_date >= start_date)
    )).scalars().all()
    excluded_dates: set[date] = set()
    for row in excluded_context_rows:
        current = max(row.start_date, start_date)
        last = min(row.end_date, end_date)
        while current <= last:
            excluded_dates.add(current)
            current += timedelta(days=1)

    sleep_rows = (await session.execute(
        select(SleepSession).where(SleepSession.date >= start_date, SleepSession.date <= end_date)
    )).scalars().all()
    sleep_by_date = {row.date: row for row in sleep_rows}
    for row in sleep_rows:
        features = features_by_date.get(row.date)
        if features is None:
            continue
        if row.sleep_score is not None:
            features["sleep_score"] = row.sleep_score
        if row.total_sleep_seconds and row.deep_sleep_seconds is not None:
            features["deep_sleep_pct"] = (row.deep_sleep_seconds / row.total_sleep_seconds) * 100

    habit_rows = (await session.execute(
        select(DailyHabit, Habit)
        .join(Habit, Habit.id == DailyHabit.habit_id)
        .where(DailyHabit.date >= start_date, DailyHabit.date <= end_date)
    )).all()
    for daily, habit in habit_rows:
        features_by_date.setdefault(daily.date, {"date": daily.date.isoformat()}).setdefault("habits", []).append({
            "name": habit.name,
            "value": daily.habit_value,
            "type": habit.habit_type,
        })

    supplement_rows = (await session.execute(
        select(SupplementLog)
        .where(SupplementLog.date >= start_date, SupplementLog.date <= end_date)
        .order_by(SupplementLog.slot)
    )).scalars().all()
    for row in supplement_rows:
        features = features_by_date.setdefault(row.date, {"date": row.date.isoformat()})
        features.setdefault("supplements", []).append({
            "slot": row.slot,
            "completed": row.completed,
            "snapshot": row.snapshot,
        })
        items_by_key = {item["key"]: item for item in features.setdefault("supplement_items", [])}
        for item in row.snapshot or []:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            key = supplement_feature_name(name)[11:]
            existing = items_by_key.get(key)
            value = 1.0 if row.completed else 0.0
            if existing is None:
                entry = {"key": key, "name": name, "value": value}
                features["supplement_items"].append(entry)
                items_by_key[key] = entry
            else:
                existing["value"] = max(existing["value"], value)

    environmental_rows = (await session.execute(
        select(EnvironmentalMetric)
        .where(EnvironmentalMetric.date >= start_date, EnvironmentalMetric.date <= end_date)
    )).scalars().all()
    for row in environmental_rows:
        key = row.metric_key
        if key.endswith("_pollen_avg") or row.category == "Weather":
            features_by_date.setdefault(row.date, {"date": row.date.isoformat()})[key] = row.value

    start_dt = _day_boundary(start_date, tz)
    end_dt = _day_boundary(end_date + timedelta(days=1), tz)
    stress_rows = (await session.execute(
        select(StressSample)
        .where(StressSample.timestamp >= start_dt, StressSample.timestamp < end_dt)
        .order_by(StressSample.timestamp)
    )).scalars().all()
    stress_by_date: dict[date, list[StressSample]] = {}
    for sample in stress_rows:
        local_dt = sample.timestamp.replace(tzinfo=dt_timezone.utc).astimezone(tz)
        if sample.stress_level > 0:
            stress_by_date.setdefault(local_dt.date(), []).append(sample)
    for sample_date, samples in stress_by_date.items():
        features = features_by_date.get(sample_date)
        if features is None:
            continue
        afternoon = []
        window_2pm = []
        high_stress = 0
        for sample in samples:
            local_dt = sample.timestamp.replace(tzinfo=dt_timezone.utc).astimezone(tz)
            if 12 <= local_dt.hour < 18:
                afternoon.append(sample.stress_level)
            if 13 <= local_dt.hour < 16:
                window_2pm.append(sample.stress_level)
            if sample.stress_level > 60:
                high_stress += 1
        if afternoon:
            features["stress_afternoon_avg"] = float(np.mean(afternoon))
        if window_2pm:
            features["stress_2pm_window"] = float(np.mean(window_2pm))
        features["high_stress_minutes"] = high_stress * 15

    bb_rows = (await session.execute(
        select(BodyBatterySample)
        .where(BodyBatterySample.timestamp >= start_dt, BodyBatterySample.timestamp < end_dt)
        .order_by(BodyBatterySample.timestamp)
    )).scalars().all()
    bb_by_date: dict[date, list[BodyBatterySample]] = {}
    for sample in bb_rows:
        local_dt = sample.timestamp.replace(tzinfo=dt_timezone.utc).astimezone(tz)
        if not (local_dt.hour == 0 and local_dt.minute == 0):
            bb_by_date.setdefault(local_dt.date(), []).append(sample)
    for sample_date, samples in bb_by_date.items():
        features = features_by_date.get(sample_date)
        if features is None:
            continue
        sleep = sleep_by_date.get(sample_date)
        if sleep and sleep.sleep_end:
            closest = min(samples, key=lambda sample: abs(sample.timestamp - sleep.sleep_end), default=None)
            if closest is not None and abs(closest.timestamp - sleep.sleep_end) <= timedelta(minutes=30):
                features["bb_wakeup"] = closest.body_battery
        noon = _day_boundary(sample_date, tz) + timedelta(hours=12)
        morning = [sample for sample in samples if sample.timestamp < noon]
        if len(morning) >= 2:
            first = morning[0]
            last = morning[-1]
            hours = (last.timestamp - first.timestamp).total_seconds() / 3600
            if hours > 0:
                features["bb_morning_drain_rate"] = (last.body_battery - first.body_battery) / hours

    return [features_by_date[key] for key in sorted(features_by_date) if key not in excluded_dates]


async def _load_habit_thresholds(session: AsyncSession) -> dict[str, Habit]:
    """Return counter habits with configured threshold values, keyed by name."""
    rows = (await session.execute(
        select(Habit)
        .where(Habit.habit_type == "counter")
        .where(Habit.target_value.is_not(None))
    )).scalars().all()
    return {habit.name: habit for habit in rows}


def _threshold_summary(
    target_vals: tuple[float, ...],
    feat_vals: tuple[float, ...],
    habit: Habit,
) -> dict | None:
    """Summarize a binary target split by a configured counter-habit threshold."""
    threshold = habit.target_value
    if threshold is None:
        return None

    operator = ">" if habit.is_negative else ">="
    if habit.is_negative:
        above = [(t, f) for t, f in zip(target_vals, feat_vals) if f > threshold]
        below = [(t, f) for t, f in zip(target_vals, feat_vals) if f <= threshold]
    else:
        above = [(t, f) for t, f in zip(target_vals, feat_vals) if f >= threshold]
        below = [(t, f) for t, f in zip(target_vals, feat_vals) if f < threshold]

    if not above or not below:
        return None

    above_rate = sum(1 for t, _ in above if t == 1.0) / len(above)
    below_rate = sum(1 for t, _ in below if t == 1.0) / len(below)
    relative_risk = above_rate / below_rate if below_rate > 0 else None

    return {
        "threshold_value": int(threshold),
        "threshold_operator": operator,
        "above_threshold_n": len(above),
        "below_threshold_n": len(below),
        "above_threshold_target_rate": float(above_rate),
        "below_threshold_target_rate": float(below_rate),
        "relative_risk": float(relative_risk) if relative_risk is not None else None,
    }


async def compute_correlations(
    session: AsyncSession,
    timezone: str = "Europe/London",
    target: str | None = None,
    target_habit: str | None = None,
    min_days: int = 5,
    features_list: list[dict] | None = None,
    habit_thresholds: dict[str, Habit] | None = None,
    diagnostics: dict | None = None,
) -> list[dict]:
    """
    Compute correlations between all features and a target habit.

    Args:
        session: Database session
        timezone: Timezone string
        target: Generic target selector. Use "habit:<name>" for habits or a
            top-level DailySummary metric key (for example "steps_total").
        target_habit: Legacy habit target parameter (backwards compatible)
        min_days: Minimum number of days required for analysis

    Returns:
        List of correlation results, sorted by |r| descending.
    """
    if not target and not target_habit:
        target_habit = await get_default_habit_name(session)
        if not target_habit:
            return []

    target_kind, target_name = _parse_correlation_target(target, target_habit)

    # Get all available data
    end_date = date.today()
    start_date = end_date - timedelta(days=365)  # Look back 1 year max

    if features_list is None:
        features_list = await compute_features_range(session, start_date, end_date, timezone)
    features_list = [features for features in features_list if _is_baseline_day(features)]

    # Filter to days with target habit data
    target_data = [
        (f, _get_target_value(f, target_kind, target_name))
        for f in features_list
    ]
    target_data = [(f, v) for f, v in target_data if v is not None]

    if diagnostics is not None:
        diagnostics["target_n"] = len(target_data)

    if len(target_data) < min_days:
        if diagnostics is not None:
            diagnostics["empty_reason"] = "insufficient_target_data"
        logger.warning(f"Insufficient data: {len(target_data)} days (need {min_days})")
        return []

    # Extract target habit values
    target_features = [f for f, _ in target_data]
    target_values = [v for _, v in target_data]
    target_is_binary = all(v in (0.0, 1.0) for v in target_values)
    if np.std(target_values) == 0:
        if diagnostics is not None:
            diagnostics["empty_reason"] = "constant_target"
        logger.warning(f"Constant target data for {_target_selector(target_kind, target_name)}: {len(target_data)} days")
        return []
    if habit_thresholds is None:
        habit_thresholds = await _load_habit_thresholds(session)

    # Separate positive and negative days for mean comparisons
    if target_is_binary:
        positive_days = [f for f, v in target_data if v == 1.0]
        negative_days = [f for f, v in target_data if v == 0.0]
        positive_label = "Positive target"
        negative_label = "Negative target"
    else:
        split = float(np.median(target_values))
        positive_days = [f for f, v in target_data if v >= split]
        negative_days = [f for f, v in target_data if v < split]
        positive_label = "Higher target"
        negative_label = "Lower target"

    results = []

    # Get all numeric features (excluding date and habits list)
    # Collect feature names from ALL days to handle sparse data
    all_feature_names = set()
    all_habit_names = set()
    all_supplement_names = set()
    for f in target_features:
        for k in f.keys():
            if k not in [
                "date",
                "habits",
                "supplements",
                "supplement_items",
                "contexts",
                "baseline_excluded",
                "context_categories",
            ]:
                all_feature_names.add(k)
        for h in f.get("habits", []):
            if not (target_kind == "habit" and h["name"] == target_name):
                all_habit_names.add(f"habit_{h['name']}")
        for item in f.get("supplement_items", []):
            if not (target_kind == "supplement" and item["key"] == target_name):
                all_supplement_names.add(supplement_feature_name(item["name"]))

    feature_names = list(all_feature_names) + list(all_habit_names) + list(all_supplement_names)

    for feature_name in feature_names:
        # Skip self-correlation against the selected target.
        if target_kind == "metric" and feature_name == target_name:
            continue
        if target_kind == "habit" and feature_name == f"habit_{target_name}":
            continue
        if target_kind == "supplement" and feature_name == f"supplement_{target_name}":
            continue

        # Extract feature values - check if it's a habit or regular feature
        if feature_name.startswith("habit_"):
            habit_name = feature_name[6:]  # Remove "habit_" prefix
            feature_values = [_get_habit_value(f, habit_name) for f in target_features]
        elif feature_name.startswith("supplement_"):
            supplement_name = feature_name[11:]
            feature_values = [_get_supplement_value(f, supplement_name) for f in target_features]
        else:
            feature_values = [_to_numeric(f.get(feature_name)) for f in target_features]

        # Filter out None values
        valid_pairs = [(t, f) for t, f in zip(target_values, feature_values) if t is not None and f is not None]

        if len(valid_pairs) < min_days:
            continue

        target_vals, feat_vals = zip(*valid_pairs)

        # Check for variance (can't correlate if all values are the same)
        if np.std(feat_vals) == 0 or np.std(target_vals) == 0:
            continue

        # Calculate Pearson correlation
        try:
            r, p_value = stats.pearsonr(target_vals, feat_vals)
        except Exception as e:
            logger.warning(f"Correlation failed for {feature_name}: {e}")
            continue

        # Calculate means for positive vs negative days
        if feature_name.startswith("habit_"):
            habit_name = feature_name[6:]
            pos_values = [_get_habit_value(f, habit_name) for f in positive_days]
            neg_values = [_get_habit_value(f, habit_name) for f in negative_days]
        elif feature_name.startswith("supplement_"):
            supplement_name = feature_name[11:]
            pos_values = [_get_supplement_value(f, supplement_name) for f in positive_days]
            neg_values = [_get_supplement_value(f, supplement_name) for f in negative_days]
        else:
            pos_values = [_to_numeric(f.get(feature_name)) for f in positive_days]
            neg_values = [_to_numeric(f.get(feature_name)) for f in negative_days]

        pos_values = [v for v in pos_values if v is not None]
        pos_avg = np.mean(pos_values) if pos_values else None

        neg_values = [v for v in neg_values if v is not None]
        neg_avg = np.mean(neg_values) if neg_values else None

        # Calculate difference percentage
        diff_pct = None
        if pos_avg is not None and neg_avg is not None and neg_avg != 0:
            diff_pct = ((pos_avg - neg_avg) / neg_avg) * 100

        # Classify strength
        abs_r = abs(r)
        if abs_r > 0.5:
            strength = "strong"
        elif abs_r > 0.3:
            strength = "moderate"
        else:
            strength = "weak"

        result = {
            "metric": feature_name,
            "coefficient": float(r),
            "p_value": float(p_value),
            "n": len(valid_pairs),
            "strength": strength,
            "fog_day_avg": float(pos_avg) if pos_avg is not None else None,
            "clear_day_avg": float(neg_avg) if neg_avg is not None else None,
            "difference_pct": float(diff_pct) if diff_pct is not None else None,
            "target_is_binary": target_is_binary,
            "positive_label": positive_label,
            "negative_label": negative_label,
        }

        if target_is_binary and feature_name.startswith("habit_"):
            threshold_habit = habit_thresholds.get(feature_name[6:])
            if threshold_habit is not None:
                summary = _threshold_summary(target_vals, feat_vals, threshold_habit)
                if summary:
                    result.update(summary)

        results.append(result)

    # Sort by absolute correlation coefficient
    results.sort(key=lambda x: abs(x["coefficient"]), reverse=True)

    if target_kind == "habit":
        target_label = f"habit:{target_name}"
    elif target_kind == "supplement":
        target_label = f"supplement:{target_name}"
    else:
        target_label = target_name
    logger.info(f"Computed correlations for {len(results)} features against {target_label}")
    if diagnostics is not None and not results:
        diagnostics["empty_reason"] = "no_correlatable_features"
    return results


async def compute_correlation_snapshot(
    session: AsyncSession,
    timezone: str = "Europe/London",
    min_days: int = 14,
    min_abs: float = 0.3,
    limit: int = 5,
) -> list[dict]:
    """Find curated overview correlations from common interesting signal buckets."""
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    features_list = await _load_bucketed_signal_features(session, start_date, end_date, timezone)
    return _compute_bucketed_correlation_signals(features_list, min_days=min_days, min_abs=min_abs, limit=limit)


async def compute_patterns(
    session: AsyncSession,
    timezone: str = "Europe/London",
    target_habit: str | None = None,
) -> list[dict]:
    """
    Detect specific patterns using conditional probabilities.

    Args:
        session: Database session
        timezone: Timezone string
        target_habit: The habit name to use as the outcome variable. If omitted,
            the first habit in settings order is used.

    Returns:
        List of pattern results with probabilities and relative risk.
    """
    if not target_habit:
        target_habit = await get_default_habit_name(session)
        if not target_habit:
            return []

    # Get all available data
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    features_list = await compute_features_range(session, start_date, end_date, timezone)

    # Filter to days with target habit data
    target_data = [
        f for f in features_list
        if _is_baseline_day(f) and _get_habit_value(f, target_habit) is not None
    ]

    if len(target_data) < 7:
        return []

    # Calculate baseline probability (target habit == 1)
    target_positive_count = sum(1 for f in target_data if _get_habit_value(f, target_habit) == 1.0)
    baseline_prob = target_positive_count / len(target_data)

    patterns = []

    def _add_pattern(subset: list[dict], description: str) -> None:
        if len(subset) < 5:
            return
        target_positive_in_subset = sum(1 for f in subset if _get_habit_value(f, target_habit) == 1.0)
        prob = target_positive_in_subset / len(subset)
        if abs(prob - baseline_prob) < 0.01:
            return
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0
        patterns.append({
            "description": description,
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(subset),
        })

    feature_pairs: dict[str, list[tuple[dict, float]]] = {}
    for day in target_data:
        for key, value in day.items():
            if key in {
                "date",
                "habits",
                "supplements",
                "supplement_items",
                "contexts",
                "baseline_excluded",
                "context_categories",
            }:
                continue
            numeric = _to_numeric(value)
            if numeric is None:
                continue
            feature_pairs.setdefault(key, []).append((day, numeric))

        for habit in day.get("habits", []):
            name = habit["name"]
            if name == target_habit:
                continue
            numeric = _to_numeric(habit.get("value"))
            if numeric is None:
                continue
            feature_pairs.setdefault(f"habit:{name}", []).append((day, numeric))

    for feature_key, pairs in feature_pairs.items():
        if len(pairs) < 7:
            continue

        values = [value for _, value in pairs]
        unique_values = set(values)
        if len(unique_values) < 2:
            continue

        label = feature_key[6:] if feature_key.startswith("habit:") else feature_key
        label = label.replace("_", " ")

        if unique_values.issubset({0.0, 1.0}):
            _add_pattern(
                [day for day, value in pairs if value == 1.0],
                f"{label} present",
            )
            continue

        q25 = float(np.quantile(values, 0.25))
        q75 = float(np.quantile(values, 0.75))
        min_value = min(values)
        max_value = max(values)

        if q75 > min_value:
            _add_pattern(
                [day for day, value in pairs if value >= q75],
                f"Higher {label} (>= {q75:.2f})",
            )

        if q25 < max_value:
            _add_pattern(
                [day for day, value in pairs if value <= q25],
                f"Lower {label} (<= {q25:.2f})",
            )

    # Sort by effect size (distance from neutral risk=1.0), then sample size.
    patterns.sort(
        key=lambda x: (abs(x["relative_risk"] - 1.0), x["sample_size"]),
        reverse=True,
    )

    logger.info(f"Identified {len(patterns)} patterns against {target_habit}")
    return patterns


async def generate_insights(
    session: AsyncSession,
    timezone: str = "Europe/London",
    target_habit: str | None = None,
) -> list[dict]:
    """
    Generate plain-English insights from correlations and patterns.

    Args:
        session: Database session
        timezone: Timezone string
        target_habit: The habit name to analyze as the outcome variable. If
            omitted, the first habit in settings order is used.

    Returns:
        List of insights with confidence ratings.
    """
    if not target_habit:
        target_habit = await get_default_habit_name(session)
        if not target_habit:
            return []

    correlations = await compute_correlations(session, timezone, target_habit=target_habit)
    patterns = await compute_patterns(session, timezone, target_habit=target_habit)

    habit_label = target_habit.replace("_", " ")
    insights = []

    # Insights from patterns (high confidence if relative risk is significant)
    for pattern in patterns:
        if pattern["sample_size"] < 5:
            continue

        rel_risk = pattern["relative_risk"]
        prob = pattern["probability"]
        baseline = pattern["baseline_probability"]

        if rel_risk > 1.5 and prob > 0.5:
            text = (
                f"You're {rel_risk:.1f}x more likely to have {habit_label} "
                f"when {pattern['description'].lower()}. "
                f"({prob*100:.0f}% vs {baseline*100:.0f}% baseline)"
            )
            confidence = "high" if pattern["sample_size"] >= 10 else "medium"

            insights.append({
                "text": text,
                "confidence": confidence,
                "supporting_metric": pattern["description"],
                "effect_size": rel_risk,
            })

        elif rel_risk < 0.7 and prob < baseline:
            text = (
                f"Days with {pattern['description'].lower()} show "
                f"{(1-rel_risk)*100:.0f}% less {habit_label}. "
                f"({prob*100:.0f}% vs {baseline*100:.0f}% baseline)"
            )
            confidence = "high" if pattern["sample_size"] >= 10 else "medium"

            insights.append({
                "text": text,
                "confidence": confidence,
                "supporting_metric": pattern["description"],
                "effect_size": 1 - rel_risk,
            })

    # Insights from top correlations
    for corr in correlations[:3]:  # Top 3
        if abs(corr["coefficient"]) < 0.3:
            continue

        metric_name = corr["metric"].replace("_", " ")

        text = (
            f"{metric_name.capitalize()} is associated with "
            f"{'more' if corr['coefficient'] > 0 else 'fewer'} {habit_label} days "
            f"(r={corr['coefficient']:.2f})"
        )

        confidence = "medium" if corr["n"] >= 14 else "low"

        insights.append({
            "text": text,
            "confidence": confidence,
            "supporting_metric": corr["metric"],
            "effect_size": abs(corr["coefficient"]),
        })

    # Sort by confidence and effect size
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    insights.sort(
        key=lambda x: (confidence_order[x["confidence"]], x.get("effect_size", 0)),
        reverse=True
    )

    logger.info(f"Generated {len(insights)} insights")
    return insights
