"""Tests for gym template and session logging API."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.gym import router
from app.core.database import get_db
from app.models.database import GymActivity, GymSessionActivityLog, GymSessionLog, GymSessionTemplate, GymTemplateActivity


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
    async def test_template_can_snapshot_library_activity(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            activity = client.post("/api/gym/activities", json={
                "activity_type": "strength",
                "name": "Chest press",
                "target_sets": 3,
                "target_reps": 10,
                "target_weight": 35,
                "target_weight_unit": "kg",
            }).json()
            resp = client.post("/api/gym/templates", json={
                "name": "Push day",
                "activities": [{"activity_id": activity["id"]}],
            })

        assert resp.status_code == 201
        row = resp.json()["activities"][0]
        assert row["activity_id"] == activity["id"]
        assert row["name"] == "Chest press"
        assert row["target_weight"] == 35


class TestGymActivities:

    @pytest.mark.asyncio
    async def test_create_list_update_and_archive_activity(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            create_resp = client.post("/api/gym/activities", json={
                "activity_type": "strength",
                "name": "Lat pulldown",
                "target_sets": 3,
                "target_reps": 12,
                "target_weight": 45,
                "target_weight_unit": "kg",
            })
            activity_id = create_resp.json()["id"]
            update_resp = client.put(f"/api/gym/activities/{activity_id}", json={
                "activity_type": "strength",
                "name": "Wide grip lat pulldown",
                "target_sets": 4,
                "target_reps": 10,
                "target_weight": 47.5,
                "target_weight_unit": "kg",
            })
            list_resp = client.get("/api/gym/activities")
            archive_resp = client.delete(f"/api/gym/activities/{activity_id}")
            default_after_archive = client.get("/api/gym/activities")
            archived_resp = client.get("/api/gym/activities", params={"include_archived": "true"})

        assert create_resp.status_code == 201
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Wide grip lat pulldown"
        assert update_resp.json()["target_sets"] == 4
        assert [row["name"] for row in list_resp.json()] == ["Wide grip lat pulldown"]
        assert archive_resp.status_code == 204
        assert default_after_archive.json() == []
        assert archived_resp.json()[0]["archived"] is True

        row = (await async_session.execute(select(GymActivity))).scalar_one()
        assert row.archived_at is not None


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
    async def test_template_activity_fields_are_normalized_by_type(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            resp = client.post("/api/gym/templates", json={
                "name": "Mixed plan",
                "activities": [
                    {
                        "activity_type": "strength",
                        "name": "Low row",
                        "target_sets": 3,
                        "target_reps": 12,
                        "target_weight": 50,
                        "target_weight_unit": "kg",
                        "target_duration_minutes": 8,
                        "target_intensity": "level 5",
                        "target_speed": 10,
                    },
                    {
                        "activity_type": "cardio",
                        "name": "Elliptical",
                        "target_sets": 3,
                        "target_reps": 12,
                        "target_weight": 50,
                        "target_weight_unit": "rpm",
                        "target_duration_minutes": 8,
                        "target_intensity": "level 5",
                        "target_speed": 5,
                    },
                    {
                        "activity_type": "mobility",
                        "name": "Stretch",
                        "target_sets": 3,
                        "target_reps": 12,
                        "target_weight": 50,
                        "target_weight_unit": "kg",
                        "target_duration_minutes": 5,
                        "target_intensity": "easy",
                        "target_speed": 5,
                        "notes": "ankle mobility focus",
                    },
                ],
            })

        assert resp.status_code == 201
        strength, cardio, mobility = resp.json()["activities"]
        assert strength["target_duration_minutes"] is None
        assert strength["target_intensity"] is None
        assert strength["target_speed"] is None
        assert cardio["target_sets"] is None
        assert cardio["target_reps"] is None
        assert cardio["target_weight"] is None
        assert cardio["target_weight_unit"] == "rpm"
        assert mobility["target_sets"] == 3
        assert mobility["target_reps"] == 12
        assert mobility["target_weight"] == 50
        assert mobility["target_weight_unit"] == "kg"
        assert mobility["target_duration_minutes"] is None
        assert mobility["target_intensity"] is None
        assert mobility["target_speed"] is None
        assert mobility["notes"] == "ankle mobility focus"

    @pytest.mark.asyncio
    async def test_freeform_activity_type_is_rejected(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            resp = client.post("/api/gym/templates", json={
                "name": "Old plan",
                "activities": [{"activity_type": "freeform", "name": "Stretch"}],
            })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reps_activity_type_is_rejected(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            resp = client.post("/api/gym/templates", json={
                "name": "Old reps plan",
                "activities": [{"activity_type": "reps", "name": "Dead bug", "target_reps": 10}],
            })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_legacy_reps_template_activity_is_returned_as_mobility(self, async_session):
        template = GymSessionTemplate(name="Legacy reps plan")
        async_session.add(template)
        await async_session.flush()
        async_session.add(GymTemplateActivity(
            template_id=template.id,
            sort_order=0,
            activity_type="reps",
            name="Dead bug",
            target_reps=10,
        ))
        await async_session.commit()

        app = _make_app(async_session)

        with TestClient(app) as client:
            resp = client.get("/api/gym/templates")

        assert resp.status_code == 200
        activity = resp.json()[0]["activities"][0]
        assert activity["activity_type"] == "mobility"
        assert activity["target_reps"] == 10

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

    @pytest.mark.asyncio
    async def test_unarchive_template_restores_it_to_default_list(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            created = client.post("/api/gym/templates", json=_template_payload()).json()
            client.delete(f"/api/gym/templates/{created['id']}")
            resp = client.post(f"/api/gym/templates/{created['id']}/unarchive")
            default_resp = client.get("/api/gym/templates")

        assert resp.status_code == 200
        assert resp.json()["archived"] is False
        assert [row["name"] for row in default_resp.json()] == ["Standard upper/back/arms"]


class TestGymSessions:

    @pytest.mark.asyncio
    async def test_add_library_activity_to_active_session_without_changing_template(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            activity = client.post("/api/gym/activities", json={
                "activity_type": "strength",
                "name": "Cable fly",
                "target_sets": 3,
                "target_reps": 12,
                "target_weight": 15,
                "target_weight_unit": "kg",
            }).json()
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            add_resp = client.post(
                f"/api/gym/sessions/{session['id']}/activities",
                json={"activity_id": activity["id"]},
            )
            template_resp = client.get("/api/gym/templates")

        assert add_resp.status_code == 201
        added = add_resp.json()
        assert added["activity_id"] == activity["id"]
        assert added["sort_order"] == 2
        assert added["name_snapshot"] == "Cable fly"
        assert added["actual_weight"] == 15
        assert [a["name"] for a in template_resp.json()[0]["activities"]] == ["Elliptical warm-up", "Low row"]

    @pytest.mark.asyncio
    async def test_add_inline_activity_to_active_session(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            resp = client.post(
                f"/api/gym/sessions/{session['id']}/activities",
                json={
                    "activity_type": "cardio",
                    "name": "Bike intervals",
                    "target_duration_minutes": 12,
                    "target_intensity": "level 7",
                    "target_speed": 90,
                    "target_weight_unit": "rpm",
                    "save_to_library": True,
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["activity_id"] is not None
        assert body["activity_type"] == "cardio"
        assert body["name_snapshot"] == "Bike intervals"
        assert body["actual_duration_minutes"] == 12

        library_row = (await async_session.execute(
            select(GymActivity).where(GymActivity.name == "Bike intervals")
        )).scalar_one()
        assert library_row.name == "Bike intervals"

    @pytest.mark.asyncio
    async def test_ad_hoc_activity_is_saved_for_later_by_default(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            added = client.post(
                f"/api/gym/sessions/{session['id']}/activities",
                json={
                    "activity_type": "strength",
                    "name": "Laid-back leg press",
                    "target_sets": 3,
                    "target_reps": 10,
                },
            )
            library = client.get("/api/gym/activities")

        assert added.status_code == 201
        assert added.json()["activity_id"] is not None
        assert "Laid-back leg press" in [activity["name"] for activity in library.json()]

    @pytest.mark.asyncio
    async def test_ad_hoc_mobility_activity_preserves_weight_and_notes(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            resp = client.post(
                f"/api/gym/sessions/{session['id']}/activities",
                json={
                    "activity_type": "mobility",
                    "name": "Kettlebell mason twist",
                    "target_sets": 3,
                    "target_reps": 10,
                    "target_weight": 12,
                    "target_weight_unit": "kg",
                    "notes": "very good",
                    "save_to_library": True,
                },
            )
            library = client.get("/api/gym/activities")

        assert resp.status_code == 201
        body = resp.json()
        assert body["activity_type"] == "mobility"
        assert body["name_snapshot"] == "Kettlebell mason twist"
        assert body["planned_sets"] == 3
        assert body["planned_reps"] == 10
        assert body["planned_weight"] == 12
        assert body["planned_weight_unit"] == "kg"
        assert body["planned_notes"] == "very good"
        assert body["actual_weight"] == 12

        library_row = (await async_session.execute(
            select(GymActivity).where(GymActivity.name == "Kettlebell mason twist")
        )).scalar_one()
        assert library_row.target_weight == 12
        assert library_row.target_weight_unit == "kg"
        assert library_row.notes == "very good"

    @pytest.mark.asyncio
    async def test_substitution_preserves_planned_activity_context(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            substitute = client.post("/api/gym/activities", json={
                "activity_type": "strength",
                "name": "Laid-back leg press",
                "target_sets": 3,
                "target_reps": 10,
                "target_weight": 80,
                "target_weight_unit": "kg",
            }).json()
            template = client.post("/api/gym/templates", json={
                "name": "Leg day",
                "activities": [{
                    "activity_type": "strength",
                    "name": "Leg press",
                    "target_sets": 4,
                    "target_reps": 8,
                    "target_weight": 100,
                    "target_weight_unit": "kg",
                }],
            }).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            planned = session["activities"][0]
            response = client.put(
                f"/api/gym/session-activities/{planned['id']}/substitution",
                json={"activity_id": substitute["id"]},
            )

        assert response.status_code == 200
        activity = response.json()
        assert activity["name_snapshot"] == "Leg press"
        assert activity["planned_weight"] == 100
        assert activity["substitution_activity_id"] == substitute["id"]
        assert activity["substitution_name_snapshot"] == "Laid-back leg press"
        assert activity["actual_weight"] == 80

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
                        {"activity_type": "mobility", "name": "Stretch"},
                    ],
                },
            )
            refetch_resp = client.get("/api/gym/session", params={"date": "2026-06-02"})

        assert session_resp.status_code == 201
        body = refetch_resp.json()
        assert body["template_name_snapshot"] == "Standard upper/back/arms"
        assert [a["name_snapshot"] for a in body["activities"]] == ["Elliptical warm-up", "Low row"]

    @pytest.mark.asyncio
    async def test_start_session_snapshots_mobility_sets_and_reps(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json={
                "name": "Mobility plan",
                "activities": [{
                    "activity_type": "mobility",
                    "name": "Hip airplanes",
                    "target_sets": 2,
                    "target_reps": 8,
                    "target_duration_minutes": 5,
                }],
            }).json()
            session_resp = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            )

        assert session_resp.status_code == 201
        activity = session_resp.json()["activities"][0]
        assert activity["planned_sets"] == 2
        assert activity["planned_reps"] == 8
        assert activity["actual_sets"] == 2
        assert activity["actual_reps"] == 8

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
    async def test_delete_session_removes_session_and_activity_logs(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            delete_resp = client.delete(f"/api/gym/sessions/{session['id']}")
            refetch_resp = client.get("/api/gym/session", params={"date": "2026-06-02"})

        assert delete_resp.status_code == 204
        assert refetch_resp.status_code == 200
        assert refetch_resp.json() is None

        sessions = (await async_session.execute(select(GymSessionLog))).scalars().all()
        activities = (await async_session.execute(select(GymSessionActivityLog))).scalars().all()
        assert sessions == []
        assert activities == []

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

    @pytest.mark.asyncio
    async def test_session_auto_finishes_only_when_all_activities_have_effort_ratings(self, async_session):
        app = _make_app(async_session)

        with TestClient(app) as client:
            template = client.post("/api/gym/templates", json=_template_payload()).json()
            session = client.post(
                "/api/gym/sessions",
                json={"date": "2026-06-02", "template_id": template["id"]},
            ).json()
            first, second = session["activities"]

            client.put(
                f"/api/gym/session-activities/{first['id']}",
                json={"completed": True, "rating": "normal"},
            )
            client.put(
                f"/api/gym/session-activities/{second['id']}",
                json={"completed": True},
            )
            before_rating = client.get("/api/gym/session", params={"date": "2026-06-02"})

            client.put(
                f"/api/gym/session-activities/{second['id']}",
                json={"rating": "hard"},
            )
            finished = client.get("/api/gym/session", params={"date": "2026-06-02"})

        assert before_rating.json()["completed_at"] is None
        assert finished.json()["completed_at"] is not None
