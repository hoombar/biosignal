"""Tests for core settings parsing."""

from app.core.config import Settings


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Unknown env vars should not cause validation failure."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setenv("BIOSIGNAL_DATA_DIR", "/home/ben/docker/biosignal/data")

    settings = Settings(_env_file=None)

    assert settings.garmin_email == "user@example.com"


def test_settings_parses_environment_location(monkeypatch):
    """Optional location config should parse as floats for environmental metrics."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setenv("ENVIRONMENT_LATITUDE", "51.5074")
    monkeypatch.setenv("ENVIRONMENT_LONGITUDE", "-0.1278")

    settings = Settings(_env_file=None)

    assert settings.environment_latitude == 51.5074
    assert settings.environment_longitude == -0.1278


def test_settings_environment_location_defaults_to_unset(monkeypatch):
    """Environmental metrics should be opt-in when no location is configured."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.delenv("ENVIRONMENT_LATITUDE", raising=False)
    monkeypatch.delenv("ENVIRONMENT_LONGITUDE", raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment_latitude is None
    assert settings.environment_longitude is None
