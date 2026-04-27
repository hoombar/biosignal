"""Native habit logging API.

Endpoints biosignal exposes for logging habits directly (no external
HabitSync round-trip). Backed by the canonical ``habits`` and
``daily_habits`` tables introduced in migration ``c4e2a1f9b3d7``.
"""
from __future__ import annotations

import re
from datetime import date as DateType, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import DailyHabit, Habit, HabitDisplayConfig
from app.schemas.responses import (
    HabitCreateRequest,
    HabitListEntry,
    HabitLogEntry,
    HabitLogUpdate,
    HabitUpdateRequest,
)


def _normalize_slug(name: str) -> str:
    """Normalize a habit name to snake_case (matches HabitSync's rule)."""
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return normalized.strip("_")


router = APIRouter(prefix="/api/habits", tags=["habits"])


@router.get("/list", response_model=list[HabitListEntry])
async def list_habits(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Return all habits with their display config attached.

    By default only active habits are returned. Pass ``include_archived=true``
    to include archived ones (kept so historical correlations can still
    surface their old data).
    """
    stmt = select(Habit)
    if not include_archived:
        stmt = stmt.where(Habit.archived_at.is_(None))
    habits = (await db.execute(stmt)).scalars().all()

    configs = (await db.execute(select(HabitDisplayConfig))).scalars().all()
    cfg_by_name = {c.habit_name: c for c in configs}

    entries = []
    for habit in habits:
        cfg = cfg_by_name.get(habit.name)
        entries.append(HabitListEntry(
            id=habit.id,
            name=habit.name,
            habit_type=habit.habit_type,
            archived=habit.archived_at is not None,
            display_name=cfg.display_name if cfg else None,
            emoji=cfg.emoji if cfg else None,
            color=cfg.color if cfg else None,
            sort_order=cfg.sort_order if cfg else 0,
        ))

    entries.sort(key=lambda e: (e.sort_order, e.name))
    return entries


async def _load_habit(db: AsyncSession, habit_id: int) -> Habit:
    habit = (await db.execute(select(Habit).where(Habit.id == habit_id))).scalar_one_or_none()
    if habit is None:
        raise HTTPException(status_code=404, detail=f"habit {habit_id} not found")
    if habit.archived_at is not None:
        raise HTTPException(
            status_code=409,
            detail=f"habit {habit.name!r} is archived; unarchive before logging",
        )
    return habit


def _validate_value_for_type(value: int, habit_type: str) -> None:
    if habit_type == "binary" and value not in (0, 1):
        raise HTTPException(
            status_code=422,
            detail=f"binary habits accept value 0 or 1, got {value}",
        )


@router.put("/log/{target_date}/{habit_id}", response_model=HabitLogEntry)
async def log_habit(
    target_date: DateType,
    habit_id: int,
    body: HabitLogUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Set the logged value for ``habit_id`` on ``target_date``.

    Idempotent: a second PUT for the same (date, habit_id) overwrites.
    This is exactly the retrospective-edit case that motivated the rewrite.
    """
    habit = await _load_habit(db, habit_id)
    _validate_value_for_type(body.value, habit.habit_type)

    stmt = insert(DailyHabit).values(
        date=target_date,
        habit_id=habit.id,
        habit_value=body.value,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "habit_id"],
        set_={"habit_value": stmt.excluded.habit_value},
    )
    await db.execute(stmt)
    await db.commit()

    return HabitLogEntry(
        date=target_date.isoformat(),
        habit_id=habit.id,
        value=body.value,
    )


