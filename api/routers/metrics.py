"""Historical accuracy, model diagnostics, and training-info endpoints."""

import json
import math
from typing import Any, cast

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from api.config import CALIBRATION_PATH, MODEL_PATH
from api.services import get_calibration
from data.paths import (
    DAILY_HISTORY_PATH,
    NATIONAL_HISTORY_PATH,
    ROOFTOP_TRAINING_DATASET_PATH,
    TRAINING_METRICS_PATH,
    TRAINING_PROGRESSION_PATH,
    VALIDATION_METRICS_PATH,
    relative_to_project,
)
from models.artifacts import load_models
from models.ml_forecast import DEFAULT_PARAMS, ENSEMBLE_SEEDS, get_feature_cols, is_gpu_enabled

router = APIRouter(tags=["Diagnostics"])


# ── History ──────────────────────────────────────────────────────────────────


@router.get("/history/rooftop")
def rooftop_history_summary():
    path = ROOFTOP_TRAINING_DATASET_PATH
    if not path.exists():
        raise HTTPException(404, "No PVGIS rooftop dataset found.")
    frame = pd.read_csv(path)
    district_summary = frame.drop_duplicates(subset=["district"])
    return {
        "dataset_path": relative_to_project(path),
        "source": str(frame["source"].iloc[0]) if not frame.empty and "source" in frame.columns else "unknown",
        "rows": len(frame),
        "districts": int(cast(Any, frame["district"].nunique())),
        "pv_count": int(cast(Any, district_summary["pv_count"].sum())),
        "installed_capacity_kwp": float(cast(Any, district_summary["installed_capacity_kwp"].sum())),
        "start": str(frame["timestamp_utc"].min()),
        "end": str(frame["timestamp_utc"].max()),
    }


@router.get("/history/national")
def history_national():
    path = NATIONAL_HISTORY_PATH
    if not path.exists():
        raise HTTPException(404, "No history found — run `python -m models.history` first.")
    frame = pd.read_csv(path)
    if "forecast_mw" not in frame.columns and "forecast_p50_mw" in frame.columns:
        frame["forecast_mw"] = frame["forecast_p50_mw"]
    return frame.to_dict(orient="records")


@router.get("/history/daily")
def history_daily():
    """Return daily rolling accuracy, nRMSE, coverage, and bias."""
    path = DAILY_HISTORY_PATH
    if not path.exists():
        raise HTTPException(404, "No daily history found — run `python -m models.history` first.")
    return pd.read_csv(path).to_dict(orient="records")


# ── Metrics ──────────────────────────────────────────────────────────────────


@router.get("/metrics")
def metrics():
    path = TRAINING_METRICS_PATH
    if not path.exists():
        raise HTTPException(404, "No metrics found — run `python -m models.ml_forecast` first.")
    frame = pd.read_csv(path).rename(columns={
        "horizon": "horizon_bucket",
        "nRMSE_ours_%": "nrmse_ours_pct",
        "nRMSE_persistence_24h_%": "nrmse_persist_24h_pct",
        "nRMSE_persistence_168h_%": "nrmse_persist_168h_pct",
        "nRMSE_clearsky_%": "nrmse_clearsky_pct",
        "coverage_P10_P90_%": "coverage_pct",
        "n_samples": "samples",
    })
    # Best persistence = min of 24h and 168h baselines
    if "nrmse_persist_24h_pct" in frame.columns and "nrmse_persist_168h_pct" in frame.columns:
        frame["nrmse_persistence_pct"] = frame[["nrmse_persist_24h_pct", "nrmse_persist_168h_pct"]].min(axis=1)
    elif "nrmse_persist_24h_pct" in frame.columns:
        frame["nrmse_persistence_pct"] = frame["nrmse_persist_24h_pct"]
    return frame.to_dict(orient="records")


@router.get("/model/validation")
def model_validation():
    path = VALIDATION_METRICS_PATH
    if not path.exists():
        raise HTTPException(404, "No model validation metrics found — run python -m models.validation_report first.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "Model validation metrics could not be read.") from exc


# ── Model info ───────────────────────────────────────────────────────────────


@router.get("/model/training-progression")
def training_progression():
    """Return per-training-run progression showing how the model learned."""
    path = TRAINING_PROGRESSION_PATH
    if not path.exists():
        raise HTTPException(404, "No training progression found — run `python -m models.history` first.")
    frame = pd.read_csv(path)
    # Replace NaN/NaT with None for JSON serialization
    records = frame.to_dict(orient="records")
    for rec in records:
        for key, val in rec.items():
            if isinstance(val, float) and math.isnan(val):
                rec[key] = None
            elif isinstance(val, str) and val == "":
                rec[key] = None
    return records


@router.get("/model/training-info")
def model_training_info():
    """Return calibration data, feature importances, and training metadata."""
    # ── Calibration ─────────────────────────────────────────────────────────
    calibration = get_calibration()

    # ── Feature importances (averaged across ensemble P50 models) ───────────
    feature_importance: list[dict[str, Any]] = []
    model_info: dict[str, Any] = {
        "model_type": "LightGBM Quantile Regression",
        "quantiles": ["p10", "p50", "p90"],
        "ensemble_seeds": list(ENSEMBLE_SEEDS),
        "default_params": {k: v for k, v in DEFAULT_PARAMS.items() if k != "verbose"},
        "gpu_enabled": is_gpu_enabled(),
    }
    if MODEL_PATH.exists():
        try:
            models = load_models(MODEL_PATH)
            feature_cols = models.get("_feature_cols", get_feature_cols())
            p50_raw = models.get("p50", [])
            # Handle both single-model (legacy) and ensemble list formats
            p50_models = p50_raw if isinstance(p50_raw, list) else [p50_raw] if p50_raw is not None else []
            if p50_models:
                avg_importance = np.mean(
                    [getattr(m, "feature_importances_", np.zeros(len(feature_cols))) for m in p50_models],
                    axis=0,
                )
                feature_importance = sorted(
                    [
                        {"feature": name, "importance": round(float(imp), 4)}
                        for name, imp in zip(feature_cols, avg_importance)
                    ],
                    key=lambda x: x["importance"],
                    reverse=True,
                )
            model_info["feature_count"] = len(feature_cols)
            model_info["ensemble_size"] = len(p50_models)
        except Exception as exc:
            model_info["error"] = str(exc)
    else:
        model_info["model_exists"] = False

    return {
        "calibration": {
            "conformal_q": round(calibration.get("conformal_q", 0.0), 4),
            "horizon_scales": calibration.get("horizon_scales", {}),
            "calibration_file": relative_to_project(CALIBRATION_PATH),
            "exists": CALIBRATION_PATH.exists(),
        },
        "feature_importance": feature_importance,
        "model_info": model_info,
    }
