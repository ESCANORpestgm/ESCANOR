"""
Generates a real actual-vs-forecast historical comparison, national level,
for the last N days of the held-out test period. This is exactly the kind
of feedback data models/retrain.py uses to detect drift — showing it in
the dashboard makes the continuous-learning story concrete instead of
abstract.

Run: python models/history.py
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import STEG_DISTRICTS, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from ingestion.synthetic_data import generate_all
from models.ml_forecast import load_models, predict

MODEL_PATH = os.path.join(os.path.dirname(__file__), "artifacts", "quantile_models.joblib")


def build_national_history(days: int = 7) -> pd.DataFrame:
    capacity_lookup = DISTRICT_CAPACITY_LOOKUP
    dust_lookup = DISTRICT_DUST_LOOKUP

    # Held-out test period (same split used in ml_forecast.py)
    df = generate_all(STEG_DISTRICTS, start="2024-10-01", end="2025-01-01")
    cutoff = df.timestamp.max() - pd.Timedelta(days=days)
    recent = df[df.timestamp >= cutoff].copy()

    # Nowcast-style comparison: what would the model have said, using the
    # weather available at the time (horizon_hours forced to 0, i.e. "we're
    # asking right now, for right now" — the fairest actual-vs-forecast test).
    recent["horizon_hours"] = 0.0

    models = load_models(MODEL_PATH)
    preds = predict(models, recent, capacity_lookup, dust_lookup)

    national = preds.groupby("timestamp").agg(
        actual_mw=("production_mw", "sum"),
        forecast_p50_mw=("forecast_p50_mw", "sum"),
        forecast_p10_mw=("forecast_p10_mw", "sum"),
        forecast_p90_mw=("forecast_p90_mw", "sum"),
    ).reset_index()

    national["error_mw"] = national["forecast_p50_mw"] - national["actual_mw"]
    national["error_pct"] = (
        100 * national["error_mw"] / national["actual_mw"].replace(0, pd.NA)
    ).fillna(0)

    return national


if __name__ == "__main__":
    history = build_national_history(days=7)
    results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(results_dir, exist_ok=True)
    out_path = os.path.join(results_dir, "history_national.csv")
    history.to_csv(out_path, index=False)
    print(f"Saved {len(history)} rows to {out_path}")
    print(history.tail(10).to_string(index=False))
