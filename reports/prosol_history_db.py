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

from sqlalchemy import delete, select, update

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

# The identity covers the official figures only. ``reconciliation`` is the check
# the importer runs *over* those figures and ``source_file`` is the name the
# export arrived under; both changed between importer versions and between the
# two March-2026 exports without a single reported number changing, and hashing
# them minted a fresh address for identical content. The history then offered
# several entries labelled "2026-03 — prosol_mars_2026_2.txt" that no reader
# could tell apart.
IDENTITY_EXCLUDED_KEYS = frozenset({"reconciliation", "source_file"})

# Payload array -> child model. Mirrors the arrays that were spread into the
# four payload tables of the legacy schema.
CHILD_MODELS: dict[str, type] = {
    "directions": ProsolDirection,
    "districts": ProsolDistrict,
    "installation_sizes": ProsolInstallationSize,
    "pending_dossiers": ProsolPendingDossier,
}

# Every table a snapshot row owns, parent first: the dedupe sweep below re-points
# and removes them as one unit.
SNAPSHOT_TABLES: tuple[type, ...] = (ProsolReport, ProsolNationalMetric, *CHILD_MODELS.values())


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
    core = {key: value for key, value in payload.items() if key not in IDENTITY_EXCLUDED_KEYS}
    canonical = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
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


def _delete_snapshot(session, snapshot_id: str) -> None:
    """Remove one snapshot and every row it owns (children first, then the parent)."""
    for model in reversed(SNAPSHOT_TABLES):
        session.execute(delete(model).where(model.snapshot_id == snapshot_id))


def _rekey_snapshot(session, old_id: str, new_id: str) -> None:
    """Move a snapshot and its children onto a different address."""
    for model in SNAPSHOT_TABLES:
        session.execute(update(model).where(model.snapshot_id == old_id).values(snapshot_id=new_id))


# The sweep is idempotent and only ever corrects historical rows, so one pass per
# process is enough — the history endpoint would otherwise re-parse every stored
# payload on each request.
_dedupe_applied = False


def dedupe_snapshots() -> dict[str, int]:
    """Collapse stored rows that hold the same official figures under two addresses.

    Snapshot addresses used to cover the whole payload, including the derived
    ``reconciliation`` block and the export filename, so an importer upgrade or a
    second export of the same month produced a second immutable snapshot of
    identical numbers. Every stored row is re-addressed with the content rule and
    one canonical row per content is kept: the row that already carries the right
    address, otherwise the one with the most complete reconciliation block, then
    the freshest import.
    """
    global _dedupe_applied
    initialize()

    # Read and write in separate transactions: the store is single-writer SQLite,
    # so a second writer opened while this one runs would block on its own lock.
    with session_scope() as session:
        stored = session.execute(
            select(ProsolReport.snapshot_id, ProsolReport.imported_at, ProsolReport.snapshot_json)
        ).all()

    groups: dict[str, list[dict[str, Any]]] = {}
    for snapshot_id, imported_at, snapshot_json in stored:
        try:
            payload = json.loads(snapshot_json)
        except json.JSONDecodeError:
            # A row that cannot be parsed has no computable content address; it is
            # reported rather than removed, so the sweep never destroys evidence.
            print(f"[prosol history] snapshot {snapshot_id} is not valid JSON; left as stored")
            continue
        groups.setdefault(_snapshot_id(payload), []).append({
            "snapshot_id": snapshot_id,
            "imported_at": imported_at,
            "reconciliation_fields": len(payload.get("reconciliation") or {}),
        })

    summary = {"rekeyed": 0, "removed": 0}
    with session_scope() as session:
        for address, members in groups.items():
            if len(members) == 1 and members[0]["snapshot_id"] == address:
                continue
            members.sort(
                key=lambda row: (
                    row["snapshot_id"] == address,
                    row["reconciliation_fields"],
                    row["imported_at"],
                    row["snapshot_id"],
                ),
                reverse=True,
            )
            for loser in members[1:]:
                _delete_snapshot(session, loser["snapshot_id"])
                summary["removed"] += 1
            keeper = members[0]["snapshot_id"]
            if keeper != address:
                _rekey_snapshot(session, keeper, address)
                summary["rekeyed"] += 1
    return summary


def import_generated_snapshots(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    global _dedupe_applied
    initialize()
    results = []
    paths = [path for path in Path(snapshot_dir).glob(SNAPSHOT_GLOB) if not path.name.endswith(COMPARISON_SUFFIX)]
    # Newest export first: when the same month arrives under several filenames the
    # one that wins the address is the provenance the operator just imported.
    for snapshot_path in sorted(paths, key=lambda path: (path.stat().st_mtime, path.name), reverse=True):
        snapshot_id, inserted = import_snapshot(snapshot_path)
        results.append({"snapshot_id": snapshot_id, "source": snapshot_path.name, "inserted": inserted})
    if not _dedupe_applied:
        summary = dedupe_snapshots()
        _dedupe_applied = True
        if summary["removed"] or summary["rekeyed"]:
            print(
                f"[prosol history] collapsed {summary['removed']} duplicate snapshot row(s), "
                f"re-addressed {summary['rekeyed']}"
            )
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


def latest_report(db_path: Path | None = None) -> dict[str, Any] | None:
    """The payload of the current official report, or ``None`` when none is stored.

    ``list_reports`` already orders the history newest period first, then newest
    emission and import, so its head row is the report the platform stands on
    today. This is what the HTML report and the summary metrics read, so a newly
    imported month reaches the printed report without a filename being edited.
    """
    reports = list_reports()
    if not reports:
        return None
    return get_report(reports[0]["snapshot_id"])
