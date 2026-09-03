"""Build a privacy-scoped, analysis-friendly export archive."""

from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import BinaryIO, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.database import (
    Activity, AppSetting, BodyBatterySample, ContextEvent, DailyHabit,
    EnvironmentalMetric, GymActivity, GymSessionActivityLog, GymSessionLog,
    GymSessionTemplate, GymTemplateActivity, Habit, HabitDisplayConfig,
    HeartRateSample, HrvSample, SleepSession, Spo2Sample, StepsSample,
    StressSample, SupplementLog, SupplementPlanVersion,
)
from app.services.habit_semantics import habit_activation, normalized_habit_value


INCLUDED_TABLES = [
    "environmental_metrics", "heart_rate_samples", "body_battery_samples",
    "stress_samples", "hrv_samples", "spo2_samples", "steps_samples",
    "sleep_sessions", "activities", "habits", "daily_habits",
    "habit_display_config", "gym_session_templates", "gym_activities",
    "gym_template_activities", "gym_session_logs", "gym_session_activity_logs",
    "app_settings", "context_events", "supplement_plan_versions", "supplement_logs",
]
EXCLUDED_TABLES = [
    "raw_garmin_responses", "sync_log", "daily_summary_cache", "credentials_and_tokens",
]

_TABLES = {
    "environmental_metrics": (EnvironmentalMetric, {"location_key", "raw_metadata"}),
    "heart_rate_samples": (HeartRateSample, set()),
    "body_battery_samples": (BodyBatterySample, set()),
    "stress_samples": (StressSample, set()),
    "hrv_samples": (HrvSample, set()),
    "spo2_samples": (Spo2Sample, set()),
    "steps_samples": (StepsSample, set()),
    "sleep_sessions": (SleepSession, set()),
    "activities": (Activity, {"raw_data"}),
    "habits": (Habit, set()),
    "daily_habits": (DailyHabit, set()),
    "habit_display_config": (HabitDisplayConfig, set()),
    "gym_session_templates": (GymSessionTemplate, set()),
    "gym_activities": (GymActivity, set()),
    "gym_template_activities": (GymTemplateActivity, set()),
    "gym_session_logs": (GymSessionLog, set()),
    "gym_session_activity_logs": (GymSessionActivityLog, set()),
    "app_settings": (AppSetting, set()),
    "context_events": (ContextEvent, set()),
    "supplement_plan_versions": (SupplementPlanVersion, set()),
    "supplement_logs": (SupplementLog, set()),
}

_DATE_COLUMNS = {
    "environmental_metrics": ("date",),
    "heart_rate_samples": ("timestamp",),
    "body_battery_samples": ("timestamp",),
    "stress_samples": ("timestamp",),
    "hrv_samples": ("timestamp",),
    "spo2_samples": ("timestamp",),
    "steps_samples": ("timestamp",),
    "sleep_sessions": ("date",),
    "activities": ("start_time", "end_time"),
    "daily_habits": ("date",),
    "gym_session_logs": ("date",),
    "supplement_logs": ("date",),
    "context_events": ("start_date", "end_date"),
}


def _json_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _row_to_dict(row, excluded: set[str], replacements: dict | None = None) -> dict:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
        if column.name not in excluded
    }


def _safe_row_to_dict(row, excluded: set[str], replacements: dict | None = None) -> dict:
    values = _row_to_dict(row, excluded)
    values.update(replacements or {})
    return values


async def _date_range(session: AsyncSession) -> tuple[date | None, date | None]:
    bounds: list[tuple[date | datetime | None, date | datetime | None]] = []
    for table_name, (model, _) in _TABLES.items():
        for name in _DATE_COLUMNS.get(table_name, ()):
            column = getattr(model, name)
            result = await session.execute(select(func.min(column), func.max(column)))
            bounds.append(result.one())
    dates = [value.date() if isinstance(value, datetime) else value for pair in bounds for value in pair if value]
    return (min(dates), max(dates)) if dates else (None, None)


async def _health_date_range(session: AsyncSession) -> tuple[date | None, date | None]:
    """Bounds for observed health records, excluding generated environment data."""
    names = (
        "heart_rate_samples", "body_battery_samples", "stress_samples", "hrv_samples",
        "spo2_samples", "steps_samples", "sleep_sessions", "activities",
    )
    dates: list[date] = []
    for name in names:
        model, _ = _TABLES[name]
        for column_name in _DATE_COLUMNS[name]:
            result = await session.execute(select(func.min(getattr(model, column_name)), func.max(getattr(model, column_name))))
            for value in result.one():
                if value:
                    dates.append(value.date() if isinstance(value, datetime) else value)
    return (min(dates), max(dates)) if dates else (None, None)


async def _habit_matrix(session: AsyncSession, start_date: date, end_date: date) -> tuple[list[dict], list[dict]]:
    habits = (await session.execute(select(Habit).order_by(Habit.name))).scalars().all()
    rows = (await session.execute(select(DailyHabit).order_by(DailyHabit.habit_id, DailyHabit.date))).scalars().all()
    rows_by_habit: dict[int, list[DailyHabit]] = {}
    rows_by_date: dict[tuple[int, date], DailyHabit] = {}
    for row in rows:
        rows_by_habit.setdefault(row.habit_id, []).append(row)
        rows_by_date[(row.habit_id, row.date)] = row

    activations = []
    matrix = []
    for habit in habits:
        activation, rule = habit_activation(habit, rows_by_habit.get(habit.id, []))
        activations.append({
            "name": habit.name,
            "habit_id": habit.id,
            "tracking_start_date": activation.isoformat() if activation else None,
            "archived_date": habit.archived_at.date().isoformat() if habit.archived_at else None,
            "activation_rule": rule,
        })
        current = start_date
        while current <= end_date:
            value, state = normalized_habit_value(
                habit, rows_by_date.get((habit.id, current)), current, activation
            )
            matrix.append({
                "date": current.isoformat(),
                "habit": habit.name,
                "habit_type": habit.habit_type,
                "value": value,
                "value_state": state,
            })
            current += timedelta(days=1)
    return matrix, activations


