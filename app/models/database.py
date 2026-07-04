from datetime import datetime, date
from uuid import uuid4
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Index,
    UniqueConstraint,
    text,
)
from app.core.database import Base


class RawGarminResponse(Base):
    """Raw Garmin API responses for reprocessing."""

    __tablename__ = "raw_garmin_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    endpoint = Column(String, nullable=False)
    response = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("date", "endpoint", name="uix_garmin_date_endpoint"),)


class EnvironmentalMetric(Base):
    """Normalized daily metrics from environmental sources."""

    __tablename__ = "environmental_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    metric_key = Column(String, nullable=False, index=True)
    location_key = Column(String, nullable=False, index=True)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    category = Column(String, nullable=False)
    raw_metadata = Column(JSON, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "date",
            "source",
            "metric_key",
            "location_key",
            name="uix_environmental_date_source_metric_location",
        ),
        Index("ix_environmental_metrics_date_metric", "date", "metric_key"),
    )


class HeartRateSample(Base):
    """Heart rate samples at ~15 minute intervals."""

    __tablename__ = "heart_rate_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    heart_rate = Column(Integer, nullable=False)


class BodyBatterySample(Base):
    """Body Battery samples at ~15 minute intervals."""

    __tablename__ = "body_battery_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    body_battery = Column(Integer, nullable=False)


class StressSample(Base):
    """Stress level samples at ~15 minute intervals."""

    __tablename__ = "stress_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    stress_level = Column(Integer, nullable=False)  # -1 or -2 for rest/unmeasured


class HrvSample(Base):
    """HRV readings (typically overnight)."""

    __tablename__ = "hrv_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    hrv_value = Column(Float, nullable=False)
    reading_type = Column(String, nullable=True)


class Spo2Sample(Base):
    """SpO2 readings (typically overnight)."""

    __tablename__ = "spo2_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    spo2_value = Column(Integer, nullable=False)


class StepsSample(Base):
    """Steps per interval."""

    __tablename__ = "steps_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    steps = Column(Integer, nullable=False)
    duration_seconds = Column(Integer, nullable=True)


class SleepSession(Base):
    """Sleep data (one record per night)."""

    __tablename__ = "sleep_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    sleep_start = Column(DateTime, nullable=True)
    sleep_end = Column(DateTime, nullable=True)
    total_sleep_seconds = Column(Integer, nullable=True)
    deep_sleep_seconds = Column(Integer, nullable=True)
    light_sleep_seconds = Column(Integer, nullable=True)
    rem_sleep_seconds = Column(Integer, nullable=True)
    awake_seconds = Column(Integer, nullable=True)
    sleep_score = Column(Integer, nullable=True)
    avg_overnight_hrv = Column(Float, nullable=True)
    avg_overnight_spo2 = Column(Float, nullable=True)
    avg_overnight_rr = Column(Float, nullable=True)
    raw_sleep_levels = Column(JSON, nullable=True)


class Activity(Base):
    """Training sessions and activities."""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    garmin_activity_id = Column(String, unique=True, nullable=False)
    activity_type = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    avg_hr = Column(Integer, nullable=True)
    max_hr = Column(Integer, nullable=True)
    min_hr = Column(Integer, nullable=True)
    calories = Column(Integer, nullable=True)
    avg_stress = Column(Integer, nullable=True)
    training_effect_aerobic = Column(Float, nullable=True)
    training_effect_anaerobic = Column(Float, nullable=True)
    hr_zones_json = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=True)


class Habit(Base):
    """Canonical habit definition."""

    __tablename__ = "habits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: str(uuid4()),
    )
    name = Column(String, nullable=False, unique=True, index=True)
    habit_type = Column(String, nullable=False)  # 'binary' | 'counter'
    source = Column(String, nullable=False, server_default=text("'manual'"), default="manual")
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Generic-tracker fields. ``period`` defines the granularity of hit/miss
    # evaluation; ``target_value`` is the threshold; ``is_negative`` flips the
    # comparison ("≤ target" instead of "≥ target").
    is_negative = Column(Boolean, nullable=False, server_default=text("0"), default=False)
    target_value = Column(Integer, nullable=True)
    period = Column(String, nullable=False, server_default=text("'day'"), default="day")


class DailyHabit(Base):
    """Per-date logged value for a habit."""

    __tablename__ = "daily_habits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False, index=True)
    habit_value = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("date", "habit_id", name="uix_habit_date_habit"),)


class HabitDisplayConfig(Base):
    """User-configured display settings for each habit (label, emoji, color, order)."""

    __tablename__ = "habit_display_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    habit_name = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=True)
    emoji = Column(String, nullable=True)
    color = Column(String, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)


