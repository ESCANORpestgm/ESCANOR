"""Live rooftop-PV installation updates layered over immutable Prosol reports.

A Prosol report is a monthly snapshot; connections approved between two
snapshots are recorded here and summed on top of the snapshot by the API and
the report generator.

These updates used to be an append-only JSONL journal, which made a mis-keyed
entry permanent and the page read-only in practice. They now live in the shared
ESCANOR store through :mod:`db` (table ``prosol_installation_updates``), so the
dashboard can add, edit, delete and reverse individual entries — real CRUD —
while the audit trail survives an edit via ``amended_at``. Any pre-existing
JSONL file is imported once on first access, so no recorded connection is lost
by the move.

The public read functions keep their historical return shapes:
``list_installation_updates`` returns the record dicts newest-first and
``aggregate_updates`` returns the per-district ``{new_installations,
installed_capacity_kwp}`` totals the report generator consumes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

from data.paths import PROSOL_UPDATES_PATH
from data.steg_districts import AVG_UNIT_KWC, DISTRICT_BY_NAME
from db.engine import session_scope
from db.models import ProsolInstallationUpdate
from db.repository import init_db

# Kept for call-site compatibility; the legacy JSONL location to import from.
UPDATES_PATH = PROSOL_UPDATES_PATH
LEGACY_ID = "update_legacy"
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


def _validate_district(district: Any) -> str:
    district_upper = str(district or "").strip().upper()
    if district_upper not in DISTRICT_BY_NAME:
        raise ValueError(f"Unknown STEG district: {district_upper or 'empty'}")
    return district_upper


def _as_record(row: ProsolInstallationUpdate) -> dict[str, Any]:
    return {
        "update_id": row.update_id,
        "recorded_at": row.recorded_at,
        "amended_at": row.amended_at,
        "report_period": row.report_period,
        "district": row.district,
        "direction": row.direction,
        "new_installations": int(row.new_installations),
        "installed_capacity_kwp": round(float(row.installed_capacity_kwp), CAPACITY_DECIMALS),
        "source": row.source,
        "notes": row.notes,
    }


def _new_update_id(session, stamp: datetime) -> str:
    """Collision-free identifier: timestamp + next sequence for that second.

    The counter matches on the ``update_id`` prefix, not ``recorded_at`` — the
    latter is a full ISO-8601 string whose format differs from the compact id
    stamp, so counting ids is what actually detects a same-second collision.
    """
    prefix = f"update_{stamp:{ID_TIMESTAMP_FORMAT}}_"
    same_second = session.scalar(
        select(func.count())
        .select_from(ProsolInstallationUpdate)
        .where(ProsolInstallationUpdate.update_id.like(f"{prefix}%"))
    )
    return f"{prefix}{int(same_second or 0) + 1:04d}"


def _import_legacy(updates_path: Path = UPDATES_PATH) -> None:
    """One-time migration of the append-only JSONL journal into the table."""
    if not updates_path.is_file():
        return
    lines = [line for line in updates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return
    with session_scope() as session:
        known = set(session.scalars(select(ProsolInstallationUpdate.update_id)).all())
        added = 0
        for index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            update_id = str(row.get("update_id") or f"{LEGACY_ID}_{index + 1:04d}")
            if update_id in known:
                continue
            district = _safe_district(row.get("district"))
            session.add(
                ProsolInstallationUpdate(
                    update_id=update_id,
                    recorded_at=str(row.get("recorded_at") or datetime.now(timezone.utc).isoformat()),
                    report_period=str(row.get("report_period") or ""),
                    district=district,
                    direction=str(row.get("direction") or ""),
                    new_installations=int(row.get("new_installations") or 0),
                    installed_capacity_kwp=float(row.get("installed_capacity_kwp") or 0),
                    source=str(row.get("source") or DEFAULT_SOURCE),
                    notes=str(row.get("notes") or ""),
                )
            )
            added += 1
        if added:
            # The file stays untouched (it is the migration receipt); a rename
            # would need the API to hold the store, so we leave it inert.
            print(f"[Prosol updates] imported {added} legacy installation updates into the store")


def _safe_district(district: Any) -> str:
    return str(district or "").strip().upper()


# One-shot guard: the store is created and the legacy journal imported on the
# first call of a process, not on every dashboard poll.
_initialized = False


def initialize() -> None:
    """Create the table if absent and pull in any legacy JSONL journal."""
    global _initialized
    if _initialized:
        return
    init_db()
    _import_legacy()
    _initialized = True


def add_installation_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one manual update and store it as a new row."""
    initialize()
    district = _validate_district(payload.get("district"))
    installations = int(_number(payload.get("new_installations"), "new_installations", 1))
    capacity = _number(
        payload.get("installed_capacity_kwp", installations * AVG_UNIT_KWC),
        "installed_capacity_kwp",
    )
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        update_id = _new_update_id(session, now)
        session.add(
            ProsolInstallationUpdate(
                update_id=update_id,
                recorded_at=now.isoformat(),
                report_period=str(payload.get("report_period") or now.strftime(REPORT_PERIOD_FORMAT)),
                district=district,
                direction=DISTRICT_BY_NAME[district].direction,
                new_installations=installations,
                installed_capacity_kwp=round(capacity, CAPACITY_DECIMALS),
                source=str(payload.get("source") or DEFAULT_SOURCE),
                notes=str(payload.get("notes") or ""),
            )
        )
    return get_installation_update(update_id)  # type: ignore[return-value]


