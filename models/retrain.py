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
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import STEG_DISTRICTS, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from ingestion.synthetic_data import generate_all
from models.ml_forecast import (
    train_quantile_models, predict, evaluate, load_models, save_models, FEATURE_COLS
)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "artifacts", "quantile_models.joblib")
DRIFT_THRESHOLD_PCT = 15.0  # retrain if our model's error is within 15% of naive persistence


def check_drift_and_retrain(recent_df: pd.DataFrame, capacity_lookup: dict, dust_lookup: dict) -> dict:
    """
    Compares the CURRENT model's MAE on recent_df against a persistence
    baseline (production 24h earlier). If our model isn't beating
    persistence by a healthy margin anymore, that's a sign conditions have
    shifted (new installations, seasonal change, degraded panels...) and
    it's time to retrain.
    """
    models = load_models(MODEL_PATH)
    preds = predict(models, recent_df, capacity_lookup, dust_lookup)
    daylight = preds["production_mw"] > 0.01

    our_mae = (preds.loc[daylight, "forecast_p50_mw"] - preds.loc[daylight, "production_mw"]).abs().mean()

    df_sorted = recent_df.sort_values(["governorate", "timestamp"]).copy()
    df_sorted["persistence_mw"] = df_sorted.groupby("governorate")["production_mw"].shift(24)
    persist_mae = (df_sorted["persistence_mw"] - df_sorted["production_mw"]).abs().mean()

    # "drift" here = how close our error has crept toward the naive baseline
    drift_pct = 100 * our_mae / persist_mae if persist_mae > 0 else 0

    status = {
        "our_mae_mw": round(our_mae, 3),
        "persistence_mae_mw": round(persist_mae, 3),
        "drift_ratio_pct": round(drift_pct, 1),
        "retrained": False,
    }

    if drift_pct > (100 - DRIFT_THRESHOLD_PCT):
        # Our model is no longer clearly beating the naive baseline — retrain.
        new_models = train_quantile_models(recent_df, capacity_lookup, dust_lookup)
        save_models(new_models, MODEL_PATH)
        status["retrained"] = True

    return status


if __name__ == "__main__":
    capacity_lookup = DISTRICT_CAPACITY_LOOKUP
    dust_lookup = DISTRICT_DUST_LOOKUP

    recent = generate_all(STEG_DISTRICTS, start="2024-12-15", end="2025-01-01")

    result = check_drift_and_retrain(recent, capacity_lookup, dust_lookup)
    print("Drift check result:", result)
