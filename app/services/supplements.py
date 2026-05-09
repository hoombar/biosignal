"""Supplement group configuration and logging helpers."""

from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import DailyHabit, Habit, SupplementLog, SupplementPlanVersion


SUPPLEMENT_SLOTS = ("morning", "midday", "evening")
SUPPLEMENT_HABIT_SOURCE = "supplement_slot"


def validate_slot(slot: str) -> str:
    if slot not in SUPPLEMENT_SLOTS:
        raise HTTPException(status_code=404, detail=f"supplement slot {slot!r} not found")
    return slot


def supplement_habit_name(slot: str) -> str:
    validate_slot(slot)
    return f"supplements_{slot}"


def normalize_items(items: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    normalized: list[dict[str, str | None]] = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=422, detail="supplement item name is required")
        dose = item.get("dose")
        notes = item.get("notes")
        normalized.append({
            "name": name,
            "dose": str(dose).strip() if dose not in (None, "") else None,
            "notes": str(notes).strip() if notes not in (None, "") else None,
        })
    return normalized


async def get_active_plan(db: AsyncSession, slot: str) -> SupplementPlanVersion | None:
    validate_slot(slot)
    return (await db.execute(
        select(SupplementPlanVersion)
        .where(SupplementPlanVersion.slot == slot)
        .order_by(SupplementPlanVersion.version.desc())
        .limit(1)
    )).scalar_one_or_none()


async def list_active_plans(db: AsyncSession) -> list[dict]:
    slots = []
    for slot in SUPPLEMENT_SLOTS:
        plan = await get_active_plan(db, slot)
        slots.append({
            "slot": slot,
            "version": plan.version if plan else None,
            "items": plan.items if plan else [],
        })
    return slots


async def create_plan_version(
    db: AsyncSession,
    slot: str,
    items: list[dict[str, Any]],
) -> SupplementPlanVersion:
    validate_slot(slot)
    normalized = normalize_items(items)
    latest_version = (await db.execute(
        select(func.max(SupplementPlanVersion.version))
        .where(SupplementPlanVersion.slot == slot)
    )).scalar_one()
    plan = SupplementPlanVersion(
        slot=slot,
        version=(latest_version or 0) + 1,
        items=normalized,
        created_at=datetime.utcnow(),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def ensure_supplement_habit(db: AsyncSession, slot: str) -> Habit:
    name = supplement_habit_name(slot)
    habit = (await db.execute(select(Habit).where(Habit.name == name))).scalar_one_or_none()
    if habit is not None:
        if habit.source != SUPPLEMENT_HABIT_SOURCE:
            habit.source = SUPPLEMENT_HABIT_SOURCE
        if habit.habit_type != "binary":
            habit.habit_type = "binary"
        if habit.archived_at is not None:
            habit.archived_at = None
        await db.flush()
        return habit

    habit = Habit(
        name=name,
        habit_type="binary",
        source=SUPPLEMENT_HABIT_SOURCE,
    )
    db.add(habit)
    await db.flush()
    return habit


async def log_supplement_slot(
    db: AsyncSession,
    target_date: DateType,
    slot: str,
    completed: bool = True,
) -> SupplementLog:
    validate_slot(slot)
    plan = await get_active_plan(db, slot)
    if plan is None:
        plan = await create_plan_version(db, slot, [])

    stmt = insert(SupplementLog).values(
        date=target_date,
        slot=slot,
        plan_version_id=plan.id,
        completed=completed,
        snapshot=plan.items,
        completed_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "slot"],
        set_={
            "plan_version_id": stmt.excluded.plan_version_id,
            "completed": stmt.excluded.completed,
            "snapshot": stmt.excluded.snapshot,
            "completed_at": stmt.excluded.completed_at,
        },
    )
    await db.execute(stmt)

    habit = await ensure_supplement_habit(db, slot)
    daily_stmt = insert(DailyHabit).values(
        date=target_date,
        habit_id=habit.id,
        habit_value=1 if completed else 0,
    )
    daily_stmt = daily_stmt.on_conflict_do_update(
        index_elements=["date", "habit_id"],
        set_={"habit_value": daily_stmt.excluded.habit_value},
    )
    await db.execute(daily_stmt)
    await db.commit()

    return (await db.execute(
        select(SupplementLog).where(
            SupplementLog.date == target_date,
            SupplementLog.slot == slot,
        )
    )).scalar_one()


async def delete_supplement_log(
    db: AsyncSession,
    target_date: DateType,
    slot: str,
) -> None:
    validate_slot(slot)
    log = (await db.execute(
        select(SupplementLog).where(
            SupplementLog.date == target_date,
            SupplementLog.slot == slot,
        )
    )).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="no supplement log entry to delete")

    await db.delete(log)
    habit = (await db.execute(
        select(Habit).where(Habit.name == supplement_habit_name(slot))
    )).scalar_one_or_none()
    if habit is not None:
        await db.execute(delete(DailyHabit).where(
            DailyHabit.date == target_date,
            DailyHabit.habit_id == habit.id,
        ))
    await db.commit()

