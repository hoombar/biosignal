"""Tests for gym template and session logging API."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.gym import router
from app.core.database import get_db
from app.models.database import GymSessionActivityLog, GymSessionLog, GymSessionTemplate


def _make_app(session):
    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _template_payload(name="Standard upper/back/arms"):
    return {
        "name": name,
        "description": "Current standard gym session",
        "activities": [
            {
                "activity_type": "cardio",
                "name": "Elliptical warm-up",
                "target_duration_minutes": 8,
                "target_intensity": "level 5",
            },
            {
                "activity_type": "strength",
                "name": "Low row",
                "target_sets": 3,
                "target_reps": 12,
                "target_weight": 50,
                "target_weight_unit": "kg",
            },
        ],
    }


class TestGymTemplates:

    @pytest.mark.asyncio
    async def test_create_and_list_template_with_ordered_activities(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            create_resp = client.post("/api/gym/templates", json=_template_payload())
            list_resp = client.get("/api/gym/templates")

        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["name"] == "Standard upper/back/arms"
        assert created["archived"] is False
        assert [a["name"] for a in created["activities"]] == ["Elliptical warm-up", "Low row"]

        assert list_resp.status_code == 200
        assert [row["name"] for row in list_resp.json()] == ["Standard upper/back/arms"]

    @pytest.mark.asyncio
    async def test_update_template_replaces_current_activity_plan(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            created = client.post("/api/gym/templates", json=_template_payload()).json()
            resp = client.put(
                f"/api/gym/templates/{created['id']}",
                json={
                    "name": "Upper pull",
                    "description": None,
                    "activities": [
                        {
                            "activity_type": "strength",
                            "name": "Shrugs",
                            "target_sets": 3,
                            "target_reps": 12,
                            "target_weight": 24,
                            "target_weight_unit": "kg",
                        }
                    ],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Upper pull"
        assert [a["name"] for a in body["activities"]] == ["Shrugs"]

    @pytest.mark.asyncio
    async def test_archive_template_excludes_it_by_default(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            created = client.post("/api/gym/templates", json=_template_payload()).json()
            archive_resp = client.delete(f"/api/gym/templates/{created['id']}")
            default_resp = client.get("/api/gym/templates")
            archived_resp = client.get("/api/gym/templates", params={"include_archived": "true"})

        assert archive_resp.status_code == 204
        assert default_resp.json() == []
        assert archived_resp.json()[0]["archived"] is True


class TestGymSessions:

    @pytest.mark.asyncio
    async def test_start_session_snapshots_current_template(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session_resp = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            )
            client.put(
                f"/api/gym/templates/{template['id']}",
                json={
                    "name": "Changed plan",
                    "description": None,
                    "activities": [
                        {"activity_type": "freeform", "name": "Stretch"},
                    ],
                },
            )
            refetch_resp = client.get("/api/gym/session", params={"date": "2026-06-02"})

        assert session_resp.status_code == 201
        body = refetch_resp.json()
        assert body["template_name_snapshot"] == "Standard upper/back/arms"
        assert [a["name_snapshot"] for a in body["activities"]] == ["Elliptical warm-up", "Low row"]

    @pytest.mark.asyncio
    async def test_one_session_per_date(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            first = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            )
            second = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            )

        assert first.status_code == 201
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_partial_activity_completion_and_actual_edits(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            low_row = session["activities"][1]
            resp = client.put(
                f"/api/gym/session-activities/{low_row['id']}",
                json={
                    "completed": True,
                    "rating": "hard",
                    "actual_sets": 3,
                    "actual_reps": 12,
                    "actual_weight": 52.5,
                    "notes": "Tough but achievable",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["completed"] is True
        assert body["rating"] == "hard"
        assert body["actual_weight"] == 52.5
        assert body["notes"] == "Tough but achievable"

        rows = (await async_session.execute(
            select(GymSessionActivityLog).order_by(GymSessionActivityLog.sort_order)
        )).scalars().all()
        assert [row.completed for row in rows] == [False, True]

    @pytest.mark.asyncio
    async def test_get_session_returns_empty_when_no_session_for_date(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            resp = client.get("/api/gym/session", params={"date": "2026-06-02"})

        assert resp.status_code == 200
        assert resp.json() is None

    @pytest.mark.asyncio
    async def test_finish_session_is_allowed_when_partial(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            resp = client.put(f"/api/gym/sessions/{session['id']}", json={"completed": True})

        assert resp.status_code == 200
        assert resp.json()["completed_at"] is not None

        row = (await async_session.execute(select(GymSessionLog))).scalar_one()
        assert row.date == date(2026, 6, 2)
        assert row.completed_at is not None
