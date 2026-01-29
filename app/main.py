from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.core.database import init_db
from app.api import config, sync, raw, daily, analysis, export
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    # Startup
    await init_db()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


# Create FastAPI application
app = FastAPI(
    title="Energy Correlation Tracker",
    description="Correlates Garmin biometric data with lifestyle habits",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(config.router)
app.include_router(sync.router)
app.include_router(raw.router)
app.include_router(daily.router)
app.include_router(analysis.router)
app.include_router(export.router)


# Page routes
@app.get("/")
async def root():
    """Redirect root to overview page."""
    return RedirectResponse(url="/overview")


@app.get("/overview")
async def overview_page(request: Request):
    """Overview page."""
    return templates.TemplateResponse("overview.html", {"request": request, "active_page": "overview"})


@app.get("/daily")
async def daily_page(request: Request):
    """Daily view page."""
    return templates.TemplateResponse("daily.html", {"request": request, "active_page": "daily"})


@app.get("/correlations")
async def correlations_page(request: Request):
    """Correlations page."""
    return templates.TemplateResponse("correlations.html", {"request": request, "active_page": "correlations"})


@app.get("/trends")
async def trends_page(request: Request):
    """Trends page."""
    return templates.TemplateResponse("trends.html", {"request": request, "active_page": "trends"})


@app.get("/insights")
async def insights_page(request: Request):
    """Insights page."""
    return templates.TemplateResponse("insights.html", {"request": request, "active_page": "insights"})
