"""Raw data API endpoints."""

from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.database import (
    HeartRateSample,
    BodyBatterySample,
    StressSample,
    HrvSample,
    Spo2Sample,
    StepsSample,
    SleepSession,
    Activity,
)
from app.schemas.responses import (
    TimeSeriesResponse,
    TimeSeriesPoint,
    SleepResponse,
    ActivityResponse,
)

router = APIRouter(prefix="/api/raw", tags=["raw"])


def _date_range(target_date: date) -> tuple[datetime, datetime]:
    """Get start and end datetime for a date."""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


@router.get("/heart_rate", response_model=TimeSeriesResponse)
async def get_heart_rate(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get heart rate samples for a specific date."""
    target_date = date.fromisoformat(date_param)
    start, end = _date_range(target_date)

    result = await db.execute(
        select(HeartRateSample)
        .where(HeartRateSample.timestamp >= start)
        .where(HeartRateSample.timestamp < end)
        .order_by(HeartRateSample.timestamp)
    )
    samples = result.scalars().all()

    points = [
        TimeSeriesPoint(timestamp=s.timestamp, value=float(s.heart_rate))
        for s in samples
    ]

    return TimeSeriesResponse(
        date=date_param,
        type="heart_rate",
        points=points
    )


@router.get("/body_battery", response_model=TimeSeriesResponse)
async def get_body_battery(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get body battery samples for a specific date."""
    target_date = date.fromisoformat(date_param)
    start, end = _date_range(target_date)

    result = await db.execute(
        select(BodyBatterySample)
        .where(BodyBatterySample.timestamp >= start)
        .where(BodyBatterySample.timestamp < end)
        .order_by(BodyBatterySample.timestamp)
    )
    samples = result.scalars().all()

    points = [
        TimeSeriesPoint(timestamp=s.timestamp, value=float(s.body_battery))
        for s in samples
    ]

    return TimeSeriesResponse(
        date=date_param,
        type="body_battery",
        points=points
    )


@router.get("/stress", response_model=TimeSeriesResponse)
async def get_stress(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get stress samples for a specific date."""
    target_date = date.fromisoformat(date_param)
    start, end = _date_range(target_date)

    result = await db.execute(
        select(StressSample)
        .where(StressSample.timestamp >= start)
        .where(StressSample.timestamp < end)
        .order_by(StressSample.timestamp)
    )
    samples = result.scalars().all()

    points = [
        TimeSeriesPoint(timestamp=s.timestamp, value=float(s.stress_level))
        for s in samples
    ]

    return TimeSeriesResponse(
        date=date_param,
        type="stress",
        points=points
    )


@router.get("/hrv", response_model=TimeSeriesResponse)
async def get_hrv(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get HRV samples for a specific date."""
    target_date = date.fromisoformat(date_param)
    start, end = _date_range(target_date)

    result = await db.execute(
        select(HrvSample)
        .where(HrvSample.timestamp >= start)
        .where(HrvSample.timestamp < end)
        .order_by(HrvSample.timestamp)
    )
    samples = result.scalars().all()

    points = [
        TimeSeriesPoint(timestamp=s.timestamp, value=s.hrv_value)
        for s in samples
    ]

    return TimeSeriesResponse(
        date=date_param,
        type="hrv",
        points=points
    )


@router.get("/spo2", response_model=TimeSeriesResponse)
async def get_spo2(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get SpO2 samples for a specific date."""
    target_date = date.fromisoformat(date_param)
    start, end = _date_range(target_date)

    result = await db.execute(
        select(Spo2Sample)
        .where(Spo2Sample.timestamp >= start)
        .where(Spo2Sample.timestamp < end)
        .order_by(Spo2Sample.timestamp)
    )
    samples = result.scalars().all()

    points = [
        TimeSeriesPoint(timestamp=s.timestamp, value=float(s.spo2_value))
        for s in samples
    ]

    return TimeSeriesResponse(
        date=date_param,
        type="spo2",
        points=points
    )


@router.get("/steps", response_model=TimeSeriesResponse)
async def get_steps(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get steps samples for a specific date."""
    target_date = date.fromisoformat(date_param)
    start, end = _date_range(target_date)

    result = await db.execute(
        select(StepsSample)
        .where(StepsSample.timestamp >= start)
        .where(StepsSample.timestamp < end)
        .order_by(StepsSample.timestamp)
    )
    samples = result.scalars().all()

    points = [
        TimeSeriesPoint(timestamp=s.timestamp, value=float(s.steps))
        for s in samples
    ]

    return TimeSeriesResponse(
        date=date_param,
        type="steps",
        points=points
    )


@router.get("/sleep", response_model=SleepResponse)
async def get_sleep(date_param: str, db: AsyncSession = Depends(get_db)):
    """Get sleep session for a specific date."""
    target_date = date.fromisoformat(date_param)

    result = await db.execute(
        select(SleepSession).where(SleepSession.date == target_date)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="No sleep data for this date")

    return SleepResponse.model_validate(session)


@router.get("/activities", response_model=list[ActivityResponse])
async def get_activities(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get activities for the last N days."""
    cutoff = datetime.now() - timedelta(days=days)

    result = await db.execute(
        select(Activity)
        .where(Activity.start_time >= cutoff)
        .order_by(Activity.start_time.desc())
    )
    activities = result.scalars().all()

    return [ActivityResponse.model_validate(a) for a in activities]
