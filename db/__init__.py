"""ESCANOR relational store: engine plumbing, ORM models and repository calls.

Public surface — import from here rather than from the submodules::

    from db import init_db, record_metering_observations, record_retraining_event

``DATABASE_URL`` selects the engine; the default is the file-backed SQLite
database at ``data.paths.DATABASE_PATH``. See :mod:`db.engine`.
"""

from __future__ import annotations

from db.engine import dispose_engine, get_engine, session_scope
from db.models import (
    Base,
    ForecastPrediction,
    MeteringObservation,
    ProsolDirection,
    ProsolDistrict,
    ProsolInstallationSize,
    ProsolInstallationUpdate,
    ProsolNationalMetric,
    ProsolPendingDossier,
    ProsolReport,
    RetrainingEvent,
)
from db.repository import (
    init_db,
    list_forecast_runs,
    prune_forecast_history,
    read_forecast_predictions,
    read_metering_frame,
    read_retraining_events,
    record_forecast_predictions,
    record_metering_observations,
    record_retraining_event,
    storage_overview,
)

__all__ = [
    "Base",
    "ForecastPrediction",
    "MeteringObservation",
    "ProsolDirection",
    "ProsolDistrict",
    "ProsolInstallationSize",
    "ProsolInstallationUpdate",
    "ProsolNationalMetric",
    "ProsolPendingDossier",
    "ProsolReport",
    "RetrainingEvent",
    "dispose_engine",
    "get_engine",
    "init_db",
    "list_forecast_runs",
    "prune_forecast_history",
    "read_forecast_predictions",
    "read_metering_frame",
    "read_retraining_events",
    "record_forecast_predictions",
    "record_metering_observations",
    "record_retraining_event",
    "session_scope",
    "storage_overview",
]
