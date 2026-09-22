"""
ML forecasting model: gradient-boosted quantile regression.

Trains three models per horizon (P10 / P50 / P90) so the platform can
report both a point forecast and an uncertainty band, as required by
the concept note. Works on the shared schema:
    timestamp, ghi_wm2, [dni_wm2, dhi_wm2, wind_speed_ms,] temp_c,
    cloud_cover_pct, governorate, district, production_mw

New features vs original:
  - dni_wm2 / dhi_wm2: DNI/DHI split matters for rooftop systems with
    varying panel orientations (cloudy sky relies more on diffuse radiation).
  - wind_speed_ms: panel cooling effect — higher wind → lower cell temp →
    slightly higher efficiency.
  - ghi_x_temp: GHI × (temp-25) interaction that directly captures the
    temperature-dependent efficiency drop (strong in Tunisian summers).
  - rolling_ghi_3h: 3-hour rolling average GHI within each governorate,
    smoothing transient cloud effects and reducing prediction variance.
  - All new columns are optional — if the incoming DataFrame lacks them
    (e.g. synthetic data, old data), they are filled with sensible defaults
    so downstream code never breaks.
"""

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
import joblib
import os

QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}

# Base features always present
_BASE_FEATURES = [
    "ghi_wm2", "temp_c", "cloud_cover_pct",
    "hour", "day_of_year_sin", "day_of_year_cos", "capacity_mwc",
    "dust_loss_pct", "horizon_hours",
]

# Extended features added when available
_EXTENDED_FEATURES = [
    "dni_wm2", "dhi_wm2", "wind_speed_ms",
    "ghi_x_temp",       # GHI × (temp_c - 25): temperature efficiency interaction
    "rolling_ghi_3h",   # 3-hour rolling average GHI (per governorate)
]

FEATURE_COLS = _BASE_FEATURES + _EXTENDED_FEATURES


def add_time_features(df: pd.DataFrame, capacity_lookup: dict,
                      dust_lookup: dict = None) -> pd.DataFrame:
    """Enrich df with all model features, handling missing optional columns gracefully."""
    df = df.copy()

    # ── Core time features ──────────────────────────────────────────────────
    df["hour"] = df["timestamp"].dt.hour
    doy = df["timestamp"].dt.dayofyear
    df["day_of_year_sin"] = np.sin(2 * np.pi * doy / 365)
    df["day_of_year_cos"] = np.cos(2 * np.pi * doy / 365)
    df["capacity_mwc"] = df["governorate"].map(capacity_lookup)

    if "dust_loss_pct" not in df.columns:
        df["dust_loss_pct"] = (
            df["governorate"].map(dust_lookup) if dust_lookup else 0.02
        )

    if "horizon_hours" not in df.columns:
        now = pd.Timestamp.now().floor("h")
        df["horizon_hours"] = (df["timestamp"] - now).dt.total_seconds() / 3600.0
        df["horizon_hours"] = df["horizon_hours"].clip(lower=0)

    # ── Extended features (fill defaults if column absent) ──────────────────
    # DNI / DHI — use 60% / 40% of GHI as rough defaults when unavailable
    if "dni_wm2" not in df.columns:
        df["dni_wm2"] = df["ghi_wm2"] * 0.60
    if "dhi_wm2" not in df.columns:
        df["dhi_wm2"] = df["ghi_wm2"] * 0.40

    # Wind speed — Tunisia average ~3 m/s when not measured
    if "wind_speed_ms" not in df.columns:
        df["wind_speed_ms"] = 3.0

    # GHI × (temp - 25): captures efficiency loss at high temperature
    # Positive GHI with high temp → lower actual output than physics predicts
    df["ghi_x_temp"] = df["ghi_wm2"] * (df["temp_c"] - 25.0)

    # 3-hour rolling average GHI per governorate (smooths cloud transients)
    # Sort first so the rolling window is time-ordered within each governorate
    df = df.sort_values(["governorate", "timestamp"])
    df["rolling_ghi_3h"] = (
        df.groupby("governorate")["ghi_wm2"]
        .transform(lambda s: s.rolling(3, min_periods=1).mean())
    )

    return df


def train_quantile_models(df: pd.DataFrame, capacity_lookup: dict,
                           dust_lookup: dict = None) -> dict:
    """Train P10/P50/P90 gradient-boosted quantile regression models."""
    df = add_time_features(df, capacity_lookup, dust_lookup)
    X = df[FEATURE_COLS]
    y = df["production_mw"]

    models = {}
    for label, q in QUANTILES.items():
        model = LGBMRegressor(
            objective="quantile", alpha=q,
            n_estimators=400, max_depth=6, learning_rate=0.04,
            num_leaves=31, min_child_samples=20,
            subsample=0.85, colsample_bytree=0.85,
            verbose=-1,
        )
        model.fit(X, y)
        models[label] = model
    return models


def predict(models: dict, df: pd.DataFrame, capacity_lookup: dict,
            dust_lookup: dict = None) -> pd.DataFrame:
    """Return df with forecast_p10_mw / forecast_p50_mw / forecast_p90_mw added."""
    feat_df = add_time_features(df, capacity_lookup, dust_lookup)
    X = feat_df[FEATURE_COLS]
    out = df.copy()
    for label, model in models.items():
        preds = model.predict(X)
        out[f"forecast_{label}_mw"] = np.clip(preds, 0, None)
    # Enforce monotonicity: p10 ≤ p50 ≤ p90 (quantile crossing guard)
    quantile_columns = ["forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw"]
    out[quantile_columns] = np.sort(out[quantile_columns].values, axis=1)

    return out


