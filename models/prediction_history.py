"""Persistence of issued forecast runs — the prediction history store.

The API serves forecasts from an in-memory cache that lives minutes, so the
question "what did we predict for this hour, as of when?" was unanswerable
after a restart. Every completed forecast run is flattened here into the
``forecast_predictions`` table at national, direction and district level,
keyed by the hour it was issued in, which makes repeated refreshes inside
the same hour idempotent.

Writing history must never break serving: :func:`persist_forecast_run`
degrades to a warning like the other startup/background writers in the
platform, and retention (``db.repository.prune_forecast_history``) bounds the
store on every write.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from db.repository import list_forecast_runs, read_forecast_predictions, record_forecast_predictions
from models.aggregation import (
    LEVEL_DIRECTION,
    LEVEL_NATIONAL,
    LEVEL_STEG_DISTRICT,
    TIMESTAMP_COLUMN,
    aggregate,
)

# Stored aggregation levels, finest kept last so the national rollup is cheap.
HISTORY_LEVELS: tuple[str, ...] = (LEVEL_NATIONAL, LEVEL_DIRECTION, LEVEL_STEG_DISTRICT)
NATIONAL_LOCATION = "NATIONAL"
# The raw district column of an aggregate frame is whichever spatial key exists.
_FORECAST_COLUMNS = {"forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw"}
RETENTION_HORIZON_DAYS = 4


def _location_column(frame: pd.DataFrame, level: str) -> str | None:
    """Name of the spatial label column an aggregate() level produced."""
    if level == LEVEL_NATIONAL:
        return None
    candidates = [
        column
        for column in frame.columns
        if column not in _FORECAST_COLUMNS and column != TIMESTAMP_COLUMN
    ]
    return candidates[0] if candidates else None


def run_rows(
    forecast: pd.DataFrame, level: str, issued_at: pd.Timestamp, data_source: str
) -> list[dict[str, Any]]:
    """Flatten one aggregation level of a forecast run into store-ready rows."""
    frame = aggregate(forecast, level)
    location_column = _location_column(frame, level)
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        target = pd.Timestamp(record[TIMESTAMP_COLUMN])
        rows.append(
            {
                "issued_at": issued_at.isoformat(),
                "level": level,
                "location": (
                    NATIONAL_LOCATION if location_column is None
                    else str(record[location_column]).upper()
                ),
                "target_timestamp": target.isoformat(),
                "forecast_p10_mw": float(record["forecast_p10_mw"]),
                "forecast_p50_mw": float(record["forecast_p50_mw"]),
                "forecast_p90_mw": float(record["forecast_p90_mw"]),
                "horizon_hours": int(round((target - issued_at).total_seconds() / 3600)),
                "data_source": data_source,
            }
        )
    return rows


def persist_forecast_run(forecast: pd.DataFrame, issued_at: Any, data_source: str) -> int:
    """Store every aggregation level of one issued forecast run.

    Returns the number of rows offered (duplicates inside the same issue hour
    are counted but not re-written). Failures are logged and swallowed: a
    storage problem must not take down the forecast endpoint that only wants
    to answer the request. A level that the forecast frame cannot support (no
    district column, say) is skipped so the coarser levels still get saved.
    """
    try:
        stamp = pd.Timestamp(issued_at)
        rows: list[dict[str, Any]] = []
        for level in HISTORY_LEVELS:
            try:
                rows.extend(run_rows(forecast, level, stamp, data_source))
            except (KeyError, ValueError) as error:
                print(f"[prediction history] level '{level}' unavailable: {error}")
        return record_forecast_predictions(rows)
    except Exception as error:  # noqa: BLE001 - deliberate graceful degradation
        print(f"[prediction history] could not save forecast run: {error}")
        return 0


def history_span() -> str:
    """ISO date ``RETENTION_HORIZON_DAYS`` back from now, as an ISO string.

    Predictions are only meaningful against a horizon the model actually
    issues (J..J+3); querying further back than the retention window simply
    returns nothing, so the dashboard asks for a bounded recent slice.
    """
    return (pd.Timestamp.now() - pd.Timedelta(days=RETENTION_HORIZON_DAYS)).isoformat()


def load_history(
    level: str | None = None,
    location: str | None = None,
    issued_at: str | None = None,
    since: str | None = None,
) -> pd.DataFrame:
    """Stored predictions, newest run first within each target hour."""
    frame = read_forecast_predictions(
        level=level, location=location, since=since or history_span(), issued_at=issued_at
    )
    if frame.empty:
        return frame
    return frame.sort_values(["target_timestamp", "issued_at"]).reset_index(drop=True)


def available_runs() -> list[dict[str, Any]]:
    """Issued runs on record, newest first."""
    return list_forecast_runs()
