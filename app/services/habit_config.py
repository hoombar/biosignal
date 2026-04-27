"""Helpers for dynamic habit display configuration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Habit, HabitDisplayConfig


async def list_habit_display_entries(db: AsyncSession) -> list[dict]:
    """Return one display-config entry per active habit, sorted for UI use."""
    habits_result = await db.execute(
        select(Habit).where(Habit.archived_at.is_(None))
    )
    habits = list(habits_result.scalars().all())

    configs_result = await db.execute(select(HabitDisplayConfig))
    configs_by_name = {c.habit_name: c for c in configs_result.scalars().all()}

    entries = []
    for habit in habits:
        cfg = configs_by_name.get(habit.name)
        entries.append({
            "habit_name": habit.name,
            "display_name": cfg.display_name if cfg else None,
            "emoji": cfg.emoji if cfg else None,
            "color": cfg.color if cfg else None,
            "sort_order": cfg.sort_order if cfg else 0,
        })

    entries.sort(key=lambda e: (e["sort_order"], e["habit_name"]))
    return entries


async def list_ordered_habit_names(db: AsyncSession) -> list[str]:
    """Return known habit names in user-configured display order."""
    entries = await list_habit_display_entries(db)
    return [e["habit_name"] for e in entries]


async def get_default_habit_name(db: AsyncSession) -> str | None:
    """Return the first known habit in configured display order."""
    names = await list_ordered_habit_names(db)
    return names[0] if names else None
