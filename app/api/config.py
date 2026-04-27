from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_alembic_revision
from app.core.version import APP_VERSION

router = APIRouter(prefix="/api", tags=["config"])


class HealthResponse(BaseModel):
    status: str
    version: str
    db_revision: str | None


class ConfigResponse(BaseModel):
    app_version: str
    db_revision: str | None
    db_path: str
    garmin_token_dir: str
    tz: str
    sync_hour: int
    sync_minute_garmin: int
    debug: bool


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        db_revision=await get_alembic_revision(),
    )


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get current configuration (excluding secrets)."""
    settings = get_settings()
    db_revision = await get_alembic_revision()
    return ConfigResponse(
        app_version=APP_VERSION,
        db_revision=db_revision,
        db_path=settings.db_path,
        garmin_token_dir=settings.garmin_token_dir,
        tz=settings.tz,
        sync_hour=settings.sync_hour,
        sync_minute_garmin=settings.sync_minute_garmin,
        debug=settings.debug,
    )
