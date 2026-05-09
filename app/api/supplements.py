"""Supplement group configuration and logging API."""

from __future__ import annotations

from datetime import date as DateType

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import SupplementLog, SupplementPlanVersion
from app.services.supplements import (
    SUPPLEMENT_SLOTS,
    create_plan_version,
    delete_supplement_log,
    list_active_plans,
    log_supplement_slot,
    validate_slot,
)


router = APIRouter(prefix="/api/supplements", tags=["supplements"])


class SupplementItem(BaseModel):
    name: str
    dose: str | None = None
    notes: str | None = None


class SupplementSlotUpdate(BaseModel):
    items: list[SupplementItem] = []


class SupplementSlotResponse(BaseModel):
    slot: str
    version: int | None = None
    items: list[SupplementItem] = []


class SupplementConfigResponse(BaseModel):
    slots: list[SupplementSlotResponse]


class SupplementLogUpdate(BaseModel):
    completed: bool = True


class SupplementLogResponse(BaseModel):
    date: str
    slot: str
    completed: bool
    version: int
    snapshot: list[SupplementItem]


class SupplementLogsResponse(BaseModel):
    logs: list[SupplementLogResponse]


async def _log_response(db: AsyncSession, log: SupplementLog) -> SupplementLogResponse:
    version = (await db.execute(
        select(SupplementPlanVersion.version)
        .where(SupplementPlanVersion.id == log.plan_version_id)
    )).scalar_one()
    return SupplementLogResponse(
        date=log.date.isoformat(),
        slot=log.slot,
        completed=log.completed,
        version=version,
        snapshot=log.snapshot,
    )


@router.get("/config", response_model=SupplementConfigResponse)
async def get_config(db: AsyncSession = Depends(get_db)):
    return SupplementConfigResponse(slots=[
        SupplementSlotResponse(**slot)
        for slot in await list_active_plans(db)
    ])


@router.put("/slots/{slot}", response_model=SupplementSlotResponse)
async def put_slot(
    slot: str,
    body: SupplementSlotUpdate,
    db: AsyncSession = Depends(get_db),
):
    plan = await create_plan_version(
        db,
        validate_slot(slot),
        [item.model_dump() for item in body.items],
    )
    return SupplementSlotResponse(slot=plan.slot, version=plan.version, items=plan.items)


@router.get("/logs", response_model=SupplementLogsResponse)
async def get_logs(
    start: DateType = Query(...),
    end: DateType = Query(...),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SupplementLog)
        .where(SupplementLog.date >= start)
        .where(SupplementLog.date <= end)
        .order_by(SupplementLog.date, SupplementLog.slot)
    )).scalars().all()
    return SupplementLogsResponse(logs=[await _log_response(db, row) for row in rows])


@router.put("/log/{target_date}/{slot}", response_model=SupplementLogResponse)
async def put_log(
    target_date: DateType,
    slot: str,
    body: SupplementLogUpdate,
    db: AsyncSession = Depends(get_db),
):
    log = await log_supplement_slot(db, target_date, slot, body.completed)
    return await _log_response(db, log)


@router.delete("/log/{target_date}/{slot}", status_code=204)
async def delete_log(
    target_date: DateType,
    slot: str,
    db: AsyncSession = Depends(get_db),
):
    await delete_supplement_log(db, target_date, slot)
    return None
