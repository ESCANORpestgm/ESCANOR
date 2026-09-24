"""Rooftop-PV forecast model suite.

Layering (each module may import the ones above it, never below):
  - ``training_config`` — hyperparameters, quantiles, ensemble seeds, device.
  - ``features``        — the frozen model feature contract and derivations.
  - ``artifacts``       — joblib save/load of the fitted ensemble.
  - ``inference``       — raw and calibrated prediction.
  - ``training``        — quantile fitting and Optuna hyperparameter search.
  - ``calibration``     — conformal and per-horizon band calibration.
  - ``evaluation``      — metrics, pinball loss, baseline backtests.
  - ``pvgis_dataset``   — hourly PVGIS dataset loading in model schema.
  - ``aggregation``     — district → Direction → national band aggregation.
  - ``model_registry``  — file-based model version / training run catalogue.
  - ``retrain``         — drift detection and the continuous-learning loop.
  - ``history``         — national/daily track record for the dashboard.
  - ``validation_report`` — train-vs-validation metrics of the deployed model.
  - ``ml_forecast``     — façade re-exporting the above, kept for the original
    ``from models.ml_forecast import ...`` call sites.

Keep this ``__init__`` free of eager imports: ``models`` depends on ``data`` and
``ingestion``, and importing it at package level would slow the API startup.
"""
