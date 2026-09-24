"""Build reproducible aggregate rooftop-PV forecast history for the dashboard.

Generates three output files:
  - history_national.csv     — hourly actual vs forecast (nighttime zeroed)
  - history_daily.csv         — daily rolling accuracy / nRMSE / coverage
  - training_progression.csv — per-training-run metrics showing model learning

Run:
    python -m models.history --days 30
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from data.io import read_json, write_dataframe
from data.paths import (
    DAILY_HISTORY_PATH,
    MODEL_PATH,
    NATIONAL_HISTORY_PATH,
    REGISTRY_DIR,
    RETRAIN_LOG_PATH,
    ROOFTOP_TRAINING_DATASET_PATH,
    TRAINING_PROGRESSION_PATH,
    VALIDATION_METRICS_PATH,
    relative_to_project,
)
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.artifacts import load_models
from models.inference import (
    FORECAST_P10_COLUMN,
    FORECAST_P50_COLUMN,
    FORECAST_P90_COLUMN,
    predict,
)
from models.pvgis_dataset import resample_hourly, to_model_schema

# GHI threshold below which forecasts are zeroed (nighttime / overcast-dark)
GHI_NIGHT_THRESHOLD = 1.0  # W/m²
# Hourly national rows counted as daylight when evaluating accuracy
DAYLIGHT_MIN_ACTUAL_MW = 0.1
TRAINING_RUNS_PATH = REGISTRY_DIR / "training_runs.json"


def _select_window(dataset_path: Path, start: str, days: int) -> pd.DataFrame:
    """15-minute rows of ``[start, start + days)`` — the evaluation window."""
    if not dataset_path.is_file():
        raise FileNotFoundError(f"PVGIS dataset not found: {dataset_path}")
    raw = pd.read_csv(dataset_path)
    timestamps = pd.to_datetime(raw["timestamp_utc"], utc=True)
    window_start = pd.Timestamp(start, tz="UTC")
    window_end = window_start + pd.Timedelta(days=days)
    selected = raw.loc[(timestamps >= window_start) & (timestamps < window_end)].copy()
    if selected.empty:
        raise ValueError(f"No PVGIS rows found between {start} and {window_end.date()}")
    return selected


def build_national_history(
    days: int = 30,
    start: str = "2020-12-01",
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate the deployed model against the PVGIS district dataset.

    Returns (hourly_national, daily_summary) DataFrames.
    """
    del seed  # Retained for CLI compatibility; PVGIS data is deterministic.
    dataset = resample_hourly(_select_window(ROOFTOP_TRAINING_DATASET_PATH, start, days))
    model_frame = to_model_schema(dataset)
    models = load_models(MODEL_PATH)
    predictions = cast(pd.DataFrame, predict(
        models, model_frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP,
    ))

    # ── Nighttime zeroing: when GHI ≈ 0, no solar production is possible ────
    night_mask = predictions["ghi_wm2"] < GHI_NIGHT_THRESHOLD
    predictions.loc[night_mask, [FORECAST_P50_COLUMN, FORECAST_P10_COLUMN, FORECAST_P90_COLUMN]] = 0.0

    national = cast(pd.DataFrame, predictions.groupby("timestamp", as_index=False).agg(
        actual_mw=("production_mw", "sum"),
        **{
            column: (column, "sum")
            for column in (FORECAST_P50_COLUMN, FORECAST_P10_COLUMN, FORECAST_P90_COLUMN)
        },
    ))
    national["error_mw"] = national[FORECAST_P50_COLUMN] - national["actual_mw"]
    actual = cast(pd.Series, national["actual_mw"])
    national["error_pct"] = (100 * national["error_mw"] / actual.replace(0, np.nan)).fillna(0)
    national["source"] = str(dataset["source"].iloc[0]) if "source" in dataset.columns else "pvgis_district_model"
    national["dataset_path"] = relative_to_project(ROOFTOP_TRAINING_DATASET_PATH)

    # ── Daily rolling metrics ────────────────────────────────────────────────
    national["date"] = pd.to_datetime(national["timestamp"]).dt.date
    daylight = national[national["actual_mw"] > DAYLIGHT_MIN_ACTUAL_MW].copy()
    daylight["abs_error"] = daylight["error_mw"].abs()
    daylight["sq_error"] = daylight["error_mw"] ** 2
    daylight["in_band"] = (
        (daylight["actual_mw"] >= daylight[FORECAST_P10_COLUMN]) &
        (daylight["actual_mw"] <= daylight[FORECAST_P90_COLUMN])
    ).astype(int)

    daily = daylight.groupby("date", as_index=False).agg(
        hours=("actual_mw", "count"),
        total_actual_mwh=("actual_mw", "sum"),
        total_forecast_mwh=(FORECAST_P50_COLUMN, "sum"),
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
        runs = read_json(TRAINING_RUNS_PATH, default=[]) or []
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
    if VALIDATION_METRICS_PATH.exists():
        try:
            val = read_json(VALIDATION_METRICS_PATH, default={}) or {}
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
    write_dataframe(history.drop(columns=["date"], errors="ignore"), NATIONAL_HISTORY_PATH)
    write_dataframe(daily, DAILY_HISTORY_PATH)
    print(f"Saved {len(history)} hourly national rows → {NATIONAL_HISTORY_PATH}")
    print(f"Saved {len(daily)} daily summary rows   → {DAILY_HISTORY_PATH}")

    # Daylight-only stats
    daylight = history[history["actual_mw"] > DAYLIGHT_MIN_ACTUAL_MW]
    if not daylight.empty:
        mae = daylight["error_mw"].abs().mean()
        coverage = ((daylight["actual_mw"] >= daylight[FORECAST_P10_COLUMN]) &
                    (daylight["actual_mw"] <= daylight[FORECAST_P90_COLUMN])).mean() * 100
        print(f"Daylight MAE: {mae:.2f} MW · Coverage: {coverage:.1f}%")
    night = history[history["actual_mw"] <= DAYLIGHT_MIN_ACTUAL_MW]
    if not night.empty:
        print(f"Nighttime rows: {len(night)} (forecast zeroed, max fc={night[FORECAST_P50_COLUMN].max():.1f} MW)")

    # ── Training progression ───────────────────────────────────────────────
    progression = build_training_progression()
    write_dataframe(progression, TRAINING_PROGRESSION_PATH)
    print(f"Saved {len(progression)} training runs   → {TRAINING_PROGRESSION_PATH}")
    if not progression.empty:
        for _, row in progression.iterrows():
            promoted_tag = " ✅ PROMOTED" if row.get("promoted") else ""
            mae_str = f"{row['mae_mw']:.2f}" if pd.notna(row.get("mae_mw")) else "—"
            print(f"  Run {row['step']}: {row['run_id']}  MAE={mae_str} MW{promoted_tag}")


if __name__ == "__main__":
    main()
