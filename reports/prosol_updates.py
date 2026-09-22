"""Append-only live installation updates layered over immutable Prosol reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.steg_districts import AVG_UNIT_KWC, DISTRICT_BY_NAME

ROOT = Path(__file__).resolve().parents[1]
UPDATES_PATH = ROOT / "results" / "prosol_updates" / "installation_updates.jsonl"


def _number(value: Any, field: str, minimum: float = 0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if number < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return number


def _read_updates() -> list[dict[str, Any]]:
    if not UPDATES_PATH.is_file():
        return []
    rows = []
    for line in UPDATES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def add_installation_update(payload: dict[str, Any]) -> dict[str, Any]:
    district = str(payload.get("district", "")).strip().upper()
    if district not in DISTRICT_BY_NAME:
        raise ValueError(f"Unknown STEG district: {district or 'empty'}")
    installations = int(_number(payload.get("new_installations"), "new_installations", 1))
    capacity = _number(
        payload.get("installed_capacity_kwp", installations * AVG_UNIT_KWC),
        "installed_capacity_kwp",
    )
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "update_id": f"update_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{len(_read_updates()) + 1:04d}",
        "recorded_at": now,
        "report_period": str(payload.get("report_period") or datetime.now(timezone.utc).strftime("%Y-%m")),
        "district": district,
        "direction": DISTRICT_BY_NAME[district].direction,
        "new_installations": installations,
        "installed_capacity_kwp": round(capacity, 3),
        "source": str(payload.get("source") or "manual_validated_update"),
        "notes": str(payload.get("notes") or ""),
    }
    UPDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with UPDATES_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_installation_updates() -> list[dict[str, Any]]:
    return list(reversed(_read_updates()))


def aggregate_updates() -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for row in _read_updates():
        district = row["district"]
        current = totals.setdefault(district, {"new_installations": 0, "installed_capacity_kwp": 0})
        current["new_installations"] += int(row["new_installations"])
        current["installed_capacity_kwp"] += float(row["installed_capacity_kwp"])
    return totals
