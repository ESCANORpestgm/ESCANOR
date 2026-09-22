"""Build reproducible aggregate rooftop-PV forecast history for the dashboard.

The historical workflow uses the SolNet-style dataset generator, but keeps the
PréSol spatial level at STEG commercial districts and national aggregation.
Synthetic output is explicitly marked and must be replaced by validated real
measurements for production evaluation.

Run:
    python models/history.py --days 7
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.ml_forecast import load_models, predict

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "artifacts" / "quantile_models.joblib"
DATASET_PATH = ROOT / "results" / "datasets" / "rooftop_actual_15min.csv"
HISTORY_PATH = ROOT / "results" / "history_national.csv"


def _to_model_schema(dataset: pd.DataFrame) -> pd.DataFrame:
    frame = cast(pd.DataFrame, dataset.copy())
    frame["timestamp"] = pd.to_datetime(frame["timestamp_utc"], utc=True).dt.tz_localize(None)
    frame["governorate"] = frame["district"]
    frame["steg_district"] = frame["district"]
    frame["production_mw"] = frame["power_kw"] / 1000.0
    return frame


def build_national_history(
    days: int = 30,
    start: str = "2020-12-01",
    seed: int = 42,
) -> pd.DataFrame:
    """Evaluate the deployed model against the PVGIS district dataset."""
    del seed  # Retained for CLI compatibility; PVGIS data is deterministic.
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(f"PVGIS dataset not found: {DATASET_PATH}")
    dataset = pd.read_csv(DATASET_PATH)
    timestamps = pd.to_datetime(dataset["timestamp_utc"], utc=True)
    end = pd.Timestamp(start, tz="UTC") + pd.Timedelta(days=days)
    selected = dataset.loc[(timestamps >= pd.Timestamp(start, tz="UTC")) & (timestamps < end)].copy()
    if selected.empty:
        raise ValueError(f"No PVGIS rows found between {start} and {end.date()}")
    # The dashboard compares hourly national points, so aggregate the 15-minute
    # PVGIS observations before evaluating and plotting them.
    selected["timestamp_utc"] = pd.to_datetime(selected["timestamp_utc"], utc=True).dt.floor("h").astype(str)
    numeric_columns = ["power_kw", "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c", "cloud_cover_pct", "wind_speed_ms", "energy_kwh"]
    hourly = selected.groupby(["timestamp_utc", "district", "direction"], as_index=False)[numeric_columns].mean()
    for column in ["location_id", "pv_count", "system_size_kwc", "installed_capacity_kwp", "tilt_deg", "azimuth_deg", "horizon_hours", "quality_status", "source", "dataset_version"]:
        if column in selected.columns:
            hourly[column] = selected.groupby(["timestamp_utc", "district", "direction"], as_index=False)[column].first()[column]
    dataset = hourly

    model_frame = _to_model_schema(dataset)
    models = load_models(str(MODEL_PATH))
    predictions = cast(pd.DataFrame, predict(models, model_frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP))

    national = cast(pd.DataFrame, predictions.groupby("timestamp", as_index=False).agg(
        actual_mw=("production_mw", "sum"),
        forecast_p50_mw=("forecast_p50_mw", "sum"),
        forecast_p10_mw=("forecast_p10_mw", "sum"),
        forecast_p90_mw=("forecast_p90_mw", "sum"),
    ))
    national["error_mw"] = national["forecast_p50_mw"] - national["actual_mw"]
    actual = cast(pd.Series, national["actual_mw"])
    national["error_pct"] = (100 * national["error_mw"] / actual.replace(0, np.nan)).fillna(0)
    national["source"] = str(dataset["source"].iloc[0]) if "source" in dataset.columns else "pvgis_district_model"
    national["dataset_path"] = str(DATASET_PATH.relative_to(ROOT))
    return national


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--start", default="2020-12-01")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    history = build_national_history(days=args.days, start=args.start, seed=args.seed)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(HISTORY_PATH, index=False)
    print(f"Saved {len(history)} national history rows to {HISTORY_PATH}")
    print(f"Saved source dataset to {DATASET_PATH}")


if __name__ == "__main__":
    main()
