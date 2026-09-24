"""
ML forecasting model: gradient-boosted quantile regression with
ensemble averaging and a native non-crossing uncertainty band.

Trains P10/P50/P90 quantile models so the platform can report both a point
forecast and an uncertainty band, as required by the concept note.

This module is the *public façade* of the forecast model. The implementation is
split across cohesive siblings and re-exported here, so every historic import
site (``from models.ml_forecast import predict``) keeps working:

  - ``models.training_config`` — quantiles, ensemble seeds, device, base params
  - ``models.features``        — the frozen feature contract
  - ``models.artifacts``       — model bundle persistence
  - ``models.training``        — ensemble fit and the Optuna study
  - ``models.inference``       — quantile ensemble → non-crossing band
  - ``models.evaluation``      — metrics and baseline backtests

Model improvements over the original implementation:
  - Solar physics features: cos_zenith, clearsky_index (solar position and
    cloud attenuation ratio for Tunisia ~35°N).
  - Cyclical hour encoding: hour_sin/hour_cos instead of integer-only hour.
  - Climate zone: 4-class Tunisian district classification (coastal north,
    central coastal, inland central, south) for spatial generalization.
  - Ensemble: 3 random seeds per quantile, averaged for variance reduction.
  - Non-crossing quantiles: symmetric band construction (p50 ± half_width)
    eliminates P10/P50/P90 crossing entirely; the reported band is the model's
    native quantile spread with no post-hoc correction.
  - Data quality gate: filters physically impossible rows before training.
  - Optuna hyperparameter tuning with temporal cross-validation.
  - Multi-baseline evaluation (persistence 24h/168h, clear-sky).
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

import pandas as pd

from data import paths
from data.climate import CLIMATE_ZONES, ZONE_IDS
from data.io import write_dataframe
from data.steg_districts import (
    DISTRICT_CAPACITY_LOOKUP,
    DISTRICT_DUST_LOOKUP,
    STEG_DISTRICTS,
)
from ingestion.synthetic_data import generate_all
from models.artifacts import FEATURE_COLUMNS_KEY, load_models, save_models
from models.evaluation import evaluate, evaluate_by_horizon_with_baselines
from models.features import (
    BASE_FEATURES,
    EXTENDED_FEATURES,
    FEATURE_COLS,
    PHYSICS_FEATURES,
    add_time_features,
    get_feature_cols,
    validate_training_data,
)
from models.inference import predict, raw_predict
from models.training import train_quantile_models, tune_hyperparameters
from models.training_config import (
    DEFAULT_PARAMS,
    ENSEMBLE_SEEDS,
    GPU_PARAMS,
    QUANTILES,
    USE_GPU,
    device_params,
    is_gpu_enabled,
)

# Legacy spellings kept for existing call sites and tests.
_CLIMATE_ZONES = CLIMATE_ZONES
_ZONE_IDS = ZONE_IDS
_maybe_gpu_params = device_params
_raw_predict = raw_predict

# Chronological split used by the standalone pipeline: everything before
# ``TRAIN_END`` trains, the tail tests.
TRAIN_END = pd.Timestamp("2024-10-01")
SYNTHETIC_TRAINING_START = "2023-01-01"
SYNTHETIC_TRAINING_END = "2025-01-01"
DEFAULT_TUNING_TRIALS = 20


def run_training_pipeline(output_model: Path | None = None, n_trials: int = DEFAULT_TUNING_TRIALS) -> dict:
    """End-to-end standalone training run on the synthetic district history.

    Returns the fitted model bundle; metrics are written to the locations
    declared in ``data.paths``.
    """
    print("Generating synthetic training data …")
    df = generate_all(STEG_DISTRICTS, start=SYNTHETIC_TRAINING_START, end=SYNTHETIC_TRAINING_END)
    df = validate_training_data(df, DISTRICT_CAPACITY_LOOKUP)
    capacity_lookup = DISTRICT_CAPACITY_LOOKUP
    dust_lookup = DISTRICT_DUST_LOOKUP

    train, test = df[df.timestamp < TRAIN_END], df[df.timestamp >= TRAIN_END]
    print(f"Train rows: {len(train):,}  Test rows: {len(test):,}")

    print(f"GPU training: {'ENABLED' if is_gpu_enabled() else 'DISABLED (CPU fallback)'}")

    print(f"Tuning hyperparameters (Optuna, {n_trials} trials)…")
    best_params = tune_hyperparameters(train, capacity_lookup, dust_lookup, n_trials=n_trials)
    print(f"Best params: { {k: v for k, v in best_params.items() if k != 'verbose'} }")

    print("Training ensemble quantile models (3 seeds × 3 quantiles)…")
    models = train_quantile_models(train, capacity_lookup, dust_lookup,
                                   params=best_params, use_ensemble=True)

    print("\nOverall backtest:")
    print(evaluate(models, test, capacity_lookup, dust_lookup))

    print("\nBy-horizon backtest (vs persistence 24h/168h & clear-sky):")
    horizon_metrics = evaluate_by_horizon_with_baselines(
        models, test, capacity_lookup, dust_lookup)
    print(horizon_metrics.to_string(index=False))

    write_dataframe(horizon_metrics, paths.TRAINING_METRICS_PATH)
    save_models(models, output_model or paths.MODEL_PATH)
    print("\nModels and metrics saved.")
    return models


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--output", type=Path, default=None,
                        help=f"Model bundle destination (default {paths.MODEL_PATH})")
    parser.add_argument("--trials", type=int, default=DEFAULT_TUNING_TRIALS,
                        help="Optuna hyperparameter trials")
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    run_training_pipeline(arguments.output, arguments.trials)


__all__ = [
    "BASE_FEATURES",
    "CLIMATE_ZONES",
    "DEFAULT_PARAMS",
    "ENSEMBLE_SEEDS",
    "EXTENDED_FEATURES",
    "FEATURE_COLS",
    "FEATURE_COLUMNS_KEY",
    "GPU_PARAMS",
    "PHYSICS_FEATURES",
    "QUANTILES",
    "USE_GPU",
    "ZONE_IDS",
    "add_time_features",
    "evaluate",
    "evaluate_by_horizon_with_baselines",
    "get_feature_cols",
    "is_gpu_enabled",
    "load_models",
    "predict",
    "run_training_pipeline",
    "save_models",
    "train_quantile_models",
    "tune_hyperparameters",
    "validate_training_data",
]
