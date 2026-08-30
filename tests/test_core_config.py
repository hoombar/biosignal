"""Tests for core settings parsing."""

from app.core.config import Settings


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Unknown env vars should not cause validation failure."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setenv("UNRELATED_SETTING", "ignored")

    settings = Settings(_env_file=None)

    assert settings.garmin_email == "user@example.com"


def test_settings_default_to_repository_data_directory(monkeypatch):
    """Direct runs should work without container-specific filesystem paths."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("GARMIN_TOKEN_DIR", raising=False)

    settings = Settings(_env_file=None)

    assert settings.db_path == "./data/energy_tracker.db"
    assert settings.garmin_token_dir == "./data/.garmin_tokens"


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


def test_settings_environment_location_blank_strings_are_unset(monkeypatch):
    """Copied .env.example blank location values should behave as unset."""
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setenv("ENVIRONMENT_LATITUDE", "")
    monkeypatch.setenv("ENVIRONMENT_LONGITUDE", "")

    settings = Settings(_env_file=None)

    assert settings.environment_latitude is None
    assert settings.environment_longitude is None
