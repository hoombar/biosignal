import json
import zipfile
from datetime import date, datetime

import pytest

from app.models.database import (
    AppSetting,
    ContextEvent,
    HeartRateSample,
    Habit,
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
