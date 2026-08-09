"""Gym template and session logging API."""
from __future__ import annotations

from datetime import date as DateType, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import (
    GymActivity,
    GymSessionActivityLog,
    GymSessionLog,
    GymSessionTemplate,
    GymTemplateActivity,
)
from app.schemas.responses import (
    GymSessionActivityResponse,
    GymSessionActivityCreateRequest,
    GymSessionActivityUpdateRequest,
    GymSessionCreateRequest,
    GymSessionResponse,
    GymSessionUpdateRequest,
    GymActivityCreateRequest,
    GymActivityResponse,
    GymActivityUpdateRequest,
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


def _activity_type(value: str) -> str:
    return "mobility" if value == "reps" else value


async def _load_template(db: AsyncSession, template_id: int) -> GymSessionTemplate:
    template = (await db.execute(
        select(GymSessionTemplate).where(GymSessionTemplate.id == template_id)
    )).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail=f"gym template {template_id} not found")
    return template


async def _load_activity(db: AsyncSession, activity_id: int) -> GymActivity:
    activity = (await db.execute(
        select(GymActivity).where(GymActivity.id == activity_id)
    )).scalar_one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail=f"gym activity {activity_id} not found")
    return activity


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
        activity_id=activity.activity_id,
        sort_order=activity.sort_order,
        activity_type=_activity_type(activity.activity_type),
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
        activity_id=activity.activity_id,
        substitution_activity_id=activity.substitution_activity_id,
        sort_order=activity.sort_order,
        activity_type=_activity_type(activity.activity_type),
        name_snapshot=activity.name_snapshot,
        substitution_name_snapshot=activity.substitution_name_snapshot,
        substitution_activity_type=(
            _activity_type(activity.substitution_activity_type)
            if activity.substitution_activity_type else None
        ),
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


