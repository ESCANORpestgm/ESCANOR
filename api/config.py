"""Static configuration — artifact paths, domain lookups and authentication.

This module is a leaf dependency: it imports nothing from ``api.services`` or
``api.routers``, so every other API module can safely import from it.

Artifact locations are **re-exported** from :mod:`data.paths`, the platform's
single source of truth for on-disk locations: the routers keep importing them
from here, while the definitions (and the categorised ``results/`` layout) live
in one place only.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from data import paths
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP

# ── Paths (re-exported from data.paths) ──────────────────────────────────────

PROJECT_ROOT = paths.PROJECT_ROOT
MODEL_PATH = paths.MODEL_PATH
CALIBRATION_PATH = paths.CALIBRATION_PATH
METER_BUFFER = paths.METER_BUFFER_PATH
RETRAIN_LOG = paths.RETRAIN_LOG_PATH
RETRAIN_STATE_PATH = paths.RETRAIN_STATE_PATH
MEASUREMENTS_DIR = paths.MEASUREMENTS_DIR

# The API appends to the metering buffer and the retrain log, so the artifact
# root has to exist before the first request does.
paths.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

# ── Capacity & dust lookups ──────────────────────────────────────────────────

# Governorate-level and district-level lookups were merged into one mapping in
# ``data.steg_districts``; the aliases below keep the historical API names.
CAPACITY_LOOKUP: dict[str, float] = DISTRICT_CAPACITY_LOOKUP
DUST_LOOKUP: dict[str, float] = DISTRICT_DUST_LOOKUP

# ── Authentication ───────────────────────────────────────────────────────────

_API_KEY = os.environ.get("ESCANOR_API_KEY", "dev-key")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(_api_key_header)) -> str:
    """FastAPI dependency that validates the ``X-API-Key`` header."""
    if key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key header.")
    return key
