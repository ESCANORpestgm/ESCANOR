"""LightGBM training configuration: quantile targets, ensemble and device choice.

Separated from the learning code so that the API (``/metrics``), the retraining
jobs and the tuning study all read the *same* knobs from one place.
"""

from __future__ import annotations

import numpy as np
from lightgbm import LGBMRegressor

# Output quantiles of the platform: a low/mid/high band per forecast point.
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
P10, P50, P90 = "p10", "p50", "p90"

# Ensemble seeds averaged per quantile; more seeds reduce prediction variance
# at a linear training-cost increase.
ENSEMBLE_SEEDS = [42, 123, 456]

# ── GPU training ─────────────────────────────────────────────────────────────
# Set USE_GPU = True to enable GPU-accelerated training (requires CUDA/OpenCL).
# Benchmarked on RTX 4060 Laptop: CPU is faster for datasets < 500k rows with
# shallow trees (max_depth=6) and 19 features. GPU benefits kick in at > 1M rows
# or very wide feature spaces. Use "auto" to probe GPU availability at startup.
USE_GPU: bool | str = True   # True | False | "auto"

GPU_PARAMS = dict(
    device_type="gpu",
    gpu_platform_id=0,
    gpu_device_id=0,
    gpu_use_dp=True,   # double precision for quantile regression accuracy
)

# Baseline hyperparameters; the Optuna study in ``models.training`` may override
# any of them, and ``models.retrain`` compares new candidates against these.
DEFAULT_PARAMS = dict(
    n_estimators=400, max_depth=6, learning_rate=0.04,
    num_leaves=31, min_child_samples=20,
    subsample=0.85, colsample_bytree=0.85,
    reg_alpha=0.1, reg_lambda=0.1,
    verbose=-1,
)

_GPU_READY: bool | None = None  # lazily evaluated, "auto" mode only


def _gpu_available() -> bool:
    """Probe whether LightGBM can train on GPU (one quick fit)."""
    try:
        probe = LGBMRegressor(n_estimators=2, verbose=-1, **GPU_PARAMS)
        probe.fit(np.zeros((10, 3)), np.zeros(10))
        return True
    except Exception:
        return False


def is_gpu_enabled() -> bool:
    """Return True if GPU training is active."""
    global _GPU_READY
    if USE_GPU is True:
        return True
    if USE_GPU is False:
        return False
    if _GPU_READY is None:
        _GPU_READY = _gpu_available()
    return _GPU_READY


def device_params() -> dict:
    """Extra LightGBM kwargs for the selected device (empty on CPU)."""
    return dict(GPU_PARAMS) if is_gpu_enabled() else {}


__all__ = [
    "DEFAULT_PARAMS",
    "ENSEMBLE_SEEDS",
    "GPU_PARAMS",
    "P10",
    "P50",
    "P90",
    "QUANTILES",
    "USE_GPU",
    "device_params",
    "is_gpu_enabled",
]
