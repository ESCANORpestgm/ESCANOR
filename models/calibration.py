"""Uncertainty calibration artefacts: split-conformal correction and per-horizon
band scales, plus the JSON file that carries them to the API process.

Both quantities are *measured* on a held-out calibration window and persisted so
that the dashboard reports the same uncertainty the retraining job validated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.io import read_json, write_json_atomic
from data.paths import CALIBRATION_PATH
from ingestion.synthetic_data import HORIZON_BUCKETS
from models.features import add_time_features
from models.inference import (
    FORECAST_P10_COLUMN,
    FORECAST_P50_COLUMN,
    FORECAST_P90_COLUMN,
    predict,
)

# Shape of the persisted calibration document.
CONFORMAL_KEY = "conformal_q"
HORIZON_SCALES_KEY = "horizon_scales"
EMPTY_CALIBRATION: dict[str, Any] = {CONFORMAL_KEY: 0.0, HORIZON_SCALES_KEY: {}}

# A horizon bucket needs this many daylight samples before its residual RMSE is
# trusted; below that the band is left untouched.
MIN_CALIBRATION_SAMPLES_PER_BUCKET = 10
# Only daytime rows carry information about forecast error.
MIN_DAYLIGHT_PRODUCTION_MW = 0.01
# Minimum mean predicted half-width for a scale to be meaningful.
MIN_HALF_WIDTH_MW = 0.001
# Maximum horizon scale factor — prevents absurdly wide uncertainty bands when
# the raw quantile spread is much narrower than the actual residuals. 1.5 allows
# modest widening for longer horizons without tripling the band.
MAX_HORIZON_SCALE = 1.5


def conformal_calibrate(
    models: dict,
    df_cal: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
    target_alpha: float = 0.2,
) -> float:
    """Split-conformal calibration: compute the nonconformity correction q_hat.

    Returns a scalar to add to the prediction half-width so that the resulting
    P10–P90 interval achieves approximate (1 - alpha) coverage. Based on Lei et
    al. (2018) distribution-free prediction intervals.
    """
    preds = predict(models, df_cal, capacity_lookup, dust_lookup)
    actual = preds["production_mw"].values
    # Nonconformity score: how far actual falls outside the predicted interval.
    scores = np.maximum(
        preds[FORECAST_P10_COLUMN].values - actual,
        actual - preds[FORECAST_P90_COLUMN].values,
    )
    n = len(scores)
    if n == 0:
        return 0.0
    q_level = min(np.ceil((1 - target_alpha) * (n + 1)) / n, 1.0)
    return max(0.0, float(np.quantile(scores, q_level)))


def calibrate_horizon_scales(
    models: dict,
    df_cal: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
) -> dict[str, float]:
    """Compute per-horizon-bucket scaling factors from calibration residuals.

    For each bucket, the ratio of actual RMSE to predicted half-width gives the
    correction factor. Buckets where bands are already wide enough (ratio ≤ 1.0)
    are left at 1.0 (no shrinking), and all factors are capped at
    ``MAX_HORIZON_SCALE``.
    """
    feat_df = add_time_features(df_cal, capacity_lookup, dust_lookup)
    preds = predict(models, df_cal, capacity_lookup, dust_lookup)
    actual = preds["production_mw"].values
    p50 = preds[FORECAST_P50_COLUMN].values
    band = preds[FORECAST_P90_COLUMN].values - preds[FORECAST_P10_COLUMN].values
    horizons = feat_df["horizon_hours"].values

    scales: dict[str, float] = {}
    for name, lo, hi in HORIZON_BUCKETS:
        mask = (horizons >= lo) & (horizons < hi) & (actual > MIN_DAYLIGHT_PRODUCTION_MW)
        if mask.sum() < MIN_CALIBRATION_SAMPLES_PER_BUCKET:
            scales[name] = 1.0
            continue
        residual_rmse = float(np.sqrt(np.mean((actual[mask] - p50[mask]) ** 2)))
        predicted_hw = float(np.mean(band[mask] / 2))
        if predicted_hw > MIN_HALF_WIDTH_MW:
            scales[name] = round(min(MAX_HORIZON_SCALE, max(1.0, residual_rmse / predicted_hw)), 3)
        else:
            scales[name] = 1.0
    return scales


def save_calibration(
    calibration: dict,
    path: str | Path | None = None,
) -> Path:
    """Persist the calibration document atomically."""
    return write_json_atomic(path or CALIBRATION_PATH, calibration)


def load_calibration(path: str | Path | None = None) -> dict:
    """Load the calibration document, or an empty one when it is not trained yet."""
    return read_json(path or CALIBRATION_PATH, default=None) or dict(EMPTY_CALIBRATION)


__all__ = [
    "CALIBRATION_PATH",
    "CONFORMAL_KEY",
    "EMPTY_CALIBRATION",
    "HORIZON_SCALES_KEY",
    "MAX_HORIZON_SCALE",
    "calibrate_horizon_scales",
    "conformal_calibrate",
    "load_calibration",
    "save_calibration",
]
