"""Tests for trends metadata validation.

Verifies that:
1. Every numeric/boolean key in FEATURE_METADATA maps to an actual DailySummary field
   (not a phantom field like bb_9am that exists in metadata but not in the schema).
2. compute_correlations() only returns metric names that are real DailySummary fields.
"""

import types
import typing
import pytest
from datetime import date, timedelta

from app.api.export import FEATURE_METADATA
from app.schemas.responses import DailySummary
from app.models.database import SleepSession, DailyHabit
from app.services.analysis import compute_correlations


def _make_date(offset: int) -> date:
    """Return a date in the recent past (within the last 365 days)."""
    anchor = date.today() - timedelta(days=30)
    return anchor + timedelta(days=offset)


def _get_daily_summary_numeric_fields() -> set[str]:
    """Return field names from DailySummary that are numeric or boolean (not str, not list)."""
    fields = set()
    for field_name, field_info in DailySummary.model_fields.items():
        ann = field_info.annotation

        # Unwrap Union / Optional types (handles both typing.Union and Python 3.10+ X | Y)
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        if origin is typing.Union or isinstance(ann, types.UnionType):
            non_none = [a for a in args if a is not type(None)]
            if not non_none:
                continue
            ann = non_none[0]

        if ann in (int, float, bool):
            fields.add(field_name)

    return fields


class TestFeatureMetadataFieldsExistInDailySummary:
    """Verify FEATURE_METADATA doesn't reference phantom fields absent from DailySummary."""

    def test_feature_metadata_fields_exist_in_daily_summary(self):
        """Every numeric/boolean FEATURE_METADATA key must either:
        (a) exist as a numeric/boolean field on DailySummary, OR
        (b) belong to the 'Habits' category (those live in the dynamic habits list).

        This test catches phantom fields like bb_9am / bb_12pm / bb_2pm / bb_6pm that
        appear in FEATURE_METADATA but have no corresponding scalar field on DailySummary,
        causing them to return all-null data in the UI.
        """
        daily_summary_fields = _get_daily_summary_numeric_fields()

        phantom_fields = []

        for key, meta in FEATURE_METADATA.items():
            # Habit-category fields are in the dynamic habits list, not direct fields
            if meta["category"] == "Habits":
                continue

            # Text/categorical fields (non-numeric) can't be charted — skip
            unit = meta.get("unit", "")
            if unit == "text" or "/" in unit:
                continue

            if key not in daily_summary_fields:
                phantom_fields.append(key)

        assert phantom_fields == [], (
            f"FEATURE_METADATA contains {len(phantom_fields)} key(s) that don't exist as "
            f"numeric fields in DailySummary: {phantom_fields}. "
            f"Either add them to DailySummary or remove them from FEATURE_METADATA."
        )


class TestCorrelationsReturnsValidMetricKeys:
    """Verify compute_correlations() only returns real DailySummary field names."""

    @pytest.mark.asyncio
    async def test_correlations_returns_valid_metric_keys(self, async_session):
        """Metric names in compute_correlations() results must be DailySummary fields
        (or habit_-prefixed names from the dynamic habits list), not arbitrary keys.
        """
        # Seed 10 days of alternating slump/no-slump with clear sleep pattern
        for i in range(10):
            d = _make_date(i)
            slump = i % 2 == 0
            async_session.add(SleepSession(
                date=d,
                total_sleep_seconds=int((5.5 if slump else 8.5) * 3600),
                sleep_score=70,
            ))
            async_session.add(DailyHabit(
                date=d,
                habit_name="pm_slump",
                habit_value="true" if slump else "false",
                habit_type="boolean",
            ))
        await async_session.commit()

        result = await compute_correlations(async_session, target_habit="pm_slump", min_days=5)

        daily_summary_fields = _get_daily_summary_numeric_fields()

        invalid_metrics = []
        for corr in result:
            metric = corr["metric"]
            if metric.startswith("habit_"):
                continue  # Dynamic habit_ keys are always valid
            if metric not in daily_summary_fields:
                invalid_metrics.append(metric)

        assert invalid_metrics == [], (
            f"compute_correlations() returned metrics not in DailySummary: {invalid_metrics}. "
            f"Valid numeric DailySummary fields: {sorted(daily_summary_fields)}"
        )
