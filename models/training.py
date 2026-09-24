"""Model fitting: ensemble quantile regression and the Optuna hyperparameter study."""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from models.artifacts import FEATURE_COLUMNS_KEY
from models.features import add_time_features, get_feature_cols
from models.training_config import (
    DEFAULT_PARAMS,
    ENSEMBLE_SEEDS,
    P50,
    QUANTILES,
    device_params,
)

# Expanding-window temporal cross-validation splits for the tuning study. Each
# pair is (train-end fraction, validation-end fraction); validation always
# follows the training window so no future row leaks into the fit.
TUNING_FOLDS = ((0.50, 0.65), (0.65, 0.80), (0.80, 0.95))
DEFAULT_TUNING_TRIALS = 30

# Search space of the tuning study, bounded by what is sensible for an hourly
# 19-feature tabular problem on district-aggregated data.
TUNING_SEARCH_SPACE = {
    "n_estimators": (200, 800),
    "max_depth": (4, 10),
    "learning_rate": (0.01, 0.1, True),
    "num_leaves": (15, 63),
    "min_child_samples": (10, 50),
    "subsample": (0.6, 1.0),
    "colsample_bytree": (0.6, 1.0),
    "reg_alpha": (1e-3, 10.0, True),
    "reg_lambda": (1e-3, 10.0, True),
}


def _fit_quantile(quantile: float, X: pd.DataFrame, y: pd.Series, params: dict, seed: int | None = None) -> LGBMRegressor:
    model = LGBMRegressor(
        objective="quantile", alpha=quantile, random_state=seed,
        **params, **device_params(),
    )
    model.fit(X, y)
    return model


def train_quantile_models(
    df: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
    params: dict | None = None,
    use_ensemble: bool = True,
) -> dict:
    """Train P10/P50/P90 gradient-boosted quantile regression models.

    When ``use_ensemble`` is True, trains ``len(ENSEMBLE_SEEDS)`` models per
    quantile with different random seeds and stores them as a list for averaged
    prediction, reducing variance and improving forecast stability.
    """
    df = add_time_features(df, capacity_lookup, dust_lookup)
    available = [c for c in get_feature_cols() if c in df.columns]
    X = df[available]
    y = df["production_mw"]
    base_params = {**DEFAULT_PARAMS, **(params or {})}

    models: dict = {}
    for label, q in QUANTILES.items():
        if use_ensemble:
            models[label] = [_fit_quantile(q, X, y, base_params, seed) for seed in ENSEMBLE_SEEDS]
        else:
            models[label] = [_fit_quantile(q, X, y, base_params)]
    models[FEATURE_COLUMNS_KEY] = available
    return models


def _temporal_folds(timestamps: pd.Series) -> list[tuple[pd.Series, pd.Series]]:
    """Build (train_mask, validation_mask) pairs that never look backwards."""
    folds = []
    for train_end, val_end in TUNING_FOLDS:
        cutoff = timestamps.quantile(train_end)
        train_mask = timestamps < cutoff
        val_mask = (timestamps >= cutoff) & (timestamps < timestamps.quantile(val_end))
        if train_mask.sum() > 0 and val_mask.sum() > 0:
            folds.append((train_mask, val_mask))
    return folds


def _trial_params(trial) -> dict:
    params = {}
    for name, spec in TUNING_SEARCH_SPACE.items():
        # Spec is (low, high) or (low, high, log); float bounds mean a float
        # draw, integer bounds an int draw. Length alone is ambiguous because
        # log-scale float specs also carry a third element.
        low, high = spec[0], spec[1]
        if isinstance(low, float) or isinstance(high, float):
            params[name] = trial.suggest_float(name, low, high, log=len(spec) == 3 and bool(spec[2]))
        else:
            params[name] = trial.suggest_int(name, int(low), int(high))
    params["verbose"] = -1
    return params


def tune_hyperparameters(
    df: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
    n_trials: int = DEFAULT_TUNING_TRIALS,
) -> dict:
    """Optuna-based hyperparameter search with expanding-window temporal CV.

    Optimises mean absolute P50 error on out-of-sample future windows. Falls
    back to ``DEFAULT_PARAMS`` when Optuna is not installed or the data is too
    short to split.
    """
    try:
        import optuna
    except ImportError:
        return DEFAULT_PARAMS

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    df = add_time_features(df, capacity_lookup, dust_lookup)
    available = [c for c in get_feature_cols() if c in df.columns]
    fold_splits = _temporal_folds(df["timestamp"])
    if not fold_splits:
        return DEFAULT_PARAMS

    def objective(trial) -> float:
        params = {**_trial_params(trial), **device_params()}
        scores = []
        for train_mask, val_mask in fold_splits:
            model = LGBMRegressor(objective="quantile", alpha=QUANTILES[P50], **params)
            model.fit(df.loc[train_mask, available], df.loc[train_mask, "production_mw"])
            preds = np.clip(model.predict(df.loc[val_mask, available]), 0, None)
            scores.append(float(np.mean(np.abs(preds - df.loc[val_mask, "production_mw"]))))
        return float(np.mean(scores))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return {**DEFAULT_PARAMS, **study.best_params}


__all__ = [
    "DEFAULT_TUNING_TRIALS",
    "TUNING_FOLDS",
    "TUNING_SEARCH_SPACE",
    "train_quantile_models",
    "tune_hyperparameters",
]
