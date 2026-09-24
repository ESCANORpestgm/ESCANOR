"""Append-only live installation updates layered over immutable Prosol reports.

A Prosol report is a monthly snapshot; connections approved between two
snapshots are recorded here as JSONL events (one per line, never rewritten) and
summed on top of the snapshot by the API and the history importer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.paths import PROSOL_UPDATES_PATH
from data.steg_districts import AVG_UNIT_KWC, DISTRICT_BY_NAME

# Kept for call-site compatibility; the canonical location lives in data.paths
UPDATES_PATH = PROSOL_UPDATES_PATH
DEFAULT_SOURCE = "manual_validated_update"
ID_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
REPORT_PERIOD_FORMAT = "%Y-%m"
# Capacity in kWp is stored with enough precision to survive monthly summing
CAPACITY_DECIMALS = 3


def _number(value: Any, field: str, minimum: float = 0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if number < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return number


def _read_updates(updates_path: Path = UPDATES_PATH) -> list[dict[str, Any]]:
    """Every recorded update, in append order; blank lines are ignored."""
    if not updates_path.is_file():
        return []
    return [json.loads(line) for line in updates_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_installation_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one manual update and append it to the log."""
    district = str(payload.get("district", "")).strip().upper()
    if district not in DISTRICT_BY_NAME:
        raise ValueError(f"Unknown STEG district: {district or 'empty'}")
    installations = int(_number(payload.get("new_installations"), "new_installations", 1))
    capacity = _number(
        payload.get("installed_capacity_kwp", installations * AVG_UNIT_KWC),
        "installed_capacity_kwp",
    )
    now = datetime.now(timezone.utc)
    record = {
        "update_id": f"update_{now:{ID_TIMESTAMP_FORMAT}}_{len(_read_updates()) + 1:04d}",
        "recorded_at": now.isoformat(),
        "report_period": str(payload.get("report_period") or now.strftime(REPORT_PERIOD_FORMAT)),
        "district": district,
        "direction": DISTRICT_BY_NAME[district].direction,
        "new_installations": installations,
        "installed_capacity_kwp": round(capacity, CAPACITY_DECIMALS),
        "source": str(payload.get("source") or DEFAULT_SOURCE),
        "notes": str(payload.get("notes") or ""),
    }
    UPDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with UPDATES_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_installation_updates() -> list[dict[str, Any]]:
    """Newest update first, as shown on the dashboard."""
    return list(reversed(_read_updates()))


def aggregate_updates() -> dict[str, dict[str, float]]:
    """Per-district totals over the whole update log."""
    totals: dict[str, dict[str, float]] = {}
    for row in _read_updates():
        district = row["district"]
        current = totals.setdefault(district, {"new_installations": 0, "installed_capacity_kwp": 0})
        current["new_installations"] += int(row["new_installations"])
        current["installed_capacity_kwp"] += float(row["installed_capacity_kwp"])
    return totals
