"""Pydantic response models for API endpoints."""

from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Any, Literal


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


class SupplementDailyEntry(BaseModel):
    """Single supplement group entry for a day."""
    slot: str
    completed: bool
    snapshot: list[dict[str, Any]] = []


class SupplementItemEntry(BaseModel):
    """Flattened supplement item signal for trends and analysis."""
    key: str
    name: str
    value: int


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
    steps_peak_hour: int | None = None
    steps_active_hours: int | None = None
    steps_walking_hours: int | None = None
    steps_peak_hour_share: float | None = None
    steps_peak_30min: int | None = None
    steps_walking_30min_blocks: int | None = None
    steps_peak_30min_share: float | None = None
    walk_peak_30min_avg_hr: float | None = None
    walk_peak_30min_hr_delta: float | None = None
    walk_hr_elevated_30min_blocks: int | None = None
    steps_peak_45min: int | None = None
    steps_walking_45min_windows: int | None = None
    steps_peak_45min_share: float | None = None
    walk_peak_45min_avg_hr: float | None = None
    walk_peak_45min_hr_delta: float | None = None
    walk_hr_elevated_45min_windows: int | None = None
    had_likely_walk: bool | None = None
    had_likely_brisk_walk: bool | None = None
    active_minutes: int | None = None
    had_training: bool | None = None
    training_type: str | None = None
    training_duration_min: float | None = None
    training_avg_hr: int | None = None
    training_intensity: str | None = None
    hours_since_training: float | None = None
    # Environmental features
    daylight_minutes: float | None = None
    sunrise_minutes_after_midnight: float | None = None
    sunset_minutes_after_midnight: float | None = None
    solar_noon_minutes_after_midnight: float | None = None
    alder_pollen_avg: float | None = None
    alder_pollen_max: float | None = None
    birch_pollen_avg: float | None = None
    birch_pollen_max: float | None = None
    grass_pollen_avg: float | None = None
    grass_pollen_max: float | None = None
    mugwort_pollen_avg: float | None = None
    mugwort_pollen_max: float | None = None
    olive_pollen_avg: float | None = None
    olive_pollen_max: float | None = None
    ragweed_pollen_avg: float | None = None
    ragweed_pollen_max: float | None = None
    # Habit features (dynamic list)
    habits: list[Habit] = []
    supplements: list[SupplementDailyEntry] = []
    supplement_items: list[SupplementItemEntry] = []


class CalendarDaySummary(BaseModel):
    """Lightweight day summary for year heatmap."""
    date: str
    sleep_score: int | None = None
    has_habit_event: bool = False


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
    target_is_binary: bool | None = None
    positive_label: str | None = None
    negative_label: str | None = None
    threshold_value: int | None = None
    threshold_operator: str | None = None
    above_threshold_n: int | None = None
    below_threshold_n: int | None = None
    above_threshold_target_rate: float | None = None
    below_threshold_target_rate: float | None = None
    relative_risk: float | None = None


class CorrelationTargetOption(BaseModel):
    """Selectable target option for correlation analysis."""
    target: str
    label: str
    kind: str
    category: str


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


class HabitDisplayConfigResponse(BaseModel):
    """Habit display config response — one entry per known habit."""
    habit_name: str
    display_name: str | None = None
    emoji: str | None = None
    color: str | None = None
    sort_order: int = 0

    class Config:
        from_attributes = True


class HabitDisplayConfigUpdate(BaseModel):
    """Request body for updating a habit's display config."""
    display_name: str | None = None
    emoji: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None


class HabitListEntry(BaseModel):
    """One row returned by GET /api/habits/list."""
    id: int
    name: str
    habit_type: str
    archived: bool
    is_negative: bool = False
    target_value: int | None = None
    period: str = "day"
    display_name: str | None = None
    emoji: str | None = None
    color: str | None = None
    sort_order: int = 0
    streak: int = 0
    completion_hit: int = 0
    completion_total: int = 0


class HabitExportLog(BaseModel):
    """One exported habit log entry."""
    date: date
    value: int = Field(..., ge=0)


class HabitExportDisplay(BaseModel):
    """Optional exported display config for a habit."""
    display_name: str | None = None
    emoji: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = 0


class HabitExportEntry(BaseModel):
    """One exported habit with its nested display and log data."""
    uuid: UUID | None = None
    name: str = Field(..., min_length=1, max_length=64)
    habit_type: str = Field(..., pattern=r"^(binary|counter)$")
    is_negative: bool = False
    target_value: int | None = Field(default=None, ge=0)
    period: str = Field(default="day", pattern=r"^(day|week|month)$")
    archived_at: datetime | None = None
    created_at: datetime
    display: HabitExportDisplay | None = None
    logs: list[HabitExportLog] = []


class HabitExportBundle(BaseModel):
    """Versioned import/export bundle for canonical habit state."""
    version: Literal[1]
    exported_at: datetime
    habits: list[HabitExportEntry] = []


class HabitLogUpdate(BaseModel):
    """Request body for PUT /api/habits/log/{date}/{habit_id}."""
    value: int = Field(..., ge=0)


class HabitLogEntry(BaseModel):
    """One logged habit value for a date."""
    date: str
    habit_id: int
    value: int


class HabitCreateRequest(BaseModel):
    """Request body for POST /api/habits."""
    name: str = Field(..., min_length=1, max_length=64)
    habit_type: str = Field(..., pattern=r"^(binary|counter)$")
    is_negative: bool = False
    target_value: int | None = Field(default=None, ge=0)
    period: str = Field(default="day", pattern=r"^(day|week|month)$")
    display_name: str | None = None
    emoji: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None


class HabitUpdateRequest(BaseModel):
    """Request body for PATCH /api/habits/{id}.

    Habit type and the internal slug are immutable. Everything else
    (target/period/polarity, plus display attrs) can change.
    """
    is_negative: bool | None = None
    target_value: int | None = Field(default=None, ge=0)
    period: str | None = Field(default=None, pattern=r"^(day|week|month)$")
    display_name: str | None = None
    emoji: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None
    # Sentinel allowing target_value to be cleared explicitly. Pydantic can't
    # distinguish "field omitted" from "field set to None" in a JSON body
    # without help; clients send ``clear_target=true`` to erase a stored target.
    clear_target: bool = False
