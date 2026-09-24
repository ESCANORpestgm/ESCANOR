"""
Continuous learning loop with temporal cross-validation, multi-baseline
drift detection, data quality gating, and conformal uncertainty calibration.

Workflow:
  1. Validate incoming data (remove outliers, night-with-production, etc.)
  2. Evaluate drift against persistence (24h + 168h) and climatology baselines
  3. If drift exceeds threshold, train candidate with temporal CV
  4. Calibrate conformal uncertainty on the validation split
  5. Promote candidate only if it outperforms current production
  6. Save calibration artifacts alongside the model

Run: python models/retrain.py
"""

import os
import sys
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP, STEG_DISTRICTS
from ingestion.synthetic_data import generate_all
from models.ml_forecast import (
    train_quantile_models, predict, evaluate, load_models, save_models,
    validate_training_data, conformal_calibrate, calibrate_horizon_scales,
    save_calibration, tune_hyperparameters,
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
CALIBRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "calibration.json")
DRIFT_THRESHOLD_PCT = 15.0  # retrain if our model's error is within 15% of best baseline
TEMPORAL_CV_FOLDS = 3       # expanding-window temporal cross-validation folds
USE_TUNING = False          # set True to enable Optuna tuning during retrain
TUNING_TRIALS = 15          # Optuna trials when USE_TUNING is True


def _compute_multi_baseline_mae(recent_df: pd.DataFrame) -> dict[str, float]:
    """Compute MAE for persistence (24h, 168h) and climatology baselines.

    The climatology baseline uses the mean production per (district, hour_of_day),
    capturing the average diurnal cycle — a strong baseline for seasonal climates.
    """
    df_sorted = recent_df.sort_values(["governorate", "timestamp"]).copy()
    intervals = pd.to_datetime(df_sorted["timestamp"]).sort_values().diff().dropna()
    intervals_min = float(intervals.dt.total_seconds().median() / 60) if len(intervals) > 0 else 60.0
    steps_24h = max(1, round(24 * 60 / intervals_min))
    steps_168h = max(1, round(168 * 60 / intervals_min))

    df_sorted["persist_24h"] = df_sorted.groupby("governorate")["production_mw"].shift(steps_24h)
    df_sorted["persist_168h"] = df_sorted.groupby("governorate")["production_mw"].shift(steps_168h)

    hourly = pd.to_datetime(df_sorted["timestamp"]).dt.hour
    df_sorted["climatology"] = df_sorted.groupby(
        ["governorate", hourly]
    )["production_mw"].transform("mean")

    results: dict[str, float] = {}
    for baseline_name, col in [("persistence_24h", "persist_24h"),
                                 ("persistence_168h", "persist_168h"),
                                 ("climatology", "climatology")]:
        valid = df_sorted.dropna(subset=[col])
        if valid.empty:
            results[baseline_name] = float("inf")
            continue
        results[baseline_name] = float((valid[col] - valid["production_mw"]).abs().mean())
    return results


def _temporal_cv_train(df: pd.DataFrame, capacity_lookup: dict, dust_lookup: dict,
                        params: dict | None = None) -> tuple[dict, dict]:
    """Train with expanding-window temporal CV, return final model + avg metrics.

    Uses 3 expanding folds (50/65/80 percentile cutoffs) to simulate
    real-world deployment where the model is trained on past data and
    evaluated on future data.
    """
    timestamps = pd.to_datetime(df["timestamp"])
    fold_mae_list: list[float] = []
    last_metrics: dict | None = None

    fold_fracs = np.linspace(0.5, 0.85, TEMPORAL_CV_FOLDS)
    for frac in fold_fracs:
        cutoff = timestamps.quantile(frac)
        train_df = cast(pd.DataFrame, df[timestamps < cutoff])
        val_df = cast(pd.DataFrame, df[timestamps >= cutoff])
        if train_df.empty or val_df.empty:
            continue
        candidate = train_quantile_models(train_df, capacity_lookup, dust_lookup,
                                          params=params, use_ensemble=True)
        metrics = evaluate(candidate, val_df, capacity_lookup, dust_lookup)
        fold_mae_list.append(metrics["MAE_MW"])
        last_metrics = metrics

    if last_metrics is None:
        raise ValueError("No valid temporal CV folds could be constructed")

    avg_mae = float(np.mean(fold_mae_list))
    avg_metrics = {
        **last_metrics,
        "MAE_MW": round(avg_mae, 3),
        "cv_folds": TEMPORAL_CV_FOLDS,
        "cv_fold_maes": [round(m, 3) for m in fold_mae_list],
    }

    # Final model trained on 80% of data
    final_train_cutoff = timestamps.quantile(0.8)
    final_train_df = cast(pd.DataFrame, df[timestamps < final_train_cutoff])
    final_models = train_quantile_models(final_train_df, capacity_lookup, dust_lookup,
                                          params=params, use_ensemble=True)
    return final_models, avg_metrics