async def build_full_export(session: AsyncSession) -> BinaryIO:
    """Build and return a seekable ZIP file; callers own and close it."""
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    settings = get_settings()
    start_date, end_date = await _date_range(session)
    health_start, health_end = await _health_date_range(session)
    data_through = datetime.now(ZoneInfo(settings.tz)).date() - timedelta(days=1)
    export_habit_activations = []
    if start_date and end_date:
        _, export_habit_activations = await _habit_matrix(session, start_date, end_date)
    counts = {}

    for name in INCLUDED_TABLES:
        model, _ = _TABLES[name]
        query = select(func.count()).select_from(model)
        if name == "app_settings":
            query = query.where(model.key == "preferences")
        counts[name] = (await session.execute(query)).scalar_one()

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            "format_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "application_timezone": settings.tz,
            "timestamp_policy": "naive application and Garmin timestamps are UTC",
            "included_tables": INCLUDED_TABLES,
            "excluded_tables": EXCLUDED_TABLES,
            "date_range": {"start": start_date.isoformat() if start_date else None,
                           "end": end_date.isoformat() if end_date else None},
            "data_through": data_through.isoformat(),
            "observed_health_data_coverage": {
                "start": health_start.isoformat() if health_start else None,
                "end": health_end.isoformat() if health_end else None,
            },
            "generated_environmental_coverage": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "file_semantics": {
                "data/*.jsonl": {
                    "nature": "raw database export",
                    "missing_value_policy": "Rows and null columns are preserved; no rows or values are inferred.",
                },
                "data/daily_habits.jsonl": {
                    "nature": "raw sparse positive-only habit log",
                    "missing_value_policy": "Absent row is unknown/not recorded, never an explicit zero.",
                },
                "analysis/daily_features.jsonl": {
                    "nature": "normalized computed analysis features",
                    "missing_value_policy": "Active sparse habits use inferred_zero; sensor and environmental nulls remain null.",
                },
                "analysis/daily_habit_matrix.jsonl": {
                    "nature": "normalized habit observations with provenance",
                    "missing_value_policy": "States distinguish explicit, inferred, not-yet-tracked, and archived dates.",
                },
                "data/supplement_logs.jsonl": {
                    "nature": "raw versioned supplement completion records",
                    "missing_value_policy": "Absence is unknown unless a plan/slot-specific product policy says otherwise; no zero inference is performed.",
                },
            },
            "habit_activation": export_habit_activations,
            "record_counts": counts,
            "privacy": {
                "raw_garmin_payloads": False,
                "precise_environmental_location": False,
                "credentials_and_tokens": False,
            },
        }
        archive.writestr("README.md", _readme(manifest))

        for name in INCLUDED_TABLES:
            model, excluded = _TABLES[name]
            query = select(model)
            if name == "app_settings":
                query = query.where(model.key == "preferences")
            query = query.order_by(*model.__table__.primary_key.columns)
            with archive.open(f"data/{name}.jsonl", "w") as member:
                result = await session.stream(query)
                async for row in result.scalars():
                    replacements = {"location_key": "redacted"} if name == "environmental_metrics" else None
                    member.write((json.dumps(_safe_row_to_dict(row, excluded, replacements), sort_keys=True) + "\n").encode())

        if start_date and end_date:
            from app.api.export import FEATURE_METADATA
            from app.services.features import compute_features_range

            with archive.open("analysis/daily_features.jsonl", "w") as member:
                features = await compute_features_range(
                    session, start_date, end_date, timezone=settings.tz,
                    persist_environmental=False,
                )
                for row in features:
                    member.write((json.dumps(_json_value(row), sort_keys=True) + "\n").encode())
            matrix, _ = await _habit_matrix(session, start_date, end_date)
            archive.writestr(
                "analysis/daily_habit_matrix.jsonl",
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in matrix),
            )
            archive.writestr("analysis/feature_metadata.json", json.dumps(FEATURE_METADATA, indent=2, sort_keys=True) + "\n")
        else:
            archive.writestr("analysis/daily_features.jsonl", "")
            archive.writestr("analysis/daily_habit_matrix.jsonl", "")
            archive.writestr("analysis/feature_metadata.json", "{}\n")

        # Manifest is written last so activation metadata reflects the matrix.
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    output.seek(0)
    return cast(BinaryIO, output)


def _readme(manifest: dict) -> str:
    return """# Biosignal Full Data Export

This is an analysis export, not a restore package. `manifest.json` describes the
format, date range, included tables, timestamp policy, and privacy exclusions.

The `data/` directory contains one UTF-8 JSON Lines file per included dataset.
`analysis/daily_features.jsonl` and `analysis/daily_habit_matrix.jsonl` are
normalized analysis files. A raw absent habit row is not an explicit zero. In
normalized files, an absent row during active tracking is `value: 0` with
`value_state: "inferred_zero"`; dates before activation are
`not_yet_tracked`, and dates on/after archival are `no_longer_tracked`.
Explicit zeros remain `explicit_zero`. Sensor, sleep, and environmental nulls
always remain missing and are never zero-filled. Use `data/` for faithful raw
export/reprocessing, or `analysis/` for analysis with provenance.

Raw Garmin payloads, credentials, authentication tokens, sync diagnostics,
derived caches, and precise environmental location metadata are intentionally
excluded.
"""
