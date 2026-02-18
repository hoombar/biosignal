"""Pydantic response models for API endpoints."""

from datetime import datetime, date
from pydantic import BaseModel
from typing import Any


class TimeSeriesPoint(BaseModel):
    """Single time-series data point."""
    timestamp: datetime
    value: float


class TimeSeriesResponse(BaseModel):
    """Time-series data response."""
    date: str
    type: str
    points: list[TimeSeriesPoint]


class SleepResponse(BaseModel):
    """Sleep session response."""
    date: date
    sleep_start: datetime | None
    sleep_end: datetime | None
    total_sleep_seconds: int | None
    deep_sleep_seconds: int | None
    light_sleep_seconds: int | None
    rem_sleep_seconds: int | None
    awake_seconds: int | None
    sleep_score: int | None
    avg_overnight_hrv: float | None
    avg_overnight_spo2: float | None
    avg_overnight_rr: float | None

    class Config:
        from_attributes = True


class ActivityResponse(BaseModel):
    """Activity response."""
    garmin_activity_id: str
    activity_type: str
    start_time: datetime
    end_time: datetime
    duration_seconds: int | None
    avg_hr: int | None
    max_hr: int | None
    min_hr: int | None
    calories: int | None
    avg_stress: int | None
    training_effect_aerobic: float | None
    training_effect_anaerobic: float | None

    class Config:
        from_attributes = True


class BodyBatterySample(BaseModel):
    """Single body battery reading with time."""
    time: str  # Human-readable time like "7:39 AM"
    value: int


class Habit(BaseModel):
    """Single habit entry."""
    name: str
    value: int
    type: str


class HabitResponse(BaseModel):
    """Daily habits response."""
    date: str
    habits: dict[str, Any]


class DailySummary(BaseModel):
    """Computed daily summary with all features."""
    date: str
    # Sleep features
    sleep_hours: float | None = None
    deep_sleep_pct: float | None = None
    rem_sleep_pct: float | None = None
    sleep_efficiency: float | None = None
    sleep_score: int | None = None
    # HRV features
    hrv_overnight_avg: float | None = None
    hrv_overnight_min: float | None = None
    hrv_rmssd_slope: float | None = None
    # SpO2 features
    spo2_overnight_avg: float | None = None
    spo2_overnight_min: int | None = None
    spo2_overnight_max: int | None = None
    spo2_dips_below_94: int | None = None
    # Heart rate features
    resting_hr: int | None = None
    hr_morning_avg: float | None = None
    hr_afternoon_avg: float | None = None
    hr_2pm_window: float | None = None
    hr_max_24h: int | None = None
    hr_recovery_slope: float | None = None
    # Body battery features
    bb_wakeup: int | None = None
    bb_samples: list[BodyBatterySample] = []  # All available samples with times
    bb_morning_drain_rate: float | None = None
    bb_afternoon_drain_rate: float | None = None
    bb_daily_min: int | None = None
    # Stress features
    stress_morning_avg: float | None = None
    stress_afternoon_avg: float | None = None
    stress_2pm_window: float | None = None
    stress_peak: int | None = None
    high_stress_minutes: int | None = None
    # Activity features
    steps_total: int | None = None
    steps_morning: int | None = None
    active_minutes: int | None = None
    had_training: bool | None = None
    training_type: str | None = None
    training_duration_min: float | None = None
    training_avg_hr: int | None = None
    training_intensity: str | None = None
    hours_since_training: float | None = None
    # Habit features (dynamic list)
    habits: list[Habit] = []


class CalendarDaySummary(BaseModel):
    """Lightweight day summary for year heatmap."""
    date: str
    sleep_score: int | None = None
    has_slump: bool = False


class NotableDay(BaseModel):
    """A notable day within a month (extreme or anomaly)."""
    date: str
    description: str
    metric: str
    value: float | None = None


class CorrelationResult(BaseModel):
    """Correlation analysis result."""
    metric: str
    coefficient: float
    p_value: float
    n: int
    strength: str
    fog_day_avg: float | None = None
    clear_day_avg: float | None = None
    difference_pct: float | None = None


class PatternResult(BaseModel):
    """Pattern detection result."""
    description: str
    probability: float
    baseline_probability: float
    relative_risk: float
    sample_size: int


class InsightResult(BaseModel):
    """Generated insight."""
    text: str
    confidence: str
    supporting_metric: str | None = None
    effect_size: float | None = None
