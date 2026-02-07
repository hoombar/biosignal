"""Analysis API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.schemas.responses import CorrelationResult, PatternResult, InsightResult
from app.services.analysis import compute_correlations, compute_patterns, generate_insights

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/correlations", response_model=list[CorrelationResult])
async def get_correlations(
    target_habit: str,
    min_days: int = 5,
    db: AsyncSession = Depends(get_db)
):
    """
    Get correlation analysis between all metrics and a target habit.

    Args:
        target_habit: The habit name to correlate against
        min_days: Minimum days of data required for analysis
    """
    settings = get_settings()
    correlations = await compute_correlations(
        db, settings.tz, target_habit=target_habit, min_days=min_days
    )

    return [CorrelationResult(**c) for c in correlations]


@router.get("/patterns", response_model=list[PatternResult])
async def get_patterns(db: AsyncSession = Depends(get_db)):
    """Get pattern detection results with conditional probabilities."""
    settings = get_settings()
    patterns = await compute_patterns(db, settings.tz)

    return [PatternResult(**p) for p in patterns]


@router.get("/insights", response_model=list[InsightResult])
async def get_insights(db: AsyncSession = Depends(get_db)):
    """Get plain-English insights generated from analysis."""
    settings = get_settings()
    insights = await generate_insights(db, settings.tz)

    return [InsightResult(**i) for i in insights]
