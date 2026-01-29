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
    days: int | None = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get correlation analysis between all metrics and PM slump.

    Args:
        days: Optional filter for last N days (not implemented yet)
    """
    settings = get_settings()
    correlations = await compute_correlations(db, settings.tz)

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
