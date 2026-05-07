from datetime import date
import pytest

from app.core.config import Settings
from app.services import scheduler as scheduler_module


def test_settings_parses_environment_sync_minute(monkeypatch):
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.delenv("SYNC_MINUTE_ENVIRONMENT", raising=False)

    settings = Settings(_env_file=None)

    assert settings.sync_minute_environment == 5


def test_scheduler_registers_garmin_and_environment_jobs(monkeypatch):
    class FakeScheduler:
        def __init__(self):
            self.jobs = []
            self.started = False

        def add_job(self, func, trigger, id, name, replace_existing):
            self.jobs.append(
                {
                    "func": func,
                    "trigger": trigger,
                    "id": id,
                    "name": name,
                    "replace_existing": replace_existing,
                }
            )

        def start(self):
            self.started = True

    fake_scheduler = FakeScheduler()
    settings = Settings(
        garmin_email="user@example.com",
        garmin_password="secret",
        sync_hour=7,
        sync_minute_garmin=12,
        sync_minute_environment=34,
        _env_file=None,
    )

    monkeypatch.setattr(scheduler_module, "scheduler", None)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", lambda: fake_scheduler)

    scheduler_module.start_scheduler()

    try:
        assert fake_scheduler.started is True
        assert [job["id"] for job in fake_scheduler.jobs] == ["daily_sync", "daily_environment_sync"]
        garmin_trigger = fake_scheduler.jobs[0]["trigger"]
        environment_trigger = fake_scheduler.jobs[1]["trigger"]
        assert str(garmin_trigger.fields[5]) == "7"
        assert str(garmin_trigger.fields[6]) == "12"
        assert str(environment_trigger.fields[5]) == "7"
        assert str(environment_trigger.fields[6]) == "34"
    finally:
        scheduler_module.scheduler = None


@pytest.mark.asyncio
async def test_run_scheduled_environment_sync_logs_result(monkeypatch, async_session):
    class FakeSessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return async_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSyncService:
        def __init__(self, garmin, timezone):
            pass

        async def run_daily_environment_sync(self, session):
            return {"date": "2026-05-06", "success": True, "errors": [], "counts": {"environmental_metrics": 4}}

    settings = Settings(garmin_email="user@example.com", garmin_password="secret", _env_file=None)

    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler_module, "async_session_maker", FakeSessionMaker())
    monkeypatch.setattr(scheduler_module, "SyncService", FakeSyncService)
    monkeypatch.setattr(scheduler_module, "GarminClient", lambda *args, **kwargs: object())

    await scheduler_module.run_scheduled_environment_sync()

    committed = await async_session.get(scheduler_module.SyncLog, 1)
    assert committed.sync_type == "environment"
    assert committed.date_synced == date(2026, 5, 6)
    assert committed.status == "success"
    assert committed.details["counts"]["environmental_metrics"] == 4
