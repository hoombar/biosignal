"""API endpoints for external automation writes."""

from __future__ import annotations

from datetime import date as DateType, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.habits import _validate_value_for_type
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.database import DailyHabit, Habit
from app.services.supplements import SUPPLEMENT_SLOTS, log_supplement_slot, validate_slot


router = APIRouter(prefix="/api/automation", tags=["automation"])


class AutomationLogRequest(BaseModel):
    target: str
    value: int | None = Field(default=None, ge=0)
    date: DateType | None = None


class AutomationLogResponse(BaseModel):
    target: str
    date: str
    value: int


def _require_automation_key(
    authorization: str | None,
    settings: Settings,
) -> None:
    expected = settings.automation_api_key
    if not expected:
        raise HTTPException(status_code=404, detail="automation API is not enabled")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid automation API token")


def _today_in_app_timezone(settings: Settings) -> DateType:
    return datetime.now(ZoneInfo(settings.tz)).date()


@router.post("/log", response_model=AutomationLogResponse)
async def log_from_automation(
    body: AutomationLogRequest,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_automation_key(authorization, settings)
    target_date = body.date or _today_in_app_timezone(settings)

    if body.target.startswith("supplement:"):
        slot = validate_slot(body.target.split(":", 1)[1])
        value = body.value if body.value is not None else 1
        if value not in (0, 1):
            raise HTTPException(status_code=422, detail="supplement targets accept value 0 or 1")
        await log_supplement_slot(db, target_date, slot, completed=bool(value))
        return AutomationLogResponse(
            target=f"supplement:{slot}",
            date=target_date.isoformat(),
            value=value,
        )

    if body.target.startswith("habit:"):
        habit_name = body.target.split(":", 1)[1]
        habit = (await db.execute(
            select(Habit).where(
                Habit.name == habit_name,
                Habit.archived_at.is_(None),
            )
        )).scalar_one_or_none()
        if habit is None:
            raise HTTPException(status_code=404, detail=f"habit {habit_name!r} not found")
        value = body.value if body.value is not None else 1
        _validate_value_for_type(value, habit.habit_type)

        stmt = insert(DailyHabit).values(
            date=target_date,
            habit_id=habit.id,
            habit_value=value,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "habit_id"],
            set_={"habit_value": stmt.excluded.habit_value},
        )
        await db.execute(stmt)
        await db.commit()
        return AutomationLogResponse(
            target=f"habit:{habit.name}",
            date=target_date.isoformat(),
            value=value,
        )

    allowed_supplements = ", ".join(f"supplement:{slot}" for slot in SUPPLEMENT_SLOTS)
    raise HTTPException(
        status_code=422,
        detail=f"target must be habit:<slug> or one of: {allowed_supplements}",
    )
