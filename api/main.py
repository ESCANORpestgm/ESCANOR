"""FastAPI application entrypoint for the ESCANOR rooftop-PV platform.

Routes are organized by domain under ``api/routers``.
Static configuration lives in ``api/config.py``; runtime state, the forecast
pipeline, and the background scheduler live in ``api/services.py``.

Run:
    uvicorn api.main:app --reload --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.services import lifespan
from api.routers.alerts import router as alerts_router
from api.routers.metrics import router as diagnostics_router
from api.routers.forecast import router as forecast_router
from api.routers.learning import router as learning_router
from api.routers.meta import router as meta_router
from api.routers.reports import router as reports_router
from api.routers.spatial import router as spatial_router, grid_router

app = FastAPI(
    title="STEG ESCANOR PV Forecast Platform API",
    description=(
        "National rooftop PV production forecasting for STEG — intra-day to D+3, "
        "across 50 commercial districts and 7 Directions de Distribution."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ────────────────────────────────────────────────────────────

app.include_router(meta_router)
app.include_router(forecast_router)
app.include_router(spatial_router)
app.include_router(grid_router)
app.include_router(alerts_router)
app.include_router(diagnostics_router)
app.include_router(learning_router)
app.include_router(reports_router)

# ── Serve the dashboard from the API itself ─────────────────────────────────
# Mounted after every router and under its own explicit prefix, so no static path
# can ever shadow an API route (Starlette matches routes in declaration order and
# a mount only claims what is beneath "/dashboard"). The directory is resolved
# from this file rather than the working directory, so uvicorn can be started
# from anywhere; html=True makes /dashboard/ return index.html directly.
#
# This is what lets a single public URL serve both halves of the platform: the
# frontend calls the API with relative URLs, so it works identically on
# http://127.0.0.1:8000/dashboard/ and on a Cloudflare quick tunnel whose host
# changes every restart.
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
