"""Settings API endpoints for user preferences."""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import DailyHabit, HabitDisplayConfig
from app.schemas.responses import HabitDisplayConfigResponse, HabitDisplayConfigUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/habits", response_model=list[HabitDisplayConfigResponse])
async def get_habit_display_configs(db: AsyncSession = Depends(get_db)):
    """Return display config for all known habits.

    Habit names are sourced from distinct entries in daily_habits.
    Each entry includes any saved display config, or null defaults if not configured.
    Results are sorted by sort_order ascending, then habit_name.
    """
    # Get all distinct habit names ever synced
    names_result = await db.execute(
        select(distinct(DailyHabit.habit_name))
    )
    known_names = set(names_result.scalars().all())

    # Get all existing configs
    configs_result = await db.execute(
        select(HabitDisplayConfig)
    )
    configs_by_name = {c.habit_name: c for c in configs_result.scalars().all()}

    # Merge: every known habit gets an entry
    entries = []
    for name in known_names:
        if name in configs_by_name:
            cfg = configs_by_name[name]
            entries.append(HabitDisplayConfigResponse(
                habit_name=cfg.habit_name,
                display_name=cfg.display_name,
                emoji=cfg.emoji,
                sort_order=cfg.sort_order,
            ))
        else:
            entries.append(HabitDisplayConfigResponse(
                habit_name=name,
                display_name=None,
                emoji=None,
                sort_order=0,
            ))

    entries.sort(key=lambda e: (e.sort_order, e.habit_name))
    return entries


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
    if body.sort_order is not None:
        config.sort_order = body.sort_order

    await db.commit()
    await db.refresh(config)

    return HabitDisplayConfigResponse(
        habit_name=config.habit_name,
        display_name=config.display_name,
        emoji=config.emoji,
        sort_order=config.sort_order,
    )
