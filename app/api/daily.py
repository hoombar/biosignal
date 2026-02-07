"""Daily data API endpoints."""

from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.models.database import DailyHabit
from app.schemas.responses import HabitResponse, DailySummary
from app.services.features import compute_features_range

router = APIRouter(prefix="/api", tags=["daily"])


@router.get("/habits/names", response_model=list[str])
async def get_habit_names(db: AsyncSession = Depends(get_db)):
    """Get list of distinct habit names."""
    result = await db.execute(
        select(DailyHabit.habit_name).distinct()
    )
    return [row[0] for row in result.all()]


@router.get("/habits", response_model=list[HabitResponse])
async def get_habits(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Get habit data for the last N days."""
    cutoff = date.today() - timedelta(days=days)

    result = await db.execute(
        select(DailyHabit)
        .where(DailyHabit.date >= cutoff)
        .order_by(DailyHabit.date.desc())
    )
    habits = result.scalars().all()

    # Group by date
    by_date: dict[str, dict] = {}
    for habit in habits:
        date_str = habit.date.isoformat()
        if date_str not in by_date:
            by_date[date_str] = {}

        # Convert value based on type
        if habit.habit_type == "boolean":
            value = habit.habit_value.lower() == "true"
        elif habit.habit_type == "counter":
            value = int(habit.habit_value) if habit.habit_value else 0
        else:
            value = habit.habit_value

        by_date[date_str][habit.habit_name] = value

    # Convert to list of responses
    responses = [
        HabitResponse(date=date_str, habits=habits_dict)
        for date_str, habits_dict in sorted(by_date.items(), reverse=True)
    ]

    return responses


@router.get("/daily", response_model=list[DailySummary])
async def get_daily_summaries(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Get computed daily summaries for the last N days."""
    settings = get_settings()
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    # Compute features for the date range
    features_list = await compute_features_range(
        db,
        start_date,
        end_date,
        timezone=settings.tz
    )

    # Convert to DailySummary objects
    summaries = [DailySummary(**features) for features in features_list]

    return summaries
