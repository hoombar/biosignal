"""Tests for core settings parsing."""

from app.core.config import Settings


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Unknown env vars should not cause validation failure."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setenv("HABITSYNC_URL", "http://habitsync:6842")
    monkeypatch.setenv("HABITSYNC_API_KEY", "key")
    monkeypatch.setenv("BIOSIGNAL_DATA_DIR", "/home/ben/docker/biosignal/data")

    settings = Settings(_env_file=None)

    assert settings.garmin_email == "user@example.com"
    assert settings.habitsync_url == "http://habitsync:6842"
