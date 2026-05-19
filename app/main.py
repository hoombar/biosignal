from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from jinja2 import Environment, FileSystemLoader

from app.api import (
    analysis,
    automation,
    config,
    context_events,
    daily,
    export,
    garmin_auth,
    habits,
    raw,
    settings,
    supplements,
    sync,
)
from app.core.version import APP_VERSION
from app.core.config import get_settings
from app.core.migrations import run_startup_migrations
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    # Startup
    settings = get_settings()
    if settings.auto_migrate_on_startup:
        await run_startup_migrations()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


# Create FastAPI application
app = FastAPI(
    title="Energy Correlation Tracker",
    description="Correlates Garmin biometric data with lifestyle habits",
    version=APP_VERSION,
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up templates (cache_size=0 avoids a Jinja2/Starlette bug where env globals
# become part of the LRU cache key as an unhashable dict)
_jinja_env = Environment(loader=FileSystemLoader("app/templates"), cache_size=0)
templates = Jinja2Templates(env=_jinja_env)

# Include routers
app.include_router(config.router)
app.include_router(context_events.router)
app.include_router(sync.router)
app.include_router(raw.router)
app.include_router(daily.router)
app.include_router(analysis.router)
app.include_router(export.router)
app.include_router(garmin_auth.router)
app.include_router(habits.router)
app.include_router(settings.router)
app.include_router(supplements.router)
app.include_router(automation.router)


# Page routes
@app.get("/")
async def root():
    """Redirect root to the daily log — the most-used page."""
    return RedirectResponse(url="/log")


@app.get("/log")
async def log_page(request: Request):
    """Focused single-day habit logging page (default landing)."""
    return templates.TemplateResponse(request, "log.html", {"active_page": "log"})


@app.get("/overview")
async def overview_page(request: Request):
    """Overview page."""
    return templates.TemplateResponse(request, "overview.html", {"active_page": "overview"})


@app.get("/daily")
async def daily_page(request: Request):
    """Daily view page."""
    return templates.TemplateResponse(request, "daily.html", {"active_page": "daily"})


@app.get("/correlations")
async def correlations_page(request: Request):
    """Correlations page."""
    return templates.TemplateResponse(request, "correlations.html", {"active_page": "correlations"})


@app.get("/trends")
async def trends_page(request: Request):
    """Trends page."""
    return templates.TemplateResponse(request, "trends.html", {"active_page": "trends"})


@app.get("/insights")
async def insights_page(request: Request):
    """Insights page."""
    return templates.TemplateResponse(request, "insights.html", {"active_page": "insights"})


@app.get("/settings")
async def settings_page(request: Request):
    """Habit display settings page."""
    return templates.TemplateResponse(request, "settings.html", {"active_page": "settings"})


@app.get("/setup/garmin")
async def garmin_setup_page(request: Request):
    """Garmin authentication setup page."""
    return templates.TemplateResponse(request, "garmin_setup.html", {"active_page": "setup"})
