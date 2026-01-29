from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    db_path: str = "/data/energy_tracker.db"

    # Garmin credentials
    garmin_email: str
    garmin_password: str
    garmin_token_dir: str = "/data/.garmin_tokens"

    # HabitSync connection
    habitsync_url: str
    habitsync_api_key: str

    # Optional settings
    tz: str = "Europe/London"
    sync_hour: int = 6
    sync_minute_garmin: int = 0
    sync_minute_habitsync: int = 15
    debug: bool = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
