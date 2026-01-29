"""Tests for Garmin data parsers."""

import json
from datetime import date
from pathlib import Path

from app.services.parsers import (
    parse_heart_rate,
    parse_body_battery,
    parse_stress,
    parse_hrv,
    parse_spo2,
    parse_steps,
    parse_sleep,
    parse_activities,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> dict | list:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / filename) as f:
        return json.load(f)


def test_parse_heart_rate():
    """Test parsing heart rate data."""
    raw = load_fixture("garmin_heart_rate.json")
    samples = parse_heart_rate(raw, date(2025, 1, 28))

    assert len(samples) > 0
    assert all(s.heart_rate > 0 for s in samples)
    assert all(s.timestamp is not None for s in samples)


def test_parse_body_battery():
    """Test parsing body battery data."""
    raw = load_fixture("garmin_body_battery.json")
    samples = parse_body_battery(raw, date(2025, 1, 28))

    assert len(samples) > 0
    assert all(0 <= s.body_battery <= 100 for s in samples)
    assert all(s.timestamp is not None for s in samples)


def test_parse_stress():
    """Test parsing stress data."""
    raw = load_fixture("garmin_stress.json")
    samples = parse_stress(raw, date(2025, 1, 28))

    assert len(samples) > 0
    assert all(s.timestamp is not None for s in samples)
    # Stress can be negative (-1, -2 for rest/unmeasured)
    assert all(s.stress_level >= -2 for s in samples)


def test_parse_hrv():
    """Test parsing HRV data."""
    raw = load_fixture("garmin_hrv.json")
    samples = parse_hrv(raw, date(2025, 1, 28))

    assert len(samples) > 0
    assert all(s.hrv_value > 0 for s in samples)
    assert all(s.reading_type is not None for s in samples)


def test_parse_spo2():
    """Test parsing SpO2 data."""
    raw = load_fixture("garmin_spo2.json")
    samples = parse_spo2(raw, date(2025, 1, 28))

    assert len(samples) > 0
    assert all(90 <= s.spo2_value <= 100 for s in samples)


def test_parse_steps():
    """Test parsing steps data."""
    raw = load_fixture("garmin_steps.json")
    samples = parse_steps(raw, date(2025, 1, 28))

    assert len(samples) > 0
    assert all(s.steps >= 0 for s in samples)
    assert all(s.duration_seconds == 3600 for s in samples)


def test_parse_sleep():
    """Test parsing sleep data."""
    raw = load_fixture("garmin_sleep.json")
    session = parse_sleep(raw, date(2025, 1, 28))

    assert session is not None
    assert session.total_sleep_seconds > 0
    assert session.sleep_score is not None
    assert session.sleep_start is not None
    assert session.sleep_end is not None


def test_parse_activities():
    """Test parsing activities data."""
    raw = load_fixture("garmin_activities.json")
    activities = parse_activities(raw)

    assert len(activities) == 2
    assert activities[0].activity_type == "brazilian_jiu_jitsu"
    assert activities[0].avg_hr > 0
    assert activities[1].activity_type == "running"
