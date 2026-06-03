"""Gym template and session logging API."""
from __future__ import annotations

from datetime import date as DateType, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import (
    GymSessionActivityLog,
    GymSessionLog,
    GymSessionTemplate,
    GymTemplateActivity,
)
from app.schemas.responses import (
    GymSessionActivityResponse,
    GymSessionActivityUpdateRequest,
    GymSessionCreateRequest,
    GymSessionResponse,
    GymSessionUpdateRequest,
    GymTemplateActivityInput,
    GymTemplateActivityResponse,
    GymTemplateCreateRequest,
    GymTemplateResponse,
    GymTemplateUpdateRequest,
)


router = APIRouter(prefix="/api/gym", tags=["gym"])


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def _load_template(db: AsyncSession, template_id: int) -> GymSessionTemplate:
    template = (await db.execute(
        select(GymSessionTemplate).where(GymSessionTemplate.id == template_id)
    )).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail=f"gym template {template_id} not found")
    return template


async def _template_activities(db: AsyncSession, template_id: int) -> list[GymTemplateActivity]:
    return list((await db.execute(
        select(GymTemplateActivity)
        .where(GymTemplateActivity.template_id == template_id)
        .order_by(GymTemplateActivity.sort_order)
    )).scalars().all())


async def _session_activities(db: AsyncSession, session_id: int) -> list[GymSessionActivityLog]:
    return list((await db.execute(
        select(GymSessionActivityLog)
        .where(GymSessionActivityLog.session_log_id == session_id)
        .order_by(GymSessionActivityLog.sort_order)
    )).scalars().all())


def _template_activity_response(activity: GymTemplateActivity) -> GymTemplateActivityResponse:
    return GymTemplateActivityResponse(
        id=activity.id,
        sort_order=activity.sort_order,
        activity_type=activity.activity_type,
        name=activity.name,
        target_sets=activity.target_sets,
        target_reps=activity.target_reps,
        target_weight=activity.target_weight,
        target_weight_unit=activity.target_weight_unit,
        target_duration_minutes=activity.target_duration_minutes,
        target_intensity=activity.target_intensity,
        target_speed=activity.target_speed,
        notes=activity.notes,
    )


async def _template_response(db: AsyncSession, template: GymSessionTemplate) -> GymTemplateResponse:
    activities = await _template_activities(db, template.id)
    return GymTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        archived=template.archived_at is not None,
        created_at=template.created_at,
        updated_at=template.updated_at,
        activities=[_template_activity_response(activity) for activity in activities],
    )


def _activity_response(activity: GymSessionActivityLog) -> GymSessionActivityResponse:
    return GymSessionActivityResponse(
        id=activity.id,
        sort_order=activity.sort_order,
        activity_type=activity.activity_type,
        name_snapshot=activity.name_snapshot,
        planned_sets=activity.planned_sets,
        planned_reps=activity.planned_reps,
        planned_weight=activity.planned_weight,
        planned_weight_unit=activity.planned_weight_unit,
        planned_duration_minutes=activity.planned_duration_minutes,
        planned_intensity=activity.planned_intensity,
        planned_speed=activity.planned_speed,
        planned_notes=activity.planned_notes,
        actual_sets=activity.actual_sets,
        actual_reps=activity.actual_reps,
        actual_weight=activity.actual_weight,
        actual_weight_unit=activity.actual_weight_unit,
        actual_duration_minutes=activity.actual_duration_minutes,
        actual_intensity=activity.actual_intensity,
        actual_speed=activity.actual_speed,
        completed=activity.completed,
        rating=activity.rating,
        notes=activity.notes,
    )


async def _session_response(db: AsyncSession, session: GymSessionLog) -> GymSessionResponse:
    activities = await _session_activities(db, session.id)
    return GymSessionResponse(
        id=session.id,
        template_id=session.template_id,
        template_name_snapshot=session.template_name_snapshot,
        date=session.date,
        started_at=session.started_at,
        completed_at=session.completed_at,
        notes=session.notes,
        activities=[_activity_response(activity) for activity in activities],
    )


def _apply_template_activity(row: GymTemplateActivity, data: GymTemplateActivityInput, sort_order: int) -> None:
    row.sort_order = sort_order
    row.activity_type = data.activity_type
    row.name = data.name.strip()
    row.target_sets = data.target_sets
    row.target_reps = data.target_reps
    row.target_weight = data.target_weight
    row.target_weight_unit = _clean_text(data.target_weight_unit)
    row.target_duration_minutes = data.target_duration_minutes
    row.target_intensity = _clean_text(data.target_intensity)
    row.target_speed = data.target_speed
    row.notes = _clean_text(data.notes)