class GymSessionTemplate(Base):
    """Current gym session plan definition."""

    __tablename__ = "gym_session_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class GymActivity(Base):
    """Reusable gym activity definition for templates and ad-hoc sessions."""

    __tablename__ = "gym_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True, index=True)
    activity_type = Column(String, nullable=False)
    target_sets = Column(Integer, nullable=True)
    target_reps = Column(Integer, nullable=True)
    target_weight = Column(Float, nullable=True)
    target_weight_unit = Column(String, nullable=True)
    target_duration_minutes = Column(Float, nullable=True)
    target_intensity = Column(String, nullable=True)
    target_speed = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class GymTemplateActivity(Base):
    """Ordered activity row within a current gym session template."""

    __tablename__ = "gym_template_activities"

    __table_args__ = (UniqueConstraint("template_id", "sort_order", name="uix_gym_template_activity_order"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, ForeignKey("gym_activities.id"), nullable=True, index=True)
    template_id = Column(Integer, ForeignKey("gym_session_templates.id"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False)
    activity_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    target_sets = Column(Integer, nullable=True)
    target_reps = Column(Integer, nullable=True)
    target_weight = Column(Float, nullable=True)
    target_weight_unit = Column(String, nullable=True)
    target_duration_minutes = Column(Float, nullable=True)
    target_intensity = Column(String, nullable=True)
    target_speed = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)


class GymSessionLog(Base):
    """One logged gym session for a date."""

    __tablename__ = "gym_session_logs"

    __table_args__ = (UniqueConstraint("date", name="uix_gym_session_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("gym_session_templates.id"), nullable=True, index=True)
    template_name_snapshot = Column(String, nullable=False)
    date = Column(Date, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)


class GymSessionActivityLog(Base):
    """Snapshot and actual values for one activity in a logged gym session."""

    __tablename__ = "gym_session_activity_logs"
    __table_args__ = (UniqueConstraint("session_log_id", "sort_order", name="uix_gym_session_activity_order"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, ForeignKey("gym_activities.id"), nullable=True, index=True)
    session_log_id = Column(Integer, ForeignKey("gym_session_logs.id"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False)
    activity_type = Column(String, nullable=False)
    name_snapshot = Column(String, nullable=False)
    planned_sets = Column(Integer, nullable=True)
    planned_reps = Column(Integer, nullable=True)
    planned_weight = Column(Float, nullable=True)
    planned_weight_unit = Column(String, nullable=True)
    planned_duration_minutes = Column(Float, nullable=True)
    planned_intensity = Column(String, nullable=True)
    planned_speed = Column(Float, nullable=True)
    planned_notes = Column(Text, nullable=True)
    actual_sets = Column(Integer, nullable=True)
    actual_reps = Column(Integer, nullable=True)
    actual_weight = Column(Float, nullable=True)
    actual_weight_unit = Column(String, nullable=True)
    actual_duration_minutes = Column(Float, nullable=True)
    actual_intensity = Column(String, nullable=True)
    actual_speed = Column(Float, nullable=True)
    completed = Column(Boolean, nullable=False, server_default=text("0"), default=False)
    rating = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class AppSetting(Base):
    """Generic persisted application setting."""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContextEvent(Base):
    """Date-range context that explains non-baseline days."""

    __tablename__ = "context_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    tags = Column(JSON, nullable=False, default=list)
    intensity = Column(String, nullable=True)
    exclude_from_baseline = Column(Boolean, nullable=False, server_default=text("1"), default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplementPlanVersion(Base):
    """Versioned supplement list for a dose slot."""

    __tablename__ = "supplement_plan_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slot = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    items = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("slot", "version", name="uix_supplement_slot_version"),
    )


class SupplementLog(Base):
    """Per-date supplement group completion with frozen item snapshot."""

    __tablename__ = "supplement_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    slot = Column(String, nullable=False, index=True)
    plan_version_id = Column(
        Integer,
        ForeignKey("supplement_plan_versions.id"),
        nullable=False,
        index=True,
    )
    completed = Column(Boolean, nullable=False, server_default=text("1"), default=True)
    snapshot = Column(JSON, nullable=False)
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "slot", name="uix_supplement_log_date_slot"),
    )


class DailySummaryCache(Base):
    """Materialized daily summary (optional performance cache)."""

    __tablename__ = "daily_summary_cache"

    date = Column(Date, primary_key=True)
    computed_at = Column(DateTime, nullable=True)
    summary_json = Column(JSON, nullable=True)
