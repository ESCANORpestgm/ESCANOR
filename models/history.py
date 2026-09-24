"""Build reproducible aggregate rooftop-PV forecast history for the dashboard.

Generates three output files:
  - history_national.csv     — hourly actual vs forecast (nighttime zeroed)
  - history_daily.csv         — daily rolling accuracy / nRMSE / coverage
  - training_progression.csv — per-training-run metrics showing model learning

Run:
    python models/history.py --days 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.ml_forecast import load_models, predict, load_calibration

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "artifacts" / "quantile_models.joblib"
DATASET_PATH = ROOT / "results" / "datasets" / "rooftop_actual_15min.csv"
CALIBRATION_PATH = ROOT / "results" / "calibration.json"
HISTORY_PATH = ROOT / "results" / "history_national.csv"
DAILY_PATH = ROOT / "results" / "history_daily.csv"
PROGRESSION_PATH = ROOT / "results" / "training_progression.csv"
TRAINING_RUNS_PATH = ROOT / "results" / "model_registry" / "training_runs.json"
RETRAIN_LOG_PATH = ROOT / "results" / "retrain_log.csv"
VALIDATION_PATH = ROOT / "results" / "model_validation_metrics.json"

# GHI threshold below which forecasts are zeroed (nighttime / overcast-dark)
GHI_NIGHT_THRESHOLD = 1.0  # W/m²


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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate the deployed model against the PVGIS district dataset.

    Returns (hourly_national, daily_summary) DataFrames.
    """
    del seed  # Retained for CLI compatibility; PVGIS data is deterministic.
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(f"PVGIS dataset not found: {DATASET_PATH}")
    dataset = pd.read_csv(DATASET_PATH)
    timestamps = pd.to_datetime(dataset["timestamp_utc"], utc=True)
    end = pd.Timestamp(start, tz="UTC") + pd.Timedelta(days=days)
    selected = dataset.loc[(timestamps >= pd.Timestamp(start, tz="UTC")) & (timestamps < end)].copy()
    if selected.empty:
        raise ValueError(f"No PVGIS rows found between {start} and {end.date()}")
    # Aggregate 15-min → hourly per district/direction
    selected["timestamp_utc"] = pd.to_datetime(selected["timestamp_utc"], utc=True).dt.floor("h").astype(str)
    numeric_columns = ["power_kw", "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c", "cloud_cover_pct", "wind_speed_ms", "energy_kwh"]
    hourly = selected.groupby(["timestamp_utc", "district", "direction"], as_index=False)[numeric_columns].mean()
    for column in ["location_id", "pv_count", "system_size_kwc", "installed_capacity_kwp", "tilt_deg", "azimuth_deg", "horizon_hours", "quality_status", "source", "dataset_version"]:
        if column in selected.columns:
            hourly[column] = selected.groupby(["timestamp_utc", "district", "direction"], as_index=False)[column].first()[column]
    dataset = hourly

    model_frame = _to_model_schema(dataset)
    models = load_models(str(MODEL_PATH))
    calibration = load_calibration(str(CALIBRATION_PATH))
    predictions = cast(pd.DataFrame, predict(
        models, model_frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP,
        conformal_q=calibration.get("conformal_q", 0.0),
        horizon_scales=calibration.get("horizon_scales"),
    ))

    # ── Nighttime zeroing: when GHI ≈ 0, no solar production is possible ────
    night_mask = predictions["ghi_wm2"] < GHI_NIGHT_THRESHOLD
    predictions.loc[night_mask, "forecast_p50_mw"] = 0.0
    predictions.loc[night_mask, "forecast_p10_mw"] = 0.0
    predictions.loc[night_mask, "forecast_p90_mw"] = 0.0

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

    # ── Daily rolling metrics ────────────────────────────────────────────────
    national["date"] = pd.to_datetime(national["timestamp"]).dt.date
    daylight = national[national["actual_mw"] > 0.1].copy()
    daylight["abs_error"] = daylight["error_mw"].abs()
    daylight["sq_error"] = daylight["error_mw"] ** 2
    daylight["in_band"] = (
        (daylight["actual_mw"] >= daylight["forecast_p10_mw"]) &
        (daylight["actual_mw"] <= daylight["forecast_p90_mw"])
    ).astype(int)

    daily = daylight.groupby("date", as_index=False).agg(
        hours=("actual_mw", "count"),
        total_actual_mwh=("actual_mw", "sum"),
        total_forecast_mwh=("forecast_p50_mw", "sum"),
        mae_mw=("abs_error", "mean"),
        rmse_mw=("sq_error", lambda x: np.sqrt(x.mean())),
        coverage_pct=("in_band", "mean"),
    )
    daily["mae_mw"] = daily["mae_mw"].round(2)
    daily["rmse_mw"] = daily["rmse_mw"].round(2)
    daily["coverage_pct"] = (daily["coverage_pct"] * 100).round(1)
    daily["nrmse_pct"] = (100 * daily["rmse_mw"] / daily["total_actual_mwh"].replace(0, np.nan) * daily["hours"]).round(2)
    daily["nrmse_pct"] = daily["nrmse_pct"].fillna(0)
    daily["bias_mw"] = (daily["total_forecast_mwh"] - daily["total_actual_mwh"]).round(2)
    daily["date"] = daily["date"].astype(str)

    return national, daily