@router.delete("/log/{target_date}/{habit_id}", status_code=204)
async def delete_habit_log(
    target_date: DateType,
    habit_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove the daily log entry for ``habit_id`` on ``target_date``.

    Distinct from logging value=0 — this means "no entry recorded" so
    correlations exclude the day from this habit's series rather than
    counting it as a zero.
    """
    result = await db.execute(
        select(DailyHabit).where(
            DailyHabit.date == target_date,
            DailyHabit.habit_id == habit_id,
        )
    )
    daily = result.scalar_one_or_none()
    if daily is None:
        raise HTTPException(status_code=404, detail="no log entry to delete")
    await db.delete(daily)
    await db.commit()
    return None


async def _entry_for_habit(db: AsyncSession, habit: Habit) -> HabitListEntry:
    cfg = (await db.execute(
        select(HabitDisplayConfig).where(HabitDisplayConfig.habit_name == habit.name)
    )).scalar_one_or_none()
    return HabitListEntry(
        id=habit.id,
        name=habit.name,
        habit_type=habit.habit_type,
        archived=habit.archived_at is not None,
        display_name=cfg.display_name if cfg else None,
        emoji=cfg.emoji if cfg else None,
        color=cfg.color if cfg else None,
        sort_order=cfg.sort_order if cfg else 0,
    )


def _has_display_attrs(body: HabitCreateRequest | HabitUpdateRequest) -> bool:
    return any(
        v is not None
        for v in (body.display_name, body.emoji, body.color, body.sort_order)
    )


def _apply_display_config(
    cfg: HabitDisplayConfig, body: HabitCreateRequest | HabitUpdateRequest
) -> None:
    cfg.display_name = body.display_name
    cfg.emoji = body.emoji
    cfg.color = body.color.lower() if body.color else None
    if body.sort_order is not None:
        cfg.sort_order = body.sort_order


@router.post("", response_model=HabitListEntry, status_code=201)
async def create_habit(
    body: HabitCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new habit + (optional) display config in one shot."""
    name = _normalize_slug(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="habit name must contain alphanumerics")

    existing = (await db.execute(select(Habit).where(Habit.name == name))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"habit {name!r} already exists")

    habit = Habit(name=name, habit_type=body.habit_type)
    db.add(habit)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"habit {name!r} already exists")

    if _has_display_attrs(body):
        cfg = HabitDisplayConfig(habit_name=name)
        _apply_display_config(cfg, body)
        db.add(cfg)

    await db.commit()
    await db.refresh(habit)
    return await _entry_for_habit(db, habit)


@router.patch("/{habit_id}", response_model=HabitListEntry)
async def update_habit(
    habit_id: int,
    body: HabitUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a habit's display attributes (label/emoji/color/sort order).

    Habit type and the internal slug are immutable; archive and create a
    new habit if you need a different type.
    """
    habit = (await db.execute(select(Habit).where(Habit.id == habit_id))).scalar_one_or_none()
    if habit is None:
        raise HTTPException(status_code=404, detail=f"habit {habit_id} not found")

    cfg = (await db.execute(
        select(HabitDisplayConfig).where(HabitDisplayConfig.habit_name == habit.name)
    )).scalar_one_or_none()
    if cfg is None:
        cfg = HabitDisplayConfig(habit_name=habit.name)
        db.add(cfg)
    _apply_display_config(cfg, body)
    await db.commit()

    return await _entry_for_habit(db, habit)


@router.post("/{habit_id}/archive", response_model=HabitListEntry)
async def archive_habit(habit_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a habit archived. Historical data is preserved; the habit
    disappears from the daily logging UI but still appears in
    correlations / trends for past dates."""
    habit = (await db.execute(select(Habit).where(Habit.id == habit_id))).scalar_one_or_none()
    if habit is None:
        raise HTTPException(status_code=404, detail=f"habit {habit_id} not found")
    if habit.archived_at is None:
        habit.archived_at = datetime.utcnow()
        await db.commit()
    return await _entry_for_habit(db, habit)


@router.post("/{habit_id}/unarchive", response_model=HabitListEntry)
async def unarchive_habit(habit_id: int, db: AsyncSession = Depends(get_db)):
    habit = (await db.execute(select(Habit).where(Habit.id == habit_id))).scalar_one_or_none()
    if habit is None:
        raise HTTPException(status_code=404, detail=f"habit {habit_id} not found")
    if habit.archived_at is not None:
        habit.archived_at = None
        await db.commit()
    return await _entry_for_habit(db, habit)
