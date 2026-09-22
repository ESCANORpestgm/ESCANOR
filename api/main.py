"""FastAPI application entrypoint for the PréSol rooftop-PV platform.

Routes are organized by domain under ``api/routers``. Shared model, cache,
path, authentication, and lifecycle services live in ``api/core.py``.

Run:
    uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core import lifespan
from api.routers.diagnostics import router as diagnostics_router
from api.routers.forecast import grid_router, router as forecast_router
from api.routers.learning import router as learning_router
from api.routers.meta import router as meta_router
from api.routers.reports import router as reports_router

app = FastAPI(
    title="STEG PréSol PV Forecast Platform API",
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

app.include_router(meta_router)
app.include_router(forecast_router)
app.include_router(grid_router)
app.include_router(learning_router)
app.include_router(diagnostics_router)
app.include_router(reports_router)
