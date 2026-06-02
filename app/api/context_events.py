"""Context event API for logging non-baseline date ranges."""
from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import ContextEvent


ContextCategory = Literal[
    "travel",
    "conference",
    "illness",
    "stress",
    "vacation",
    "recovery",
    "other",
]
ContextIntensity = Literal["low", "medium", "high"]

router = APIRouter(prefix="/api/context-events", tags=["context-events"])


class ContextEventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    start_date: DateType
    end_date: DateType
    category: ContextCategory = "other"
    tags: list[str] = Field(default_factory=list)
    intensity: ContextIntensity | None = None
    exclude_from_baseline: bool = True
    notes: str | None = None

    @field_validator("title", "notes", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, value):
        if value is None:
            return []
        cleaned = []
        seen = set()
        for tag in value:
            normalized = str(tag).strip().lower().replace(" ", "_")
            if normalized and normalized not in seen:
                cleaned.append(normalized)
                seen.add(normalized)
        return cleaned

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ContextEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    start_date: DateType | None = None
    end_date: DateType | None = None
    category: ContextCategory | None = None
    tags: list[str] | None = None
    intensity: ContextIntensity | None = None
    exclude_from_baseline: bool | None = None
    notes: str | None = None

    @field_validator("title", "notes", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return ContextEventCreate.clean_optional_text(value)

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, value):
        return ContextEventCreate.clean_tags(value)


class ContextEventResponse(BaseModel):
    id: int
    title: str
    start_date: DateType
    end_date: DateType
    category: str
    tags: list[str] = []
    intensity: str | None = None
    exclude_from_baseline: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


async def _load_event(db: AsyncSession, event_id: int) -> ContextEvent:
    event = (await db.execute(
        select(ContextEvent).where(ContextEvent.id == event_id)
    )).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail=f"context event {event_id} not found")
    return event


@router.get("", response_model=list[ContextEventResponse])
async def list_context_events(
    start: DateType = Query(...),
    end: DateType = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return context events that overlap the requested date range."""
    if end < start:
        raise HTTPException(status_code=422, detail="end must be on or after start")

    rows = (await db.execute(
        select(ContextEvent)
        .where(ContextEvent.start_date <= end)
        .where(ContextEvent.end_date >= start)
        .order_by(ContextEvent.start_date, ContextEvent.id)
    )).scalars().all()
    return rows


@router.post("", response_model=ContextEventResponse, status_code=status.HTTP_201_CREATED)
async def create_context_event(
    body: ContextEventCreate,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    event = ContextEvent(
        title=body.title,
        start_date=body.start_date,
        end_date=body.end_date,
        category=body.category,
        tags=body.tags,
        intensity=body.intensity,
        exclude_from_baseline=body.exclude_from_baseline,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.patch("/{event_id}", response_model=ContextEventResponse)
async def update_context_event(
    event_id: int,
    body: ContextEventUpdate,
    db: AsyncSession = Depends(get_db),
):
    event = await _load_event(db, event_id)
    changes = body.model_dump(exclude_unset=True)

    start_date = changes.get("start_date", event.start_date)
    end_date = changes.get("end_date", event.end_date)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")

    for key, value in changes.items():
        setattr(event, key, value)
    event.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    event = await _load_event(db, event_id)
    await db.execute(delete(ContextEvent).where(ContextEvent.id == event.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
