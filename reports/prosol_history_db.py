"""Relational persistence for immutable official Prosol rooftop-PV snapshots.

Snapshots are stored in the shared ESCANOR store selected by
``data.paths.database_url()``, through the pooled engine in ``db.engine``, next
to ``metering_observations`` and ``retraining_events``. They used to live in a
second file, ``results/prosol/prosol_history.db``, opened with a fresh
``sqlite3.Connection`` per query; routing them through ``db`` retires that store
and the connection leak that came with its ``with sqlite3.connect(...)`` pattern.

Function signatures and return shapes are unchanged, so ``api/routers/reports.py``
and the dashboard need no adjustment. The ``db_path`` parameters are still
accepted and now ignored: which database is used is a deployment decision
(``DATABASE_URL``), not a per-call one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from data.paths import DATABASE_PATH, PROSOL_SNAPSHOT_DIR
from data.prosol_report_schema import SNAPSHOT_SCOPE
from db.engine import get_engine, session_scope
from db.models import (
    ProsolDirection,
    ProsolDistrict,
    ProsolInstallationSize,
    ProsolNationalMetric,
    ProsolPendingDossier,
    ProsolReport,
)
from db.repository import init_db

# Kept for call-site compatibility. Reports where the store is a file; under a
# server engine there is no path, but the value is only ever echoed back to
# import_snapshot, which ignores it.
DEFAULT_DB_PATH = DATABASE_PATH
DEFAULT_SNAPSHOT_DIR = PROSOL_SNAPSHOT_DIR

# Content-addressed identity of a snapshot: prefix + leading hex of its SHA-256
SNAPSHOT_ID_PREFIX = "prosol_"
SNAPSHOT_ID_LENGTH = 16
SNAPSHOT_GLOB = "prosol_*.json"
# Comparison files are derived from snapshots and must not be imported as such
COMPARISON_SUFFIX = "_comparison.json"

# Payload array -> child model. Mirrors the arrays that were spread into the
# four payload tables of the legacy schema.
CHILD_MODELS: dict[str, type] = {
    "directions": ProsolDirection,
    "districts": ProsolDistrict,
    "installation_sizes": ProsolInstallationSize,
    "pending_dossiers": ProsolPendingDossier,
}


def connect():
    """A raw connection to the shared store, for ad-hoc SQL and CLI use.

    Returns a SQLAlchemy ``Connection``, not the ``sqlite3.Connection`` this
    function used to hand back: raw SQL needs ``execute(text("..."))`` and the
    caller must close it. Application code should prefer ``session_scope()``,
    which commits, rolls back and closes.
    """
    return get_engine().connect()


def initialize(db_path: Path | None = None) -> None:
    """Create the Prosol tables if they are missing.

    Goes through ``db.repository.init_db``, which also guarantees the metering
    and retraining tables exist — one ``create_all`` call for the whole store.
    Note it only creates: adding a column to an existing store needs a migration.
    """
    init_db()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return SNAPSHOT_ID_PREFIX + hashlib.sha256(canonical).hexdigest()[:SNAPSHOT_ID_LENGTH]


def import_snapshot(snapshot_path: Path, db_path: Path | None = None) -> tuple[str, bool]:
    # Strict on purpose: a snapshot is content-addressed, so an unreadable file
    # must abort the import instead of silently receiving a bogus identifier.
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot_id = _snapshot_id(payload)
    initialize()

    with session_scope() as session:
        already_there = session.scalar(
            select(ProsolReport.snapshot_id).where(ProsolReport.snapshot_id == snapshot_id)
        )
        if already_there:
            return snapshot_id, False

        reconciliation = payload.get("reconciliation", {})
        session.add(
            ProsolReport(
                snapshot_id=snapshot_id,
                report_period=payload.get("report_period", "unknown"),
                emission_date=payload.get("emission_date"),
                source_file=payload.get("source_file", snapshot_path.name),
                imported_at=datetime.now(timezone.utc).isoformat(),
                scope=payload.get("scope", SNAPSHOT_SCOPE),
                reconciliation_passed=bool(reconciliation.get("passed", False)),
                snapshot_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        # The parent must be on the table before any child is staged: these mappers
        # carry no relationship(), so the unit of work does not order them by the
        # foreign key and would otherwise emit a child INSERT first and abort on it.
        session.flush()

        for row_order, row in enumerate(payload.get("national_rows", [])):
            session.add(
                ProsolNationalMetric(
                    snapshot_id=snapshot_id,
                    row_order=row_order,
                    name=row.get("name", ""),
                    unit=row.get("unit"),
                    current_month=_number(row.get("current_month")),
                    previous_year_month=_number(row.get("previous_year_month")),
                    variance_month_pct=_number(row.get("variance_month_pct")),
                    current_year_to_date=_number(row.get("current_year_to_date")),
                    previous_year_to_date=_number(row.get("previous_year_to_date")),
                    variance_ytd_pct=_number(row.get("variance_ytd_pct")),
                    since_program_start=_number(row.get("since_program_start")),
                )
            )

        for payload_key, model in CHILD_MODELS.items():
            for row_order, row in enumerate(payload.get(payload_key, [])):
                session.add(
                    model(
                        snapshot_id=snapshot_id,
                        row_order=row_order,
                        payload_json=json.dumps(row, ensure_ascii=False),
                    )
                )

    return snapshot_id, True


def import_generated_snapshots(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    initialize()
    results = []
    for snapshot_path in sorted(Path(snapshot_dir).glob(SNAPSHOT_GLOB)):
        if snapshot_path.name.endswith(COMPARISON_SUFFIX):
            continue
        snapshot_id, inserted = import_snapshot(snapshot_path)
        results.append({"snapshot_id": snapshot_id, "source": snapshot_path.name, "inserted": inserted})
    return results


def list_reports(db_path: Path | None = None) -> list[dict[str, Any]]:
    initialize()
    statement = select(ProsolReport).order_by(
        ProsolReport.report_period.desc(),
        ProsolReport.emission_date.desc(),
        ProsolReport.imported_at.desc(),
    )
    with session_scope() as session:
        rows = session.scalars(statement).all()
    return [
        {
            "snapshot_id": row.snapshot_id,
            "report_period": row.report_period,
            "emission_date": row.emission_date,
            "source_file": row.source_file,
            "imported_at": row.imported_at,
            "scope": row.scope,
            # 0/1, exactly as the sqlite3.Row wire format served it: the column
            # is Boolean for server engines, the JSON contract stays integer.
            "reconciliation_passed": int(row.reconciliation_passed),
        }
        for row in rows
    ]


def get_report(snapshot_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    initialize()
    with session_scope() as session:
        row = session.scalar(
            select(ProsolReport).where(ProsolReport.snapshot_id == snapshot_id)
        )
        if row is None:
            return None
        # Copied out before the session closes, so the detached object is never touched.
        stored = row.snapshot_json
        imported_at = row.imported_at
        passed = row.reconciliation_passed

    payload = json.loads(stored)
    payload["snapshot_id"] = snapshot_id
    payload["database"] = {
        "imported_at": imported_at,
        "reconciliation_passed": bool(passed),
    }
    return payload
