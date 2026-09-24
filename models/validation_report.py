"""Build train-versus-validation metrics for the deployed PVGIS model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.history import _to_model_schema
from models.ml_forecast import load_models, predict, load_calibration

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "results" / "datasets" / "rooftop_actual_15min.csv"
MODEL_PATH = ROOT / "models" / "artifacts" / "quantile_models.joblib"
CALIBRATION_PATH = ROOT / "results" / "calibration.json"
REPORT_PATH = ROOT / "results" / "model_validation_metrics.json"


def _hourly_dataset() -> pd.DataFrame:
    raw = pd.read_csv(DATASET_PATH)
    raw["timestamp_utc"] = pd.to_datetime(raw["timestamp_utc"], utc=True).dt.floor("h").astype(str)
    numeric = [
        "power_kw", "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c",
        "cloud_cover_pct", "wind_speed_ms", "energy_kwh",
    ]
    hourly = raw.groupby(["timestamp_utc", "district", "direction"], as_index=False)[numeric].mean()
    return _to_model_schema(cast(pd.DataFrame, hourly))


def _split_metrics(models: dict[str, Any], frame: pd.DataFrame,
                    conformal_q: float = 0.0,
                    horizon_scales: dict | None = None) -> dict[str, Any]:
    predictions = predict(models, frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP,
                          conformal_q=conformal_q, horizon_scales=horizon_scales)
    actual = predictions["production_mw"].to_numpy(dtype=float)
    quantile_losses = []
    for quantile in (0.1, 0.5, 0.9):
        forecast = predictions[f"forecast_p{int(quantile * 100)}_mw"].to_numpy(dtype=float)
        error = actual - forecast
        quantile_losses.append(np.maximum(quantile * error, (quantile - 1) * error).mean())
    p50_error = predictions["forecast_p50_mw"] - predictions["production_mw"]
    daylight = predictions["production_mw"] > 0.01
    mae = float(p50_error[daylight].abs().mean()) if daylight.any() else 0.0
    rmse = float(np.sqrt((p50_error[daylight] ** 2).mean())) if daylight.any() else 0.0
    capacity_mw = sum(DISTRICT_CAPACITY_LOOKUP.values())
    nrmse = 100 * rmse / capacity_mw if capacity_mw else 0.0
    coverage = (
        (predictions["production_mw"] >= predictions["forecast_p10_mw"])
        & (predictions["production_mw"] <= predictions["forecast_p90_mw"])
    ).mean() * 100
    return {
        "pinball_loss": round(float(np.mean(quantile_losses)), 4),
        "mae_mw": round(mae, 4),
        "rmse_mw": round(rmse, 4),
        "nrmse_pct": round(float(nrmse), 4),
        "accuracy_pct": round(max(0.0, 100.0 - float(nrmse)), 4),
        "coverage_pct": round(float(coverage), 4),
        "samples": len(frame),
    }


def build_validation_report() -> dict[str, Any]:
    frame = _hourly_dataset()
    split = frame["timestamp"].quantile(0.8)
    train = cast(pd.DataFrame, frame[frame["timestamp"] < split])
    validation = cast(pd.DataFrame, frame[frame["timestamp"] >= split])
    models = load_models(str(MODEL_PATH))
    calibration = load_calibration(str(CALIBRATION_PATH))
    conformal_q = calibration.get("conformal_q", 0.0)
    horizon_scales = calibration.get("horizon_scales")
    report = {
        "source": "pvgis_district_model",
        "dataset_path": str(DATASET_PATH.relative_to(ROOT)),
        "model_path": str(MODEL_PATH.relative_to(ROOT)),
        "split_timestamp": str(split),
        "conformal_q": round(conformal_q, 4),
        "training": _split_metrics(models, train, conformal_q, horizon_scales),
        "validation": _split_metrics(models, validation, conformal_q, horizon_scales),
    }
    return report


def write_validation_report() -> dict[str, Any]:
    report = build_validation_report()
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(write_validation_report(), indent=2))
