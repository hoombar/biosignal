from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api", tags=["config"])


class HealthResponse(BaseModel):
    status: str
    version: str


class ConfigResponse(BaseModel):
    db_path: str
    garmin_token_dir: str
    habitsync_url: str
    tz: str
    sync_hour: int
    sync_minute_garmin: int
    sync_minute_habitsync: int
    debug: bool


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get current configuration (excluding secrets)."""
    settings = get_settings()
    return ConfigResponse(
        db_path=settings.db_path,
        garmin_token_dir=settings.garmin_token_dir,
        habitsync_url=settings.habitsync_url,
        tz=settings.tz,
        sync_hour=settings.sync_hour,
        sync_minute_garmin=settings.sync_minute_garmin,
        sync_minute_habitsync=settings.sync_minute_habitsync,
        debug=settings.debug,
    )
