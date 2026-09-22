"""
Continuous learning loop: compare recent forecast error against a
persistence baseline; if the model has drifted (degraded) beyond a
threshold, retrain on the latest available data.

In production this would run on a schedule (cron / Airflow / GitHub
Action), fed by real STEG metering data as it arrives — exactly what
the note conceptuelle calls "apprentissage continu à partir des écarts
entre les prévisions et les productions observées".

Run: python models/retrain.py
"""

import os
import sys
from pathlib import Path
from typing import cast

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP, STEG_DISTRICTS
from ingestion.synthetic_data import generate_all
from models.ml_forecast import (
    train_quantile_models, predict, evaluate, load_models, save_models
)
from models.model_registry import (
    REGISTRY_DIR,
    create_training_run,
    ensure_initial_production,
    finish_training_run,
    promote_model,
    register_model,
)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "artifacts", "quantile_models.joblib")
DRIFT_THRESHOLD_PCT = 15.0  # retrain if our model's error is within 15% of naive persistence


def check_drift_and_retrain(recent_df: pd.DataFrame, capacity_lookup: dict, dust_lookup: dict) -> dict:
    """Evaluate drift, train an immutable candidate, and promote only if better."""
    models = load_models(MODEL_PATH)
    timestamps = pd.to_datetime(recent_df["timestamp"])
    cutoff = timestamps.quantile(0.8)
    validation_df = cast(pd.DataFrame, recent_df.loc[timestamps >= cutoff])
    baseline_frame: pd.DataFrame = validation_df if not validation_df.empty else recent_df
    current_metrics = evaluate(models, baseline_frame, capacity_lookup, dust_lookup)
    preds = predict(models, recent_df, capacity_lookup, dust_lookup)
    daylight = preds["production_mw"] > 0.01
    our_mae = (preds.loc[daylight, "forecast_p50_mw"] - preds.loc[daylight, "production_mw"]).abs().mean()

    df_sorted = recent_df.sort_values(["governorate", "timestamp"]).copy()
    intervals = pd.to_datetime(df_sorted["timestamp"]).sort_values().diff().dropna().dt.total_seconds() / 60
    interval_minutes = float(intervals[intervals > 0].median()) if not intervals.empty else 60.0
    persistence_steps = max(1, round(24 * 60 / interval_minutes))
    df_sorted["persistence_mw"] = df_sorted.groupby("governorate")["production_mw"].shift(persistence_steps)
    persist_mae = (df_sorted["persistence_mw"] - df_sorted["production_mw"]).abs().mean()
    drift_pct = 100 * our_mae / persist_mae if persist_mae > 0 else 0

    ensure_initial_production(Path(MODEL_PATH), current_metrics)
    status = {
        "our_mae_mw": round(float(our_mae), 3),
        "persistence_mae_mw": round(float(persist_mae), 3),
        "drift_ratio_pct": round(float(drift_pct), 1),
        "retrained": False,
        "candidate_promoted": False,
    }
    if drift_pct <= (100 - DRIFT_THRESHOLD_PCT):
        return status

    run_id = create_training_run(
        str(recent_df["timestamp"].min()), str(recent_df["timestamp"].max()),
        "time_weather_v1", "rooftop_pv_measurement_v1", "validated rooftop measurements",
    )
    try:
        train_df = cast(pd.DataFrame, recent_df.loc[timestamps < cutoff])
        validation_df = cast(pd.DataFrame, recent_df.loc[timestamps >= cutoff])
        if train_df.empty or validation_df.empty:
            raise ValueError("Not enough data for a separate training and validation split")

        candidate_models = train_quantile_models(train_df, capacity_lookup, dust_lookup)
        candidate_metrics = evaluate(candidate_models, validation_df, capacity_lookup, dust_lookup)
        candidate_path = REGISTRY_DIR / "artifacts" / f"candidate_{run_id}.joblib"
        save_models(candidate_models, str(candidate_path))
        model_version = register_model(
            run_id, str(candidate_path), candidate_metrics,
            str(train_df["timestamp"].min()), str(train_df["timestamp"].max()),
            "time_weather_v1", "rooftop_pv_measurement_v1", "candidate",
        )
        status.update({
            "retrained": True,
            "training_run_id": run_id,
            "candidate_model_version": model_version,
            "candidate_mae_mw": candidate_metrics.get("MAE_MW"),
        })
        try:
            promote_model(model_version, Path(MODEL_PATH))
            status["candidate_promoted"] = True
        except ValueError as promotion_error:
            status["promotion_reason"] = str(promotion_error)
        return status
    except Exception as error:
        finish_training_run(run_id, "failed", error=str(error))
        raise


if __name__ == "__main__":
    capacity_lookup = DISTRICT_CAPACITY_LOOKUP
    dust_lookup = DISTRICT_DUST_LOOKUP

    recent = generate_all(STEG_DISTRICTS, start="2024-12-15", end="2025-01-01")

    result = check_drift_and_retrain(recent, capacity_lookup, dust_lookup)
    print("Drift check result:", result)
