"""Repository functions — the only place that opens a database session.

Callers pass plain dicts / DataFrames and never see an ORM object, so the
storage engine stays swappable behind :func:`db.engine.get_engine`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd
from sqlalchemy import func, insert, select

from db.engine import get_engine, session_scope
from db.models import Base, MeteringObservation, RetrainingEvent


def init_db() -> None:
    """Create every table if absent.

    Intentionally idempotent so it can run at application startup, mirroring the
    ``initialize()`` it replaces. Schema *changes* after this should go through
    Alembic rather than rely on ``create_all``, which never alters existing
    tables.
    """
    Base.metadata.create_all(get_engine())


def _insert_ignore(session, rows: list[dict[str, Any]], model, conflict_columns: list[str]):
    """Insert ``rows``, skipping ones that violate the unique contract.

    Both SQLite and PostgreSQL expose the same ``on_conflict_do_nothing`` API on
    their dialect ``insert``, so only the module import differs; anything else
    falls back to filtering against the existing keys.
    """
    dialect = get_engine().dialect.name
    if dialect in {"sqlite", "postgresql"}:
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        statement = dialect_insert(model).values(rows)
        return statement.on_conflict_do_nothing(index_elements=conflict_columns)

    existing = {
        tuple(row)
        for row in session.execute(
            select(*(getattr(model, column) for column in conflict_columns))
        )
    }
    fresh = [row for row in rows if tuple(row.get(column) for column in conflict_columns) not in existing]
    return insert(model).values(fresh) if fresh else None


def record_metering_observations(rows: Iterable[Mapping[str, Any]]) -> int:
    """Store governorate metering rows, ignoring replays of known keys.

    Returns the number of rows offered. A row violating a ``CHECK`` (negative
    MW) raises :class:`sqlalchemy.exc.IntegrityError` and fails the whole batch
    — that is deliberate, so a malformed feed cannot half-write.
    """
    payload = [
        {
            "timestamp": str(row["timestamp"]),
            "governorate": str(row["governorate"]),
            "actual_mw": float(row["actual_mw"]),
            "forecast_p50_mw": (
                None if row.get("forecast_p50_mw") is None else float(row["forecast_p50_mw"])
            ),
            "received_at": str(row.get("received_at") or pd.Timestamp.now().isoformat()),
        }
        for row in rows
    ]
    if not payload:
        return 0

    with session_scope() as session:
        statement = _insert_ignore(
            session, payload, MeteringObservation, ["timestamp", "governorate"]
        )
        if statement is not None:
            session.execute(statement)
    return len(payload)


def read_metering_frame(since: str | None = None) -> pd.DataFrame:
    """Metering observations as a DataFrame, optionally from ``since`` (inclusive)."""
    statement = select(MeteringObservation).order_by(MeteringObservation.timestamp)
    if since:
        statement = statement.where(MeteringObservation.timestamp >= since)
    with session_scope() as session:
        rows = session.execute(statement).scalars().all()
    return pd.DataFrame(
        [
            {
                "timestamp": row.timestamp,
                "governorate": row.governorate,
                "actual_mw": row.actual_mw,
                "forecast_p50_mw": row.forecast_p50_mw,
                "received_at": row.received_at,
            }
            for row in rows
        ]
    )


def record_retraining_event(result: Mapping[str, Any]) -> None:
    """Append one retrain decision, keeping the full result as a JSON payload."""
    timestamp = str(result.get("timestamp") or pd.Timestamp.now().isoformat())
    with session_scope() as session:
        session.add(
            RetrainingEvent(
                timestamp=timestamp,
                source=str(result.get("source") or ""),
                retrained=bool(result.get("retrained")),
                candidate_promoted=bool(result.get("candidate_promoted")),
                payload=json.dumps(result, default=str, sort_keys=True),
            )
        )


def read_retraining_events(limit: int | None = 50) -> list[dict[str, Any]]:
    """Most recent retrain decisions, newest first, with the payload decoded."""
    statement = select(RetrainingEvent).order_by(RetrainingEvent.timestamp.desc())
    if limit:
        statement = statement.limit(limit)
    with session_scope() as session:
        rows = session.execute(statement).scalars().all()
    return [
        {
            "timestamp": row.timestamp,
            "source": row.source,
            "retrained": row.retrained,
            "candidate_promoted": row.candidate_promoted,
            "payload": json.loads(row.payload),
        }
        for row in rows
    ]


def storage_overview() -> dict[str, Any]:
    """Engine and row counts for every mapped table, for the diagnostics page.

    Iterated from the metadata rather than listed by hand, so a newly added model
    appears here without anyone remembering to extend this function.
    """
    engine = get_engine()
    with session_scope() as session:
        counts = {
            table.name: session.scalar(select(func.count()).select_from(table)) or 0
            for table in Base.metadata.sorted_tables
        }
    return {
        "url": engine.url.render_as_string(hide_password=True),
        "dialect": engine.dialect.name,
        "tables": counts,
        "row_total": sum(counts.values()),
    }
