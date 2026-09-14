"""
FastAPI application entry point.

Startup sequence:
  1. Load config/model.yaml        → app.state.config
  2. Load config/constraints.yaml  → app.state.constraints_config
  3. Load config/vehicles.yaml     → app.state.vehicles_config
  4. Initialize in-memory missions store

Run with:
  uvicorn harness.api.main:app --reload
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from harness.api.routes import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path, default: dict) -> dict:
    """Load a YAML file; return default dict if the file is absent or unreadable."""
    if path.exists():
        try:
            with path.open() as fh:
                data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else default
        except Exception as exc:
            logger.warning(f"Failed to load {path}: {exc}, using defaults")
    return default


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_dir = Path("config")

    app.state.config = _load_yaml(
        config_dir / "model.yaml",
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": None,
            "api_key": "sk-placeholder",
            "api_key_env": "OPENAI_API_KEY",
        },
    )

    app.state.constraints_config = _load_yaml(
        config_dir / "constraints.yaml",
        {
            "geofence_polygon": [],
            "max_alt_m": 120.0,
            "min_alt_m": 5.0,
            "require_rtl": True,
            "max_range_m": 5000.0,
        },
    )

    app.state.vehicles_config = _load_yaml(config_dir / "vehicles.yaml", {"fleet": []})

    app.state.missions = {}

    logger.info("PX4 AI Orchestration Harness — startup complete")
    yield
    logger.info("PX4 AI Orchestration Harness — shutdown")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


app = FastAPI(
    title="PX4 AI Orchestration Harness",
    description=(
        "AI harness that accepts natural-language mission intent, decomposes it "
        "into a validated multi-vehicle PX4 plan, enforces hard constraints "
        "deterministically, requires human authorization, and dispatches over "
        "ROS 2 / MAVLink 2 stubs against SITL."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)

# ---------------------------------------------------------------------------
# Static files (optional — directory may not exist in CI)
# ---------------------------------------------------------------------------

_static_dir = Path("harness/ui/static")
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ---------------------------------------------------------------------------
# Jinja2 UI routes
# ---------------------------------------------------------------------------

_templates_dir = Path("harness/ui/templates")
templates = Jinja2Templates(directory=str(_templates_dir))


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def ui_missions(request: Request):
    """Mission list dashboard."""
    missions = list(request.app.state.missions.values())
    return templates.TemplateResponse(
        "missions.html",
        {"request": request, "missions": missions},
    )


@app.get("/ui/authorize/{mission_id}", response_class=HTMLResponse, include_in_schema=False)
async def ui_authorize(mission_id: str, request: Request):
    """Human authorization screen for a specific mission."""
    missions = request.app.state.missions
    if mission_id not in missions:
        return HTMLResponse(
            "<html><body><h1>Mission not found</h1></body></html>",
            status_code=404,
        )
    return templates.TemplateResponse(
        "authorize.html",
        {"request": request, "mission": missions[mission_id], "mission_id": mission_id},
    )


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse(
        {
            "status": "ok",
            "service": "px4-ai-orchestration-harness",
            "version": "0.1.0",
            "docs": "/docs",
            "ui": "/ui",
        }
    )