def check_drift_and_retrain(recent_df: pd.DataFrame, capacity_lookup: dict,
                             dust_lookup: dict) -> dict:
    """Validate data, evaluate drift, train candidate with temporal CV, and promote if better."""

    # Step 1: Data quality gate
    recent_df = validate_training_data(recent_df, capacity_lookup)
    if recent_df.empty:
        return {"retrained": False, "error": "All data filtered out by quality gate"}

    # Step 2: Evaluate current model on the latest 20% of data
    models = load_models(MODEL_PATH)
    timestamps = pd.to_datetime(recent_df["timestamp"])
    cutoff = timestamps.quantile(0.8)
    validation_df = cast(pd.DataFrame, recent_df.loc[timestamps >= cutoff])
    baseline_frame: pd.DataFrame = validation_df if not validation_df.empty else recent_df
    current_metrics = evaluate(models, baseline_frame, capacity_lookup, dust_lookup)

    preds = predict(models, recent_df, capacity_lookup, dust_lookup)
    daylight = preds["production_mw"] > 0.01
    our_mae = float((preds.loc[daylight, "forecast_p50_mw"] - preds.loc[daylight, "production_mw"]).abs().mean())

    # Step 3: Multi-baseline drift detection
    baseline_maes = _compute_multi_baseline_mae(recent_df)
    best_baseline_mae = min(baseline_maes.values())
    drift_pct = 100 * our_mae / best_baseline_mae if best_baseline_mae > 0 else 0

    ensure_initial_production(Path(MODEL_PATH), current_metrics)
    status: dict = {
        "our_mae_mw": round(our_mae, 3),
        "baseline_maes": {k: round(v, 3) for k, v in baseline_maes.items()},
        "best_baseline_mae_mw": round(best_baseline_mae, 3),
        "drift_ratio_pct": round(float(drift_pct), 1),
        "retrained": False,
        "candidate_promoted": False,
    }
    if drift_pct <= (100 - DRIFT_THRESHOLD_PCT):
        return status

    # Step 4: Train candidate with temporal CV
    run_id = create_training_run(
        str(recent_df["timestamp"].min()), str(recent_df["timestamp"].max()),
        "time_weather_v2", "rooftop_pv_measurement_v2",
        "validated rooftop measurements (quality-gated)",
    )
    try:
        train_df = cast(pd.DataFrame, recent_df.loc[timestamps < cutoff])
        validation_df = cast(pd.DataFrame, recent_df.loc[timestamps >= cutoff])
        if train_df.empty or validation_df.empty:
            raise ValueError("Not enough data for training and validation splits")

        # Optional hyperparameter tuning
        params = None
        if USE_TUNING:
            params = tune_hyperparameters(train_df, capacity_lookup, dust_lookup,
                                          n_trials=TUNING_TRIALS)
            status["tuned_params"] = {k: v for k, v in params.items() if k != "verbose"}

        # Temporal CV training
        candidate_models, cv_metrics = _temporal_cv_train(
            recent_df, capacity_lookup, dust_lookup, params=params)

        # Step 5: Conformal calibration on the 70-80% slice
        cal_split = timestamps.quantile(0.7)
        df_cal = cast(pd.DataFrame, recent_df[(timestamps >= cal_split) & (timestamps < cutoff)])
        conformal_q = conformal_calibrate(candidate_models, df_cal, capacity_lookup, dust_lookup)
        horizon_scales = calibrate_horizon_scales(candidate_models, df_cal, capacity_lookup, dust_lookup)
        save_calibration({"conformal_q": conformal_q, "horizon_scales": horizon_scales}, CALIBRATION_PATH)

        # Step 6: Evaluate candidate with conformal correction
        candidate_metrics = evaluate(candidate_models, validation_df, capacity_lookup, dust_lookup,
                                     conformal_q=conformal_q)
        candidate_metrics["conformal_q"] = round(conformal_q, 4)
        candidate_metrics["horizon_scales"] = horizon_scales
        candidate_metrics["cv_avg_mae"] = cv_metrics.get("MAE_MW")

        candidate_path = REGISTRY_DIR / "artifacts" / f"candidate_{run_id}.joblib"
        save_models(candidate_models, str(candidate_path))
        model_version = register_model(
            run_id, str(candidate_path), candidate_metrics,
            str(train_df["timestamp"].min()), str(train_df["timestamp"].max()),
            "time_weather_v2", "rooftop_pv_measurement_v2", "candidate",
        )
        status.update({
            "retrained": True,
            "training_run_id": run_id,
            "candidate_model_version": model_version,
            "candidate_mae_mw": candidate_metrics.get("MAE_MW"),
            "conformal_q": round(conformal_q, 4),
        })

        # Step 7: Promote if better than current production
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