def build_training_progression() -> pd.DataFrame:
    """Build a per-training-run progression table showing how the model learned.

    Merges data from:
      - model_registry/training_runs.json  (all training runs, metrics)
      - retrain_log.csv                  (drift detection, promotion decisions)
      - model_validation_metrics.json     (current model train/val split)
    """
    rows: list[dict] = []

    # 1) Training runs from registry
    if TRAINING_RUNS_PATH.exists():
        runs = json.loads(TRAINING_RUNS_PATH.read_text(encoding="utf-8"))
        for run in runs:
            metrics = run.get("metrics", {})
            rows.append({
                "step": len(rows) + 1,
                "run_id": run.get("training_run_id", ""),
                "model_version": run.get("model_version", ""),
                "status": run.get("status", ""),
                "source": run.get("source", ""),
                "feature_version": run.get("feature_version", ""),
                "data_start": run.get("data_start") or "",
                "data_end": run.get("data_end") or "",
                "finished_at": run.get("finished_at", ""),
                "mae_mw": metrics.get("MAE_MW", np.nan),
                "nrmse_pct": metrics.get("nRMSE_%", np.nan),
                "coverage_pct": metrics.get("P10_P90_coverage_%", np.nan),
                "promoted": False,
                "drift_ratio_pct": np.nan,
            })

    # 2) Enrich with retrain log (promotion, drift)
    if RETRAIN_LOG_PATH.exists():
        try:
            retrain_df = pd.read_csv(RETRAIN_LOG_PATH)
            for _, entry in retrain_df.iterrows():
                run_id = str(entry.get("training_run_id", ""))
                promoted = bool(entry.get("candidate_promoted", False))
                drift = entry.get("drift_ratio_pct", np.nan)
                candidate_mae = entry.get("candidate_mae_mw", np.nan)
                for row in rows:
                    if row["run_id"] == run_id:
                        row["promoted"] = promoted
                        if not np.isnan(drift):
                            row["drift_ratio_pct"] = float(drift)
                        if not np.isnan(candidate_mae) and np.isnan(row["mae_mw"]):
                            row["mae_mw"] = float(candidate_mae)
                        break
        except Exception:
            pass

    # 3) Add current validation metrics as a final "evaluation" row
    if VALIDATION_PATH.exists():
        try:
            val = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
            train = val.get("training", {})
            valid = val.get("validation", {})
            if rows:
                rows[-1]["mae_mw"] = valid.get("mae_mw", rows[-1]["mae_mw"])
                rows[-1]["nrmse_pct"] = valid.get("nrmse_pct", rows[-1]["nrmse_pct"])
                rows[-1]["coverage_pct"] = valid.get("coverage_pct", rows[-1]["coverage_pct"])
                rows[-1]["val_mae_mw"] = valid.get("mae_mw", np.nan)
                rows[-1]["train_mae_mw"] = train.get("mae_mw", np.nan)
                rows[-1]["val_coverage_pct"] = valid.get("coverage_pct", np.nan)
                rows[-1]["train_coverage_pct"] = train.get("coverage_pct", np.nan)
        except Exception:
            pass

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--start", default="2020-12-01")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # ── Hourly + daily history ─────────────────────────────────────────────
    history, daily = build_national_history(days=args.days, start=args.start, seed=args.seed)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history.drop(columns=["date"], errors="ignore").to_csv(HISTORY_PATH, index=False)
    daily.to_csv(DAILY_PATH, index=False)
    print(f"Saved {len(history)} hourly national rows → {HISTORY_PATH}")
    print(f"Saved {len(daily)} daily summary rows   → {DAILY_PATH}")

    # Daylight-only stats
    daylight = history[history["actual_mw"] > 0.1]
    if not daylight.empty:
        mae = daylight["error_mw"].abs().mean()
        coverage = ((daylight["actual_mw"] >= daylight["forecast_p10_mw"]) &
                    (daylight["actual_mw"] <= daylight["forecast_p90_mw"])).mean() * 100
        print(f"Daylight MAE: {mae:.2f} MW · Coverage: {coverage:.1f}%")
    night = history[history["actual_mw"] <= 0.1]
    if not night.empty:
        print(f"Nighttime rows: {len(night)} (forecast zeroed, max fc={night['forecast_p50_mw'].max():.1f} MW)")

    # ── Training progression ───────────────────────────────────────────────
    progression = build_training_progression()
    progression.to_csv(PROGRESSION_PATH, index=False)
    print(f"Saved {len(progression)} training runs   → {PROGRESSION_PATH}")
    if not progression.empty:
        for _, row in progression.iterrows():
            promoted_tag = " ✅ PROMOTED" if row.get("promoted") else ""
            mae_str = f"{row['mae_mw']:.2f}" if pd.notna(row.get("mae_mw")) else "—"
            print(f"  Run {row['step']}: {row['run_id']}  MAE={mae_str} MW{promoted_tag}")


if __name__ == "__main__":
    main()
