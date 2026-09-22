"""SQLite persistence for immutable official Prosol rooftop-PV snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "results" / "prosol_history.db"
DEFAULT_SNAPSHOT_DIR = ROOT / "reports" / "generated"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prosol_reports (
    snapshot_id TEXT PRIMARY KEY,
    report_period TEXT NOT NULL,
    emission_date TEXT,
    source_file TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'rooftop_pv',
    reconciliation_passed INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prosol_reports_period
    ON prosol_reports(report_period, emission_date);

CREATE TABLE IF NOT EXISTS prosol_national_metrics (
    snapshot_id TEXT NOT NULL REFERENCES prosol_reports(snapshot_id),
    row_order INTEGER NOT NULL,
    name TEXT NOT NULL,
    unit TEXT,
    current_month REAL,
    previous_year_month REAL,
    variance_month_pct REAL,
    current_year_to_date REAL,
    previous_year_to_date REAL,
    variance_ytd_pct REAL,
    since_program_start REAL,
    PRIMARY KEY (snapshot_id, row_order)
);

CREATE TABLE IF NOT EXISTS prosol_directions (
    snapshot_id TEXT NOT NULL REFERENCES prosol_reports(snapshot_id),
    row_order INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, row_order)
);
CREATE TABLE IF NOT EXISTS prosol_districts (
    snapshot_id TEXT NOT NULL REFERENCES prosol_reports(snapshot_id),
    row_order INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, row_order)
);
CREATE TABLE IF NOT EXISTS prosol_installation_sizes (
    snapshot_id TEXT NOT NULL REFERENCES prosol_reports(snapshot_id),
    row_order INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, row_order)
);
CREATE TABLE IF NOT EXISTS prosol_pending_dossiers (
    snapshot_id TEXT NOT NULL REFERENCES prosol_reports(snapshot_id),
    row_order INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, row_order)
);
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "prosol_" + hashlib.sha256(canonical).hexdigest()[:16]


def import_snapshot(snapshot_path: Path, db_path: Path = DEFAULT_DB_PATH) -> tuple[str, bool]:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot_id = _snapshot_id(payload)
    initialize(db_path)

    with connect(db_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM prosol_reports WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if exists:
            return snapshot_id, False

        reconciliation = payload.get("reconciliation", {})
        connection.execute(
            """INSERT INTO prosol_reports
            (snapshot_id, report_period, emission_date, source_file, imported_at,
             scope, reconciliation_passed, snapshot_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                payload.get("report_period", "unknown"),
                payload.get("emission_date"),
                payload.get("source_file", snapshot_path.name),
                datetime.now(timezone.utc).isoformat(),
                payload.get("scope", "rooftop_pv"),
                int(bool(reconciliation.get("passed", False))),
                json.dumps(payload, ensure_ascii=False),
            ),
        )

        for row_order, row in enumerate(payload.get("national_rows", [])):
            connection.execute(
                """INSERT INTO prosol_national_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id, row_order, row.get("name", ""), row.get("unit"),
                    _number(row.get("current_month")), _number(row.get("previous_year_month")),
                    _number(row.get("variance_month_pct")), _number(row.get("current_year_to_date")),
                    _number(row.get("previous_year_to_date")), _number(row.get("variance_ytd_pct")),
                    _number(row.get("since_program_start")),
                ),
            )

        child_tables = {
            "directions": "prosol_directions",
            "districts": "prosol_districts",
            "installation_sizes": "prosol_installation_sizes",
            "pending_dossiers": "prosol_pending_dossiers",
        }
        for payload_key, table in child_tables.items():
            for row_order, row in enumerate(payload.get(payload_key, [])):
                connection.execute(
                    f"INSERT INTO {table} (snapshot_id, row_order, payload_json) VALUES (?, ?, ?)",
                    (snapshot_id, row_order, json.dumps(row, ensure_ascii=False)),
                )

    return snapshot_id, True


def import_generated_snapshots(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    initialize(db_path)
    results = []
    for snapshot_path in sorted(snapshot_dir.glob("prosol_*.json")):
        if snapshot_path.name.endswith("_comparison.json"):
            continue
        snapshot_id, inserted = import_snapshot(snapshot_path, db_path)
        results.append({"snapshot_id": snapshot_id, "source": snapshot_path.name, "inserted": inserted})
    return results


def list_reports(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    initialize(db_path)
    with connect(db_path) as connection:
        rows = connection.execute(
            """SELECT snapshot_id, report_period, emission_date, source_file,
                      imported_at, scope, reconciliation_passed
               FROM prosol_reports ORDER BY report_period DESC, emission_date DESC, imported_at DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_report(snapshot_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    initialize(db_path)
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM prosol_reports WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["snapshot_json"])
    payload["snapshot_id"] = snapshot_id
    payload["database"] = {
        "imported_at": row["imported_at"],
        "reconciliation_passed": bool(row["reconciliation_passed"]),
    }
    return payload
