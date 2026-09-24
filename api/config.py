"""Static configuration — paths, lookups, and authentication.

This module is a leaf dependency: it imports nothing from ``api.services``
or ``api.routers``, so every other module can safely import from it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

# Ensure project root is on sys.path for bare imports (data/, models/, …)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import (
    DISTRICT_CAPACITY_LOOKUP,
    DISTRICT_DUST_LOOKUP,
    GOVERNORATES,
)

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "artifacts" / "quantile_models.joblib"
CALIBRATION_PATH = ROOT / "results" / "calibration.json"
RESULTS_DIR = ROOT / "results"
METER_BUFFER = RESULTS_DIR / "metering_buffer.csv"
RETRAIN_LOG = RESULTS_DIR / "retrain_log.csv"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Capacity & dust lookups ──────────────────────────────────────────────────

CAPACITY_LOOKUP: dict[str, float] = {
    **{item.name: item.installed_capacity_mwc for item in GOVERNORATES},
    **DISTRICT_CAPACITY_LOOKUP,
}
DUST_LOOKUP: dict[str, float] = {
    **{item.name: item.dust_loss_pct for item in GOVERNORATES},
    **DISTRICT_DUST_LOOKUP,
}

# ── Authentication ───────────────────────────────────────────────────────────

_API_KEY = os.environ.get("ESCANOR_API_KEY", "dev-key")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(_api_key_header)) -> str:
    """FastAPI dependency that validates the ``X-API-Key`` header."""
    if key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key header.")
    return key