async def _replace_template_activities(
    db: AsyncSession,
    template_id: int,
    activities: list[GymTemplateActivityInput],
) -> None:
    await db.execute(delete(GymTemplateActivity).where(GymTemplateActivity.template_id == template_id))
    for index, activity_data in enumerate(activities):
        activity = GymTemplateActivity(template_id=template_id)
        _apply_template_activity(activity, activity_data, index)
        db.add(activity)


@router.get("/templates", response_model=list[GymTemplateResponse])
async def list_templates(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(GymSessionTemplate)
    if not include_archived:
        stmt = stmt.where(GymSessionTemplate.archived_at.is_(None))
    templates = list((await db.execute(stmt.order_by(GymSessionTemplate.name))).scalars().all())
    return [await _template_response(db, template) for template in templates]


@router.post("/templates", response_model=GymTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(body: GymTemplateCreateRequest, db: AsyncSession = Depends(get_db)):
    template = GymSessionTemplate(
        name=body.name.strip(),
        description=_clean_text(body.description),
    )
    if not template.name:
        raise HTTPException(status_code=422, detail="template name must not be blank")
    db.add(template)
    try:
        await db.flush()
        await _replace_template_activities(db, template.id, body.activities)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym template name already exists") from exc
    return await _template_response(db, template)


@router.put("/templates/{template_id}", response_model=GymTemplateResponse)
async def update_template(
    template_id: int,
    body: GymTemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    template = await _load_template(db, template_id)
    template.name = body.name.strip()
    if not template.name:
        raise HTTPException(status_code=422, detail="template name must not be blank")
    template.description = _clean_text(body.description)
    template.updated_at = datetime.utcnow()
    try:
        await _replace_template_activities(db, template.id, body.activities)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym template update conflicts with existing data") from exc
    return await _template_response(db, template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await _load_template(db, template_id)
    template.archived_at = datetime.utcnow()
    template.updated_at = datetime.utcnow()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/templates/{template_id}/unarchive", response_model=GymTemplateResponse)
async def unarchive_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await _load_template(db, template_id)
    template.archived_at = None
    template.updated_at = datetime.utcnow()
    await db.commit()
    return await _template_response(db, template)


@router.get("/session", response_model=GymSessionResponse | None)
async def get_session(date: DateType, db: AsyncSession = Depends(get_db)):
    session = (await db.execute(
        select(GymSessionLog).where(GymSessionLog.date == date)
    )).scalar_one_or_none()
    if session is None:
        return None
    return await _session_response(db, session)


@router.post("/sessions", response_model=GymSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(body: GymSessionCreateRequest, db: AsyncSession = Depends(get_db)):
    template = await _load_template(db, body.template_id)
    if template.archived_at is not None:
        raise HTTPException(status_code=409, detail="cannot start archived gym template")
    activities = await _template_activities(db, template.id)
    session = GymSessionLog(
        template_id=template.id,
        template_name_snapshot=template.name,
        date=body.date,
    )
    db.add(session)
    try:
        await db.flush()
        for activity in activities:
            db.add(GymSessionActivityLog(
                session_log_id=session.id,
                sort_order=activity.sort_order,
                activity_type=activity.activity_type,
                name_snapshot=activity.name,
                planned_sets=activity.target_sets,
                planned_reps=activity.target_reps,
                planned_weight=activity.target_weight,
                planned_weight_unit=activity.target_weight_unit,
                planned_duration_minutes=activity.target_duration_minutes,
                planned_intensity=activity.target_intensity,
                planned_speed=activity.target_speed,
                planned_notes=activity.notes,
                actual_sets=activity.target_sets,
                actual_reps=activity.target_reps,
                actual_weight=activity.target_weight,
                actual_weight_unit=activity.target_weight_unit,
                actual_duration_minutes=activity.target_duration_minutes,
                actual_intensity=activity.target_intensity,
                actual_speed=activity.target_speed,
            ))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym session already exists for this date") from exc
    return await _session_response(db, session)


@router.put("/sessions/{session_id}", response_model=GymSessionResponse)
async def update_session(
    session_id: int,
    body: GymSessionUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    session = (await db.execute(
        select(GymSessionLog).where(GymSessionLog.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"gym session {session_id} not found")
    if body.notes is not None:
        session.notes = _clean_text(body.notes)
    if body.completed is not None:
        session.completed_at = datetime.utcnow() if body.completed else None
    await db.commit()
    return await _session_response(db, session)


@router.put("/session-activities/{activity_id}", response_model=GymSessionActivityResponse)
async def update_session_activity(
    activity_id: int,
    body: GymSessionActivityUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    activity = (await db.execute(
        select(GymSessionActivityLog).where(GymSessionActivityLog.id == activity_id)
    )).scalar_one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail=f"gym session activity {activity_id} not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(activity, field, _clean_text(value) if field in {"actual_weight_unit", "actual_intensity", "notes"} else value)
    await db.commit()
    return _activity_response(activity)