def list_installation_updates() -> list[dict[str, Any]]:
    """Newest update first, as shown on the dashboard."""
    initialize()
    with session_scope() as session:
        rows = session.scalars(
            select(ProsolInstallationUpdate).order_by(
                ProsolInstallationUpdate.recorded_at.desc(),
                ProsolInstallationUpdate.update_id.desc(),
            )
        ).all()
    return [_as_record(row) for row in rows]


def get_installation_update(update_id: str) -> dict[str, Any] | None:
    initialize()
    with session_scope() as session:
        row = session.get(ProsolInstallationUpdate, update_id)
        return _as_record(row) if row is not None else None


def update_installation_update(update_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Edit a stored update in place, stamping ``amended_at``.

    Any subset of district / new_installations / installed_capacity_kwp /
    report_period / notes may be supplied; the direction is re-derived from the
    district so the two never drift apart.
    """
    initialize()
    with session_scope() as session:
        row = session.get(ProsolInstallationUpdate, update_id)
        if row is None:
            raise KeyError(update_id)
        if payload.get("district") is not None:
            row.district = _validate_district(payload["district"])
            row.direction = DISTRICT_BY_NAME[row.district].direction
        if payload.get("new_installations") is not None:
            row.new_installations = int(_number(payload["new_installations"], "new_installations"))
        if payload.get("installed_capacity_kwp") is not None:
            row.installed_capacity_kwp = round(
                _number(payload["installed_capacity_kwp"], "installed_capacity_kwp"),
                CAPACITY_DECIMALS,
            )
        if payload.get("report_period") is not None:
            row.report_period = str(payload["report_period"])
        if payload.get("notes") is not None:
            row.notes = str(payload["notes"])
        row.amended_at = datetime.now(timezone.utc).isoformat()
    return get_installation_update(update_id)  # type: ignore[return-value]


def delete_installation_update(update_id: str) -> bool:
    """Remove one update outright. Returns whether a row was deleted."""
    initialize()
    with session_scope() as session:
        result = session.execute(
            delete(ProsolInstallationUpdate).where(
                ProsolInstallationUpdate.update_id == update_id
            )
        )
    return int(result.rowcount or 0) > 0


def reverse_installation_update(update_id: str) -> dict[str, Any]:
    """Append the negation of an update, keeping the original for the audit trail.

    Deleting is sometimes wrong — the mis-keyed connection was still a real
    event. A reversal leaves both rows so the ledger reads honestly, while
    :func:`aggregate_updates` nets them to the corrected district total.
    """
    original = get_installation_update(update_id)
    if original is None:
        raise KeyError(update_id)
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        reversal_id = _new_update_id(session, now)
        session.add(
            ProsolInstallationUpdate(
                update_id=reversal_id,
                recorded_at=now.isoformat(),
                report_period=original["report_period"],
                district=original["district"],
                direction=original["direction"],
                new_installations=-int(original["new_installations"]),
                installed_capacity_kwp=-round(float(original["installed_capacity_kwp"]), CAPACITY_DECIMALS),
                source="manual_reversal",
                notes=f"Reversal of {update_id}",
            )
        )
    return get_installation_update(reversal_id)  # type: ignore[return-value]


def aggregate_updates() -> dict[str, dict[str, float]]:
    """Per-district net totals over the whole update ledger."""
    initialize()
    totals: dict[str, dict[str, float]] = {}
    with session_scope() as session:
        rows = session.execute(
            select(
                ProsolInstallationUpdate.district,
                func.sum(ProsolInstallationUpdate.new_installations),
                func.sum(ProsolInstallationUpdate.installed_capacity_kwp),
            ).group_by(ProsolInstallationUpdate.district)
        ).all()
    for district, count, capacity in rows:
        totals[str(district).upper()] = {
            "new_installations": int(count or 0),
            "installed_capacity_kwp": round(float(capacity or 0), CAPACITY_DECIMALS),
        }
    return totals
