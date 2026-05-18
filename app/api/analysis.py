"""Analysis API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.services.habit_config import list_habit_display_entries
from app.services.supplements import list_supplement_items
from app.api.export import FEATURE_METADATA
from app.schemas.responses import (
    CorrelationResult,
    CorrelationSnapshotResult,
    CorrelationTargetOption,
    PatternResult,
    InsightResult,
)
from app.services.analysis import (
    compute_correlation_snapshot,
    compute_correlations,
    compute_patterns,
    generate_insights,
)

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/correlation-targets", response_model=list[CorrelationTargetOption])
async def get_correlation_targets(db: AsyncSession = Depends(get_db)):
    """Return all selectable targets for correlations UI.

    Includes:
    - numeric/boolean non-habit metrics from FEATURE_METADATA
    - distinct tracked habits from daily_habits table (as "habit:<name>")
    """
    targets: list[CorrelationTargetOption] = []

    for key, meta in sorted(FEATURE_METADATA.items(), key=lambda kv: kv[0]):
        category = meta.get("category", "Other")
        unit = meta.get("unit", "")
        if category == "Habits":
            continue
        if unit in {"text", "low/medium/high"}:
            continue
        targets.append(CorrelationTargetOption(
            target=key,
            label=key.replace("_", " "),
            kind="metric",
            category=category,
        ))

    habit_entries = await list_habit_display_entries(db)
    for entry in habit_entries:
        name = entry["habit_name"]
        label = entry["display_name"] or name.replace("_", " ")
        targets.append(CorrelationTargetOption(
            target=f"habit:{name}",
            label=label,
            kind="habit",
            category="Habits",
        ))

    for item in await list_supplement_items(db):
        targets.append(CorrelationTargetOption(
            target=f"supplement:{item['key']}",
            label=item["name"],
            kind="supplement",
            category="Supplements",
        ))

    return targets


@router.get("/correlations", response_model=list[CorrelationResult])
async def get_correlations(
    target: str | None = None,
    target_habit: str | None = None,
    min_days: int = 5,
    db: AsyncSession = Depends(get_db)
):
    """
    Get correlation analysis between all metrics and a target habit.

    Args:
        target: Generic target selector. Use "habit:<name>" for habits or
            top-level metric keys like "steps_total".
        target_habit: Legacy habit target selector (backwards compatible)
        min_days: Minimum days of data required for analysis
    """
    if not target and not target_habit:
        raise HTTPException(status_code=422, detail="Either 'target' or 'target_habit' is required")

    settings = get_settings()
    correlations = await compute_correlations(
        db,
        settings.tz,
        target=target,
        target_habit=target_habit,
        min_days=min_days,
    )

    return [CorrelationResult(**c) for c in correlations]


@router.get("/correlation-snapshot", response_model=list[CorrelationSnapshotResult])
async def get_correlation_snapshot(
    min_days: int = 14,
    min_abs: float = 0.3,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Get curated overview correlations from common interesting signal buckets."""
    settings = get_settings()
    snapshot = await compute_correlation_snapshot(
        db,
        settings.tz,
        min_days=min_days,
        min_abs=min_abs,
        limit=limit,
    )
    return [CorrelationSnapshotResult(**c) for c in snapshot]


@router.get("/patterns", response_model=list[PatternResult])
async def get_patterns(
    target_habit: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get pattern detection results with conditional probabilities."""
    settings = get_settings()
    patterns = await compute_patterns(db, settings.tz, target_habit=target_habit)

    return [PatternResult(**p) for p in patterns]


@router.get("/insights", response_model=list[InsightResult])
async def get_insights(
    target_habit: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get plain-English insights generated from analysis."""
    settings = get_settings()
    insights = await generate_insights(db, settings.tz, target_habit=target_habit)

    return [InsightResult(**i) for i in insights]
