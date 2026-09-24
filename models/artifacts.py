"""Persistence of trained model bundles.

A bundle is a plain dict ``{"p10": [...], "p50": [...], "p90": [...],
"_feature_cols": [...]}`` pickled with joblib. Keeping the (de)serialisation in
one place lets ``models.model_registry`` and ``models.retrain`` store candidate
bundles without duplicating the file handling.

joblib unpickles arbitrary Python objects, so only bundles produced by this
project's own training runs may ever be loaded — never drop in a file from an
untrusted source.
"""

from __future__ import annotations

from pathlib import Path

import joblib

from data.paths import MODEL_PATH

# Key under which a bundle records the feature columns it was fitted on; the
# loader must rebuild exactly those, not the current default list.
FEATURE_COLUMNS_KEY = "_feature_cols"


def save_models(models: dict, path: str | Path | None = None) -> Path:
    """Pickle a trained model bundle, creating its parent directory."""
    target = Path(path or MODEL_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, target)
    return target


def load_models(path: str | Path | None = None) -> dict:
    """Load a trained model bundle from disk."""
    return joblib.load(Path(path or MODEL_PATH))


__all__ = ["FEATURE_COLUMNS_KEY", "MODEL_PATH", "load_models", "save_models"]
