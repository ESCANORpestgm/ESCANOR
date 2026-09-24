"""Forecast scoring: headline metrics and the lead-time backtest against
industry-standard baselines.

Every metric is reported on daylight rows only and normalised by *national*
installed capacity (nRMSE), which is what STEG's grid-integration teams compare
across horizons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ingestion.synthetic_data import HORIZON_BUCKETS, ghi_to_pv_output_kw, horizon_bucket_label
from models.features import add_time_features
from models.inference import (
    FORECAST_P10_COLUMN,
    FORECAST_P50_COLUMN,
    FORECAST_P90_COLUMN,
    predict,
)
from models.training_config import QUANTILES

# Rows below this production (MW) are night/curtailment and excluded from error
# metrics — including them would flatter every score.
DAYLIGHT_MIN_PRODUCTION_MW = 0.01
# Persistence lags compared against the model: yesterday and one week ago.
PERSISTENCE_LAG_HOURS = (24, 168)
# The clear-sky baseline reconstructs cloud-free irradiance from the forecast
# GHI, which the ingestion reports as ``DNI / 0.6``.
CLEARSKY_GHI_RECOVERY_DIVISOR = 0.6
MW_PER_KW = 1000.0
# Coverage is reported as a percentage.
PERCENT = 100.0

HORIZON_COLUMN = "horizon"


def _band_coverage(frame: pd.DataFrame) -> float:
    """Percentage of rows whose actual production falls inside P10–P90."""
    inside = (
        (frame["production_mw"] >= frame[FORECAST_P10_COLUMN])
        & (frame["production_mw"] <= frame[FORECAST_P90_COLUMN])
    )
    return float(inside.mean() * PERCENT)


def _nrmse_pct(errors: pd.Series | np.ndarray, total_capacity_mw: float) -> float:
    """Normalised RMSE as a percentage of national installed capacity."""
    if total_capacity_mw <= 0:
        return 0.0
    return 100 * float(np.sqrt(np.mean(np.asarray(errors, dtype=float) ** 2))) / total_capacity_mw


def _pinball_loss(preds: pd.DataFrame) -> float:
    """Mean quantile loss across the three reported quantiles."""
    losses = []
    for label, q in QUANTILES.items():
        error = preds["production_mw"] - preds[f"forecast_{label}_mw"]
        losses.append(float(np.maximum(q * error, (q - 1) * error).mean()))
    return float(np.mean(losses))


def evaluate(
    models: dict,
    df_test: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
) -> dict:
    """MAE, nRMSE, P10–P90 coverage and pinball loss on the forecast."""
    preds = predict(models, df_test, capacity_lookup, dust_lookup)
    daylight = preds["production_mw"] > DAYLIGHT_MIN_PRODUCTION_MW
    errors = preds.loc[daylight, FORECAST_P50_COLUMN] - preds.loc[daylight, "production_mw"]

    return {
        "MAE_MW": round(float(errors.abs().mean()), 3),
        "nRMSE_%": round(_nrmse_pct(errors, sum(capacity_lookup.values())), 2),
        "P10_P90_coverage_%": round(_band_coverage(preds), 1),
        "pinball_loss": round(_pinball_loss(preds), 4),
    }


def add_persistence_baselines(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ``persistence_<lag>h`` columns: what production looked like then.

    Persistence is the benchmark a forecast must beat; a model that only tracks
    yesterday's weather scores no better than a lookup table.
    """
    out = frame.sort_values(["governorate", "timestamp"]).copy()
    for lag in PERSISTENCE_LAG_HOURS:
        out[f"persistence_{lag}h"] = out.groupby("governorate")["production_mw"].shift(lag)
    return out


def add_clearsky_baseline(
    frame: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
) -> pd.DataFrame:
    """Add ``clearsky_mw``: the physics-only production a clear atmosphere gives."""
    out = frame.copy()
    capacity_kwc = out["governorate"].map(capacity_lookup) * MW_PER_KW
    dust = out["governorate"].map(dust_lookup) if dust_lookup else 0.02
    out["clearsky_mw"] = ghi_to_pv_output_kw(
        out["ghi_wm2"] / CLEARSKY_GHI_RECOVERY_DIVISOR, out["temp_c"],
        capacity_kwc=capacity_kwc.values,
        dust_loss_pct=dust.values if hasattr(dust, "values") else dust,
        noise=False,
    ) / MW_PER_KW
    return out


def evaluate_by_horizon_with_baselines(
    models: dict,
    df_test: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
) -> pd.DataFrame:
    """Backtest by forecast lead-time bucket vs persistence (24h + 168h) and clear-sky."""
    preds = predict(models, df_test, capacity_lookup, dust_lookup)
    feat_df = add_time_features(df_test, capacity_lookup, dust_lookup)
    preds["horizon_bucket"] = horizon_bucket_label(feat_df["horizon_hours"].values)

    baselines = add_persistence_baselines(df_test)
    keyed = baselines.set_index(["governorate", "timestamp"])
    index = preds.set_index(["governorate", "timestamp"]).index
    for lag in PERSISTENCE_LAG_HOURS:
        preds[f"persistence_{lag}h"] = index.map(keyed[f"persistence_{lag}h"])

    preds = add_clearsky_baseline(preds, capacity_lookup, dust_lookup)

    total_capacity = sum(capacity_lookup.values())
    rows = []
    for name, _lo, _hi in HORIZON_BUCKETS:
        bucket = preds[(preds["horizon_bucket"] == name) & (preds["production_mw"] > DAYLIGHT_MIN_PRODUCTION_MW)]
        if bucket.empty:
            continue

        def nrmse(pred_col: str) -> float:
            valid = bucket.dropna(subset=[pred_col])
            if valid.empty:
                return np.nan
            return round(_nrmse_pct(valid[pred_col] - valid["production_mw"], total_capacity), 2)

        rows.append({
            HORIZON_COLUMN:             name,
            "nRMSE_ours_%":             nrmse(FORECAST_P50_COLUMN),
            "nRMSE_persistence_24h_%":  nrmse("persistence_24h"),
            "nRMSE_persistence_168h_%": nrmse("persistence_168h"),
            "nRMSE_clearsky_%":         nrmse("clearsky_mw"),
            "coverage_P10_P90_%":       round(_band_coverage(bucket), 1),
            "n_samples":                len(bucket),
        })
    return pd.DataFrame(rows)


__all__ = [
    "DAYLIGHT_MIN_PRODUCTION_MW",
    "HORIZON_COLUMN",
    "PERSISTENCE_LAG_HOURS",
    "add_clearsky_baseline",
    "add_persistence_baselines",
    "evaluate",
    "evaluate_by_horizon_with_baselines",
]
