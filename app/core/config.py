from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    db_path: str = "/data/energy_tracker.db"

    # Garmin credentials
    garmin_email: str
    garmin_password: str
    garmin_token_dir: str = "/data/.garmin_tokens"

    # Optional settings
    tz: str = "Europe/London"
    sync_hour: int = 6
    sync_minute_garmin: int = 0
    sync_minute_environment: int = 5
    debug: bool = False

    # Optional location for environmental metrics
    environment_latitude: float | None = None
    environment_longitude: float | None = None

    @field_validator("environment_latitude", "environment_longitude", mode="before")
    @classmethod
    def blank_environment_location_is_unset(cls, value):
        if value == "":
            return None
        return value


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
