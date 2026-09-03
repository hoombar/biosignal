import json
import zipfile
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.models.database import (
    AppSetting,
    ContextEvent,
    HeartRateSample,
    Habit,
    DailyHabit,
)
from app.services.full_export import EXCLUDED_TABLES, INCLUDED_TABLES, build_full_export


@pytest.mark.asyncio
async def test_full_export_contains_analysis_data_and_manifest(async_session):
    async_session.add_all([
        HeartRateSample(timestamp=datetime(2025, 1, 2, 8), heart_rate=60),
        Habit(name="Coffee", habit_type="binary", source="manual"),
        AppSetting(key="preferences", value={"weather_temperature_unit": "celsius"}),
        ContextEvent(
            title="Holiday", start_date=date(2025, 1, 2), end_date=date(2025, 1, 3),
            category="travel", tags=["trip"],
        ),
    ])
    await async_session.commit()

    archive = await build_full_export(async_session)
    try:
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            assert manifest["format_version"] == 1
            assert "heart_rate_samples" in manifest["included_tables"]
            assert "raw_garmin_responses" in manifest["excluded_tables"]
            assert "daily_summary_cache" in manifest["excluded_tables"]
            assert manifest["date_range"] == {"start": "2025-01-02", "end": "2025-01-03"}
            assert "file_semantics" in manifest
            assert manifest["data_through"]
            assert manifest["observed_health_data_coverage"] == {"start": "2025-01-02", "end": "2025-01-02"}
            assert "README.md" in bundle.namelist()

            heart_rate = [
                json.loads(line)
                for line in bundle.read("data/heart_rate_samples.jsonl").splitlines()
            ]
            assert heart_rate == [{"id": 1, "timestamp": "2025-01-02T08:00:00Z", "heart_rate": 60}]
            settings = json.loads(bundle.read("data/app_settings.jsonl").decode())
            assert settings["key"] == "preferences"
            assert settings["value"] == {"weather_temperature_unit": "celsius"}
    finally:
        archive.close()


def test_full_export_registry_is_explicit_and_privacy_scoped():
    assert "daily_summary_cache" not in INCLUDED_TABLES
    assert set(INCLUDED_TABLES).isdisjoint(EXCLUDED_TABLES)
    assert "raw_garmin_responses" in EXCLUDED_TABLES
    assert "sync_log" in EXCLUDED_TABLES


@pytest.mark.asyncio
async def test_full_export_normalizes_sparse_habits_without_changing_raw_rows(async_session):
    habit = Habit(name="coffee", habit_type="counter", tracking_start_date=date(2025, 1, 2))
    async_session.add(habit)
    await async_session.flush()
    async_session.add_all([
        DailyHabit(date=date(2025, 1, 1), habit_id=habit.id, habit_value=3),
        DailyHabit(date=date(2025, 1, 2), habit_id=habit.id, habit_value=2),
        HeartRateSample(timestamp=datetime(2025, 1, 3, 8), heart_rate=60),
    ])
    await async_session.commit()
    before = [(row.date, row.habit_value) for row in (await async_session.execute(select(DailyHabit))).scalars()]

    archive = await build_full_export(async_session)
    try:
        with zipfile.ZipFile(archive) as bundle:
            raw = [json.loads(line) for line in bundle.read("data/daily_habits.jsonl").splitlines()]
            matrix = [json.loads(line) for line in bundle.read("analysis/daily_habit_matrix.jsonl").splitlines()]
            assert [(row["date"], row["habit_value"]) for row in raw] == [
                ("2025-01-01", 3), ("2025-01-02", 2)
            ]
            assert any(row["date"] == "2025-01-03" and row["value_state"] == "inferred_zero" for row in matrix)
            assert any(row["date"] == "2025-01-01" and row["value_state"] == "explicit_positive" for row in matrix)
    finally:
        archive.close()
    after = [(row.date, row.habit_value) for row in (await async_session.execute(select(DailyHabit))).scalars()]
    assert after == before