def _gym_activity_response(activity: GymActivity) -> GymActivityResponse:
    return GymActivityResponse(
        id=activity.id,
        archived=activity.archived_at is not None,
        activity_type=_activity_type(activity.activity_type),
        name=activity.name,
        target_sets=activity.target_sets,
        target_reps=activity.target_reps,
        target_weight=activity.target_weight,
        target_weight_unit=activity.target_weight_unit,
        target_duration_minutes=activity.target_duration_minutes,
        target_intensity=activity.target_intensity,
        target_speed=activity.target_speed,
        notes=activity.notes,
        created_at=activity.created_at,
        updated_at=activity.updated_at,
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


def _apply_gym_activity(row: GymActivity, data: GymActivityCreateRequest | GymActivityUpdateRequest) -> None:
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


def _apply_template_activity(row: GymTemplateActivity, data: GymTemplateActivityInput, sort_order: int) -> None:
    if data.activity_type is None or data.name is None:
        raise HTTPException(status_code=422, detail="activity_type and name are required")
    row.sort_order = sort_order
    row.activity_id = data.activity_id
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


def _activity_input_from_library(activity: GymActivity) -> GymTemplateActivityInput:
    return GymTemplateActivityInput(
        activity_id=activity.id,
        activity_type=_activity_type(activity.activity_type),
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


async def _resolve_template_activity(db: AsyncSession, data: GymTemplateActivityInput) -> GymTemplateActivityInput:
    if data.activity_id is None:
        return data
    activity = await _load_activity(db, data.activity_id)
    if activity.archived_at is not None:
        raise HTTPException(status_code=409, detail="cannot add archived gym activity")
    if data.activity_type is not None and data.name is not None:
        return data
    return _activity_input_from_library(activity)


async def _resolve_session_activity(db: AsyncSession, data: GymSessionActivityCreateRequest) -> GymTemplateActivityInput:
    if data.activity_id is not None:
        activity = await _load_activity(db, data.activity_id)
        if activity.archived_at is not None:
            raise HTTPException(status_code=409, detail="cannot add archived gym activity")
        return _activity_input_from_library(activity)
    inline = GymActivityCreateRequest(
        activity_type=data.activity_type,
        name=data.name,
        target_sets=data.target_sets,
        target_reps=data.target_reps,
        target_weight=data.target_weight,
        target_weight_unit=data.target_weight_unit,
        target_duration_minutes=data.target_duration_minutes,
        target_intensity=data.target_intensity,
        target_speed=data.target_speed,
        notes=data.notes,
    )
    activity_id = None
    if data.save_to_library:
        activity = (await db.execute(
            select(GymActivity).where(GymActivity.name == inline.name.strip())
        )).scalar_one_or_none()
        if activity is None:
            activity = GymActivity()
            _apply_gym_activity(activity, inline)
            db.add(activity)
            await db.flush()
        elif activity.archived_at is not None:
            raise HTTPException(status_code=409, detail="gym activity name belongs to an archived activity")
        activity_id = activity.id
    return GymTemplateActivityInput(
        activity_id=activity_id,
        activity_type=inline.activity_type,
        name=inline.name,
        target_sets=inline.target_sets,
        target_reps=inline.target_reps,
        target_weight=inline.target_weight,
        target_weight_unit=inline.target_weight_unit,
        target_duration_minutes=inline.target_duration_minutes,
        target_intensity=inline.target_intensity,
        target_speed=inline.target_speed,
        notes=inline.notes,
    )


def _new_session_activity(session_id: int, data: GymTemplateActivityInput, sort_order: int) -> GymSessionActivityLog:
    if data.activity_type is None or data.name is None:
        raise HTTPException(status_code=422, detail="activity_type and name are required")
    return GymSessionActivityLog(
        session_log_id=session_id,
        activity_id=data.activity_id,
        sort_order=sort_order,
        activity_type=data.activity_type,
        name_snapshot=data.name,
        planned_sets=data.target_sets,
        planned_reps=data.target_reps,
        planned_weight=data.target_weight,
        planned_weight_unit=data.target_weight_unit,
        planned_duration_minutes=data.target_duration_minutes,
        planned_intensity=data.target_intensity,
        planned_speed=data.target_speed,
        planned_notes=data.notes,
        actual_sets=data.target_sets,
        actual_reps=data.target_reps,
        actual_weight=data.target_weight,
        actual_weight_unit=data.target_weight_unit,
        actual_duration_minutes=data.target_duration_minutes,
        actual_intensity=data.target_intensity,
        actual_speed=data.target_speed,
    )


async def _replace_template_activities(
    db: AsyncSession,
    template_id: int,
    activities: list[GymTemplateActivityInput],
) -> None:
    await db.execute(delete(GymTemplateActivity).where(GymTemplateActivity.template_id == template_id))
    for index, activity_data in enumerate(activities):
        activity_data = await _resolve_template_activity(db, activity_data)
        if activity_data.activity_id is None:
            if activity_data.name is None:
                raise HTTPException(status_code=422, detail="activity name is required")
            library_activity = (await db.execute(
                select(GymActivity).where(GymActivity.name == activity_data.name.strip())
            )).scalar_one_or_none()
            if library_activity is None:
                library_activity = GymActivity()
                _apply_gym_activity(library_activity, GymActivityCreateRequest(**activity_data.model_dump()))
                db.add(library_activity)
                await db.flush()
            if library_activity.archived_at is None:
                activity_data.activity_id = library_activity.id
        activity = GymTemplateActivity(template_id=template_id)
        _apply_template_activity(activity, activity_data, index)
        db.add(activity)


@router.get("/activities", response_model=list[GymActivityResponse])
async def list_activities(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(GymActivity)
    if not include_archived:
        stmt = stmt.where(GymActivity.archived_at.is_(None))
    rows = list((await db.execute(stmt.order_by(GymActivity.name))).scalars().all())
    return [_gym_activity_response(row) for row in rows]


@router.post("/activities", response_model=GymActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(body: GymActivityCreateRequest, db: AsyncSession = Depends(get_db)):
    activity = GymActivity()
    _apply_gym_activity(activity, body)
    if not activity.name:
        raise HTTPException(status_code=422, detail="activity name must not be blank")
    db.add(activity)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym activity name already exists") from exc
    return _gym_activity_response(activity)


@router.put("/activities/{activity_id}", response_model=GymActivityResponse)
async def update_activity(activity_id: int, body: GymActivityUpdateRequest, db: AsyncSession = Depends(get_db)):
    activity = await _load_activity(db, activity_id)
    _apply_gym_activity(activity, body)
    activity.updated_at = datetime.utcnow()
    if not activity.name:
        raise HTTPException(status_code=422, detail="activity name must not be blank")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym activity update conflicts with existing data") from exc
    return _gym_activity_response(activity)


@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_activity(activity_id: int, db: AsyncSession = Depends(get_db)):
    activity = await _load_activity(db, activity_id)
    activity.archived_at = datetime.utcnow()
    activity.updated_at = datetime.utcnow()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
            db.add(_new_session_activity(
                session.id,
                GymTemplateActivityInput(
                    activity_id=activity.activity_id,
                    activity_type=_activity_type(activity.activity_type),
                    name=activity.name,
                    target_sets=activity.target_sets,
                    target_reps=activity.target_reps,
                    target_weight=activity.target_weight,
                    target_weight_unit=activity.target_weight_unit,
                    target_duration_minutes=activity.target_duration_minutes,
                    target_intensity=activity.target_intensity,
                    target_speed=activity.target_speed,
                    notes=activity.notes,
                ),
                activity.sort_order,
            ))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym session already exists for this date") from exc
    return await _session_response(db, session)


@router.post("/sessions/{session_id}/activities", response_model=GymSessionActivityResponse, status_code=status.HTTP_201_CREATED)
async def add_session_activity(
    session_id: int,
    body: GymSessionActivityCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    session = (await db.execute(
        select(GymSessionLog).where(GymSessionLog.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"gym session {session_id} not found")
    sort_order = (await db.execute(
        select(func.max(GymSessionActivityLog.sort_order))
        .where(GymSessionActivityLog.session_log_id == session_id)
    )).scalar_one()
    activity_data = await _resolve_session_activity(db, body)
    activity = _new_session_activity(session.id, activity_data, 0 if sort_order is None else sort_order + 1)
    db.add(activity)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="gym session activity already exists at this order") from exc
    return _activity_response(activity)


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


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = (await db.execute(
        select(GymSessionLog).where(GymSessionLog.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"gym session {session_id} not found")
    await db.execute(delete(GymSessionActivityLog).where(GymSessionActivityLog.session_log_id == session_id))
    await db.delete(session)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    await db.flush()
    await _auto_finish_session(db, activity.session_log_id)
    await db.commit()
    return _activity_response(activity)


async def _auto_finish_session(db: AsyncSession, session_id: int) -> None:
    remaining = (await db.execute(
        select(func.count(GymSessionActivityLog.id)).where(
            GymSessionActivityLog.session_log_id == session_id,
            (GymSessionActivityLog.completed.is_(False)) | (GymSessionActivityLog.rating.is_(None)),
        )
    )).scalar_one()
    total = (await db.execute(
        select(func.count(GymSessionActivityLog.id)).where(
            GymSessionActivityLog.session_log_id == session_id,
        )
    )).scalar_one()
    if total and remaining == 0:
        session = (await db.execute(
            select(GymSessionLog).where(GymSessionLog.id == session_id)
        )).scalar_one()
        if session.completed_at is None:
            session.completed_at = datetime.utcnow()


@router.put(
    "/session-activities/{activity_id}/substitution",
    response_model=GymSessionActivityResponse,
)
async def substitute_session_activity(
    activity_id: int,
    body: GymSessionActivityCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    activity = (await db.execute(
        select(GymSessionActivityLog).where(GymSessionActivityLog.id == activity_id)
    )).scalar_one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail=f"gym session activity {activity_id} not found")

    substitute = await _resolve_session_activity(db, body)
    activity.substitution_activity_id = substitute.activity_id
    activity.substitution_name_snapshot = substitute.name
    activity.substitution_activity_type = substitute.activity_type
    activity.actual_sets = substitute.target_sets
    activity.actual_reps = substitute.target_reps
    activity.actual_weight = substitute.target_weight
    activity.actual_weight_unit = substitute.target_weight_unit
    activity.actual_duration_minutes = substitute.target_duration_minutes
    activity.actual_intensity = substitute.target_intensity
    activity.actual_speed = substitute.target_speed
    activity.completed = False
    activity.rating = None
    await db.commit()
    return _activity_response(activity)
