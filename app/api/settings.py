"""Settings API endpoints for user preferences."""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.core.database import get_db
from app.models.database import AppSetting, HabitDisplayConfig
from app.schemas.responses import HabitDisplayConfigResponse, HabitDisplayConfigUpdate
from app.services.habit_config import list_habit_display_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

PREFERENCES_KEY = "preferences"


class UserPreferences(BaseModel):
    """User display preferences."""

    weather_temperature_unit: Literal["celsius", "fahrenheit"] = "celsius"
    weather_wind_speed_unit: Literal["kmh", "mph"] = "kmh"


def _preferences_from_value(value: dict | None) -> UserPreferences:
    if not isinstance(value, dict):
        return UserPreferences()
    return UserPreferences(**{**UserPreferences().model_dump(), **value})


@router.get("/preferences", response_model=UserPreferences)
async def get_preferences(db: AsyncSession = Depends(get_db)):
    """Return persisted user display preferences."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == PREFERENCES_KEY))
    setting = result.scalar_one_or_none()
    return _preferences_from_value(setting.value if setting else None)


@router.put("/preferences", response_model=UserPreferences)
async def put_preferences(
    body: UserPreferences,
    db: AsyncSession = Depends(get_db),
):
    """Persist user display preferences."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == PREFERENCES_KEY))
    setting = result.scalar_one_or_none()
    value = body.model_dump()

    if setting is None:
        setting = AppSetting(key=PREFERENCES_KEY, value=value)
        db.add(setting)
    else:
        setting.value = value

    await db.commit()
    return body


@router.get("/habits", response_model=list[HabitDisplayConfigResponse])
async def get_habit_display_configs(db: AsyncSession = Depends(get_db)):
    """Return display config for all known habits.

    Habit names are sourced from distinct entries in daily_habits.
    Each entry includes any saved display config, or null defaults if not configured.
    Results are sorted by sort_order ascending, then habit_name.
    """
    entries = await list_habit_display_entries(db)
    return [HabitDisplayConfigResponse(**entry) for entry in entries]


@router.put("/habits/{habit_name}", response_model=HabitDisplayConfigResponse)
async def upsert_habit_display_config(
    habit_name: str,
    body: HabitDisplayConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update the display config for a habit."""
    result = await db.execute(
        select(HabitDisplayConfig).where(HabitDisplayConfig.habit_name == habit_name)
    )
    config = result.scalar_one_or_none()

    if config is None:
        config = HabitDisplayConfig(habit_name=habit_name)
        db.add(config)

    config.display_name = body.display_name
    config.emoji = body.emoji
    config.color = body.color.lower() if body.color else None
    if body.sort_order is not None:
        config.sort_order = body.sort_order

    await db.commit()
    await db.refresh(config)

    return HabitDisplayConfigResponse(
        habit_name=config.habit_name,
        display_name=config.display_name,
        emoji=config.emoji,
        color=config.color,
        sort_order=config.sort_order,
    )