def evaluate(models: dict, df_test: pd.DataFrame, capacity_lookup: dict,
             dust_lookup: dict = None) -> dict:
    """MAE / nRMSE on the p50 (median) forecast, only over daylight hours."""
    preds = predict(models, df_test, capacity_lookup, dust_lookup)
    daylight = preds["production_mw"] > 0.01
    err = preds.loc[daylight, "forecast_p50_mw"] - preds.loc[daylight, "production_mw"]
    total_capacity = sum(capacity_lookup.values())
    mae = err.abs().mean()
    rmse = np.sqrt((err ** 2).mean())
    nrmse_pct = 100 * rmse / total_capacity
    coverage = (
        (preds["production_mw"] >= preds["forecast_p10_mw"]) &
        (preds["production_mw"] <= preds["forecast_p90_mw"])
    ).mean() * 100
    return {
        "MAE_MW": round(mae, 3),
        "nRMSE_%": round(nrmse_pct, 2),
        "P10_P90_coverage_%": round(coverage, 1),
    }


def evaluate_by_horizon_with_baselines(models: dict, df_test: pd.DataFrame,
                                        capacity_lookup: dict,
                                        dust_lookup: dict = None) -> pd.DataFrame:
    """
    Backtest by forecast lead-time bucket, compared against two baselines:

    Persistence: "production equals what it was 24 h ago" — standard naive
      baseline in solar forecasting.
    Clear-sky: assume zero cloud cover (physics upper bound ignoring clouds).

    Uncertainty aggregation note: the combined P10-P90 band at national level
    uses sqrt-sum-of-squares of per-governorate half-widths, which assumes
    partial spatial independence of forecast errors. In practice, adjacent
    governorates share the same cloud systems (high error correlation), so
    this approach slightly under-states the true uncertainty for nearby
    regions. A full covariance model (Bremnes 2004) would be more accurate
    but requires a historical error correlation matrix.
    """
    from ingestion.synthetic_data import HORIZON_BUCKETS, horizon_bucket_label, ghi_to_pv_output_kw

    preds = predict(models, df_test, capacity_lookup, dust_lookup)
    preds["horizon_bucket"] = horizon_bucket_label(
        add_time_features(df_test, capacity_lookup, dust_lookup)["horizon_hours"].values
    )

    # Persistence baseline (24 h lag)
    df_sorted = df_test.sort_values(["governorate", "timestamp"]).copy()
    df_sorted["persistence_mw"] = df_sorted.groupby("governorate")["production_mw"].shift(24)
    persist_lookup = df_sorted.set_index(["governorate", "timestamp"])["persistence_mw"]
    preds["persistence_mw"] = preds.set_index(["governorate", "timestamp"]).index.map(persist_lookup)

    # Clear-sky baseline (physics, no cloud attenuation)
    cap_series = preds["governorate"].map(capacity_lookup) * 1000
    dust_series = preds["governorate"].map(dust_lookup) if dust_lookup else 0.02
    preds["clearsky_mw"] = ghi_to_pv_output_kw(
        preds["ghi_wm2"] / 0.6, preds["temp_c"],
        capacity_kwc=cap_series.values,
        dust_loss_pct=dust_series.values if hasattr(dust_series, "values") else dust_series,
        noise=False,
    ) / 1000.0

    rows = []
    total_capacity = sum(capacity_lookup.values())
    for name, lo, hi in HORIZON_BUCKETS:
        bucket = preds[preds["horizon_bucket"] == name]
        bucket = bucket[bucket["production_mw"] > 0.01]
        if bucket.empty:
            continue

        def nrmse(pred_col):
            valid = bucket.dropna(subset=[pred_col])
            if valid.empty:
                return np.nan
            err = valid[pred_col] - valid["production_mw"]
            return round(100 * np.sqrt((err ** 2).mean()) / total_capacity, 2)

        coverage = (
            (bucket["production_mw"] >= bucket["forecast_p10_mw"]) &
            (bucket["production_mw"] <= bucket["forecast_p90_mw"])
        ).mean() * 100

        rows.append({
            "horizon":                 name,
            "nRMSE_ours_%":            nrmse("forecast_p50_mw"),
            "nRMSE_persistence_%":     nrmse("persistence_mw"),
            "nRMSE_clearsky_%":        nrmse("clearsky_mw"),
            "coverage_P10_P90_%":      round(coverage, 1),
            "n_samples":               len(bucket),
        })
    return pd.DataFrame(rows)


def save_models(models: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(models, path)


def load_models(path: str) -> dict:
    return joblib.load(path)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.steg_districts import STEG_DISTRICTS, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
    from ingestion.synthetic_data import generate_all

    print("Generating synthetic training data …")
    df = generate_all(STEG_DISTRICTS, start="2023-01-01", end="2025-01-01")
    capacity_lookup = DISTRICT_CAPACITY_LOOKUP
    dust_lookup     = DISTRICT_DUST_LOOKUP

    split = pd.Timestamp("2024-10-01")
    train, test = df[df.timestamp < split], df[df.timestamp >= split]

    print(f"Train rows: {len(train):,}  Test rows: {len(test):,}")
    print("Training quantile models (P10/P50/P90, extended features)…")
    models = train_quantile_models(train, capacity_lookup, dust_lookup)

    print("Overall backtest:")
    print(evaluate(models, test, capacity_lookup, dust_lookup))

    print("By-horizon backtest (vs persistence & clear-sky):")
    horizon_metrics = evaluate_by_horizon_with_baselines(models, test, capacity_lookup, dust_lookup)
    print(horizon_metrics.to_string(index=False))

    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(results_dir, exist_ok=True)
    horizon_metrics.to_csv(os.path.join(results_dir, "metrics_by_horizon.csv"), index=False)

    save_models(models, os.path.join(os.path.dirname(__file__), "artifacts", "quantile_models.joblib"))
    print("Models and metrics saved.")
