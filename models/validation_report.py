"""Build train-versus-validation metrics for the deployed PVGIS model.

Scores the deployed quantile ensemble on the 80/20 temporal split of the PVGIS
district dataset and persists the result as ``model_validation_metrics.json``.

Run:
    python -m models.validation_report
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
from typing import Any, cast

import numpy as np
import pandas as pd

from data.io import write_json_atomic
from data.paths import (
    MODEL_PATH,
    ROOFTOP_TRAINING_DATASET_PATH,
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
from models.pvgis_dataset import load_hourly_dataset

# Quantiles scored by the pinball loss, and the column each one maps to
REPORT_QUANTILES = (0.1, 0.5, 0.9)
# Temporal split: the last 20% of the dataset is held out for validation
VALIDATION_FRACTION = 0.8
# Production above this threshold counts as daylight when scoring
MIN_DAYLIGHT_PRODUCTION_MW = 0.01


def _column_for(quantile: float) -> str:
    return {0.1: FORECAST_P10_COLUMN, 0.5: FORECAST_P50_COLUMN, 0.9: FORECAST_P90_COLUMN}[quantile]


def _split_metrics(models: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    predictions = predict(models, frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP)
    actual = predictions["production_mw"].to_numpy(dtype=float)
    quantile_losses = []
    for quantile in REPORT_QUANTILES:
        forecast = predictions[_column_for(quantile)].to_numpy(dtype=float)
        error = actual - forecast
        quantile_losses.append(np.maximum(quantile * error, (quantile - 1) * error).mean())
    p50_error = predictions[FORECAST_P50_COLUMN] - predictions["production_mw"]
    daylight = predictions["production_mw"] > MIN_DAYLIGHT_PRODUCTION_MW
    mae = float(p50_error[daylight].abs().mean()) if daylight.any() else 0.0
    rmse = float(np.sqrt((p50_error[daylight] ** 2).mean())) if daylight.any() else 0.0
    capacity_mw = sum(DISTRICT_CAPACITY_LOOKUP.values())
    nrmse = 100 * rmse / capacity_mw if capacity_mw else 0.0
    coverage = (
        (predictions["production_mw"] >= predictions[FORECAST_P10_COLUMN])
        & (predictions["production_mw"] <= predictions[FORECAST_P90_COLUMN])
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
    # Weather-only frame: no ``horizon_hours`` column, so the feature builder
    # derives it from the timestamp — exactly how the deployed report was scored.
    frame = load_hourly_dataset(include_descriptive_columns=False)
    split = frame["timestamp"].quantile(VALIDATION_FRACTION)
    train = cast(pd.DataFrame, frame[frame["timestamp"] < split])
    validation = cast(pd.DataFrame, frame[frame["timestamp"] >= split])
    models = load_models(MODEL_PATH)
    return {
        "source": "pvgis_district_model",
        "dataset_path": relative_to_project(ROOFTOP_TRAINING_DATASET_PATH),
        "model_path": relative_to_project(MODEL_PATH),
        "split_timestamp": str(split),
        "training": _split_metrics(models, train),
        "validation": _split_metrics(models, validation),
    }


def write_validation_report() -> dict[str, Any]:
    """Build the report and persist it atomically to the registry location."""
    report = build_validation_report()
    write_json_atomic(VALIDATION_METRICS_PATH, report)
    return report


if __name__ == "__main__":
    print(json.dumps(write_validation_report(), indent=2))
