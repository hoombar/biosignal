"""Daily data API endpoints."""

import calendar
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.models.database import DailyHabit, SleepSession
from app.schemas.responses import (
    HabitResponse,
    DailySummary,
    CalendarDaySummary,
    NotableDay,
)
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
async def get_daily_summaries(
    days: int = 30,
    start: Optional[date] = Query(None, description="Start date (inclusive)"),
    end: Optional[date] = Query(None, description="End date (inclusive)"),
    db: AsyncSession = Depends(get_db),
):
    """Get computed daily summaries.

    Supports two modes:
    - start + end params: return summaries for the exact date range
    - days param (default): return last N days from today
    """
    settings = get_settings()

    if start is not None and end is not None:
        start_date = start
        end_date = end
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

    features_list = await compute_features_range(
        db,
        start_date,
        end_date,
        timezone=settings.tz
    )

    summaries = [DailySummary(**features) for features in features_list]
    return summaries


@router.get("/daily/calendar", response_model=list[CalendarDaySummary])
async def get_calendar_year(
    year: int = Query(..., description="Year to fetch calendar data for"),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight year summary for the heatmap.

    Returns one entry per day of the year with only sleep_score and has_slump.
    Queries the database directly (no feature computation) for speed.
    """
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    # Fetch sleep scores for the year
    sleep_result = await db.execute(
        select(SleepSession.date, SleepSession.sleep_score)
        .where(SleepSession.date >= start_date, SleepSession.date <= end_date)
    )
    sleep_by_date = {row.date: row.sleep_score for row in sleep_result.all()}

    # Fetch afternoon_slump habits for the year
    slump_result = await db.execute(
        select(DailyHabit.date, DailyHabit.habit_value)
        .where(
            DailyHabit.date >= start_date,
            DailyHabit.date <= end_date,
            DailyHabit.habit_name == "afternoon_slump",
        )
    )
    slump_by_date = {}
    for row in slump_result.all():
        try:
            slump_by_date[row.date] = int(row.habit_value) > 0
        except (ValueError, TypeError):
            slump_by_date[row.date] = False

    # Build entries for every day of the year
    days_in_year = (end_date - start_date).days + 1
    summaries = []
    for i in range(days_in_year):
        d = start_date + timedelta(days=i)
        summaries.append(CalendarDaySummary(
            date=d.isoformat(),
            sleep_score=sleep_by_date.get(d),
            has_slump=slump_by_date.get(d, False),
        ))

    return summaries


@router.get("/daily/notable", response_model=list[NotableDay])
async def get_notable_days(
    year: int = Query(..., description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: AsyncSession = Depends(get_db),
):
    """Get notable days (extremes and anomalies) for a given month.

    Returns up to 5 notable items: best/worst sleep, HRV extremes,
    and metrics that deviate significantly from the rolling average.
    """
    settings = get_settings()

    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    features_list = await compute_features_range(
        db, start_date, end_date, timezone=settings.tz
    )

    notable = _compute_notable_days(features_list)
    return notable


def _compute_notable_days(features_list: list[dict]) -> list[NotableDay]:
    """Extract notable days from a month of feature data.

    Finds extremes (best/worst) across key metrics. Returns up to 5 items
    sorted by significance.
    """
    if not features_list:
        return []

    candidates: list[NotableDay] = []

    # --- Sleep score extremes ---
    sleep_days = [
        (f["date"], f["sleep_score"])
        for f in features_list
        if f.get("sleep_score") is not None
    ]
    if len(sleep_days) >= 2:
        best = max(sleep_days, key=lambda x: x[1])
        worst = min(sleep_days, key=lambda x: x[1])
        candidates.append(NotableDay(
            date=best[0],
            description=f"Best sleep score: {best[1]}",
            metric="sleep_score",
            value=float(best[1]),
        ))
        candidates.append(NotableDay(
            date=worst[0],
            description=f"Worst sleep score: {worst[1]}",
            metric="sleep_score",
            value=float(worst[1]),
        ))

    # --- HRV extremes ---
    hrv_days = [
        (f["date"], f["hrv_overnight_avg"])
        for f in features_list
        if f.get("hrv_overnight_avg") is not None
    ]
    if len(hrv_days) >= 2:
        best_hrv = max(hrv_days, key=lambda x: x[1])
        candidates.append(NotableDay(
            date=best_hrv[0],
            description=f"Highest HRV: {best_hrv[1]:.0f} ms",
            metric="hrv_overnight_avg",
            value=float(best_hrv[1]),
        ))

    # --- Body battery extremes ---
    bb_days = [
        (f["date"], f["bb_wakeup"])
        for f in features_list
        if f.get("bb_wakeup") is not None
    ]
    if len(bb_days) >= 2:
        best_bb = max(bb_days, key=lambda x: x[1])
        candidates.append(NotableDay(
            date=best_bb[0],
            description=f"Highest body battery at wake: {best_bb[1]}",
            metric="bb_wakeup",
            value=float(best_bb[1]),
        ))

    # --- Resting HR extremes (lower is better) ---
    rhr_days = [
        (f["date"], f["resting_hr"])
        for f in features_list
        if f.get("resting_hr") is not None
    ]
    if len(rhr_days) >= 2:
        best_rhr = min(rhr_days, key=lambda x: x[1])
        candidates.append(NotableDay(
            date=best_rhr[0],
            description=f"Lowest resting HR: {best_rhr[1]} bpm",
            metric="resting_hr",
            value=float(best_rhr[1]),
        ))

    # Deduplicate by date (keep first occurrence if same date appears for
    # multiple metrics)
    seen_dates: set[str] = set()
    unique: list[NotableDay] = []
    for c in candidates:
        if c.date not in seen_dates:
            seen_dates.add(c.date)
            unique.append(c)

    return unique[:5]
