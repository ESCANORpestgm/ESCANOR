"""Inference: turn a weather frame into a P10/P50/P90 forecast.

The band is built *symmetrically* around P50 (``p50 ± half_width``) rather than
by reading the three quantile models independently. LightGBM quantile regression
has no cross-quantile constraint, so raw P10/P50/P90 can cross on sparse
districts; the symmetric construction removes crossing by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.artifacts import FEATURE_COLUMNS_KEY
from models.features import add_time_features, get_feature_cols
from models.training_config import P10, P50, P90, QUANTILES

# Output columns, in the order the API and the dashboard expect them.
FORECAST_P10_COLUMN = "forecast_p10_mw"
FORECAST_P50_COLUMN = "forecast_p50_mw"
FORECAST_P90_COLUMN = "forecast_p90_mw"

# Minimum reported band half-width (MW) so a perfectly certain P50 still shows
# a non-degenerate interval downstream.
MIN_HALF_WIDTH_MW = 0.001
# Floor on how wide a band may grow relative to its own P50; also the absolute
# minimum applied at night so low-output hours keep a usable interval.
MIN_BAND_REFERENCE_MW = 0.5
# Fallback spreads used when a quantile model is missing from the bundle.
P10_MISSING_RATIO = 0.7
P90_MISSING_RATIO = 1.3
PRECISION_DIGITS = 4


def raw_predict(models: dict, feat_df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Average ensemble predictions per quantile."""
    feature_cols = models.get("_feature_cols") or get_feature_cols()
    available = [c for c in feature_cols if c in feat_df.columns]
    X = feat_df[available]
    raw: dict[str, np.ndarray] = {}
    for label in QUANTILES:
        model_list = models.get(label, [])
        if not model_list:
            continue
        preds = np.mean([m.predict(X) for m in model_list], axis=0)
        raw[label] = np.clip(preds, 0, None)
    return raw


def predict(
    models: dict,
    df: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
    conformal_q: float = 0.0,
    horizon_scales: dict | None = None,
) -> pd.DataFrame:
    """Return df with forecast_p10/p50/p90_mw columns added.

    Uses symmetric band construction (p50 ± half_width) to eliminate quantile
    crossing. ``conformal_q`` and ``horizon_scales`` are accepted for call-site
    compatibility with the calibration artefacts, but are deliberately *not*
    applied: as MW-based multipliers they inflate the band at low P50 and made
    the reported uncertainty inversely proportional to output.
    """
    feat_df = add_time_features(df, capacity_lookup, dust_lookup)
    out = df.copy()

    raw = raw_predict(models, feat_df)
    p50 = raw.get(P50, np.zeros(len(out)))
    p10_raw = raw.get(P10, p50 * P10_MISSING_RATIO)
    p90_raw = raw.get(P90, p50 * P90_MISSING_RATIO)

    half_width = np.clip((p90_raw - p10_raw) / 2.0, MIN_HALF_WIDTH_MW, None)

    # Safety cap: the band may not exceed the forecast value (P10 can't go below
    # 0, and P90 shouldn't exceed 2×P50), with an absolute floor for night hours.
    max_half_width = np.maximum(p50, MIN_BAND_REFERENCE_MW)
    half_width = np.minimum(half_width, max_half_width)

    out[FORECAST_P50_COLUMN] = np.round(p50, PRECISION_DIGITS)
    out[FORECAST_P10_COLUMN] = np.clip(np.round(p50 - half_width, PRECISION_DIGITS), 0, None)
    out[FORECAST_P90_COLUMN] = np.round(p50 + half_width, PRECISION_DIGITS)

    return out


__all__ = [
    "FORECAST_P10_COLUMN",
    "FORECAST_P50_COLUMN",
    "FORECAST_P90_COLUMN",
    "predict",
    "raw_predict",
]
