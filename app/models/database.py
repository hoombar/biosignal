from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    Float,
    JSON,
    Index,
    UniqueConstraint,
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


class RawHabitSyncResponse(Base):
    """Raw HabitSync API responses."""

    __tablename__ = "raw_habitsync_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    response = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)


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


class DailyHabit(Base):
    """Habits from HabitSync (flexible schema)."""

    __tablename__ = "daily_habits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    habit_name = Column(String, nullable=False, index=True)
    habit_value = Column(String, nullable=False)
    habit_type = Column(String, nullable=True)

    __table_args__ = (UniqueConstraint("date", "habit_name", name="uix_habit_date_name"),)


class HabitDisplayConfig(Base):
    """User-configured display settings for each habit (label, emoji, order)."""

    __tablename__ = "habit_display_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    habit_name = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=True)
    emoji = Column(String, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)


class DailySummaryCache(Base):
    """Materialized daily summary (optional performance cache)."""

    __tablename__ = "daily_summary_cache"

    date = Column(Date, primary_key=True)
    computed_at = Column(DateTime, nullable=True)
    summary_json = Column(JSON, nullable=True)
