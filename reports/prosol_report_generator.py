"""Official STEG "Tableau de Bord Programme Prosol": metrics payload and print report.

Source of truth is the JSON snapshot produced by
``reports.prosol_report_importer`` from the official PDF; when none has been
imported yet the module falls back to the March-2026 figures kept in
``prosol_fallback_snapshot``. On top of whichever base applies, the validated
append-only installation updates of ``reports.prosol_updates`` are overlaid, so
the report always reflects the latest approved connections.

Produces:
- ``get_prosol_summary_metrics()`` — the eight canonical indicators (dashboard JSON)
- ``generate_html_prosol_report()`` — standalone print-optimized HTML (A4)

Run to regenerate the archived report:
    python -m reports.prosol_report_generator
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
from pathlib import Path
from typing import Any

from data.io import write_text_atomic
from data.paths import PROSOL_HTML_REPORT_PATH, PROSOL_SNAPSHOT_DIR
from data.steg_districts import NATIONAL_ROOFTOP_PV_MWC, STEG_DISTRICTS, direction_summary
from reports.prosol_fallback_snapshot import (
    DEFAULT_MONTH_LABEL,
    DIRECTION_TUTELLE,
    build_fallback_summary,
)
from reports.prosol_report_template import (
    DIRECTION_TABLE_START,
    EXECUTION_TABLE_START,
    LAGGARD_TABLE_START,
    RATE_CLASS_LAGGARDS,
    RATE_CLASS_LEADERS,
    render_direction_row,
    render_direction_total_row,
    render_district_rate_row,
    render_footer,
    render_head,
    render_indicator_row,
)
from reports.prosol_updates import aggregate_updates

# Snapshot imported by reports.prosol_report_importer; None falls back to the
# hardcoded March-2026 figures.
DEFAULT_SNAPSHOT_PATH = PROSOL_SNAPSHOT_DIR / "prosol_mars_2026.json"
# Section 1.1 of the official report lists exactly these eight indicators, in order
MIN_NATIONAL_ROWS = 8
INDICATOR_UNITS = ("sites", "MW", "GWh", "GWh", "GWh", "ktep", "MDT", "ktonne")
INDICATOR_INSTALLATIONS = 1
INDICATOR_CAPACITY = 2
INDICATOR_PRODUCTION = 3
INDICATOR_INJECTION = 5
INDICATOR_FUEL_COST = 7
# Pending-dossier year-on-year figures the snapshot does not carry yet; they are
# still the ones printed by the March-2026 report.
PENDING_PREV_BASELINE = 1466
PENDING_VAR_BASELINE_PCT = 116.3
KW_PER_MW = 1000.0
PERCENT = 100.0
COMPLETION_RATE_DECIMALS = 1


def _indicator_map(summary: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """The summary's indicators keyed by their official 1-8 identifier."""
    return {indicator["id"]: indicator for indicator in summary.get("indicators", [])}


def _load_imported_summary(snapshot_path: str | Path | None = None) -> dict[str, Any] | None:
    """Load a normalized Prosol snapshot, or ``None`` when none was imported."""
    path = Path(snapshot_path) if snapshot_path else DEFAULT_SNAPSHOT_PATH
    if not path.exists():
        return None

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    rows = snapshot.get("national_rows", [])
    if len(rows) < MIN_NATIONAL_ROWS:
        raise ValueError("Imported Prosol snapshot is missing national PV metrics")

    units = list(INDICATOR_UNITS)
    indicators = [
        {
            "id": index,
            "label": row["name"],
            "unit": units[index - 1],
            "month_current": row["current_month"],
            "month_prev": row["previous_year_month"],
            "month_var": row["variance_month_pct"],
            "ytd_current": row["current_year_to_date"],
            "ytd_prev": row["previous_year_to_date"],
            "ytd_var": row["variance_ytd_pct"],
            "since_2011": row["since_program_start"],
        }
        for index, row in enumerate(rows[:MIN_NATIONAL_ROWS], start=1)
    ]

    installations = indicators[INDICATOR_INSTALLATIONS - 1]
    pending = snapshot["reconciliation"]["pending_dossiers"]
    return {
        "report_period": snapshot["report_period"],
        "emission_date": snapshot["emission_date"],
        "source_file": snapshot["source_file"],
        "direction_tutelle": DIRECTION_TUTELLE,
        "recap_executions": {
            "period": snapshot["report_period"],
            "executes_current": installations["ytd_current"],
            "executes_prev": installations["ytd_prev"],
            "executes_var_pct": installations["ytd_var"],
            "pending_current": pending["current_year_to_date"],
            "pending_prev": PENDING_PREV_BASELINE,
            "pending_var_pct": PENDING_VAR_BASELINE_PCT,
            "completion_rate_pct": round(
                installations["ytd_current"]
                / (installations["ytd_current"] + pending["current_year_to_date"])
                * PERCENT,
                COMPLETION_RATE_DECIMALS,
            ),
        },
        "indicators": indicators,
        # District velocity rankings are not part of the parsed national tables
        "top_five_districts": [],
        "last_five_districts": [],
    }


def _overlay_indicator(indicator: dict[str, Any], delta: float) -> None:
    """Add ``delta`` to every current figure and re-derive the variances."""
    for field in ("month_current", "ytd_current", "since_2011"):
        indicator[field] += delta
    if indicator["month_prev"]:
        indicator["month_var"] = (indicator["month_current"] / indicator["month_prev"] - 1) * PERCENT
    if indicator["ytd_prev"]:
        indicator["ytd_var"] = (indicator["ytd_current"] / indicator["ytd_prev"] - 1) * PERCENT


def _apply_live_installation_updates(summary: dict[str, Any]) -> dict[str, Any]:
    """Overlay validated append-only installation updates on the current report."""
    updates = aggregate_updates()
    live_sites = sum(int(row.get("new_installations", 0)) for row in updates.values())
    live_capacity_mw = sum(float(row.get("installed_capacity_kwp", 0)) for row in updates.values()) / KW_PER_MW
    if not live_sites and not live_capacity_mw:
        return summary

    indicators = _indicator_map(summary)
    installations = indicators.get(INDICATOR_INSTALLATIONS)
    capacity = indicators.get(INDICATOR_CAPACITY)
    if installations:
        _overlay_indicator(installations, live_sites)
    if capacity:
        _overlay_indicator(capacity, live_capacity_mw)

    if installations:
        recap = summary.setdefault("recap_executions", {})
        recap["executes_current"] = installations["ytd_current"]
        denominator = recap.get("executes_current", 0) + recap.get("pending_current", 0)
        recap["completion_rate_pct"] = (
            round(recap["executes_current"] / denominator * PERCENT, COMPLETION_RATE_DECIMALS)
            if denominator
            else 0
        )
    summary["live_updates_applied"] = live_sites
    return summary


def get_prosol_summary_metrics(
    month_str: str = DEFAULT_MONTH_LABEL,
    snapshot_path: str | Path | None = None,
) -> dict[str, Any]:
    """The official 8 canonical Prosol metrics of section 1.1 of the report."""
    imported_summary = _load_imported_summary(snapshot_path)
    if imported_summary is not None:
        return _apply_live_installation_updates(imported_summary)
    return _apply_live_installation_updates(build_fallback_summary(month_str))


def generate_html_prosol_report(
    output_path: str | Path | None = None,
    snapshot_path: str | Path | None = None,
) -> str:
    """Render an HTML report styled like STEG's Tableau de Bord Programme Prosol."""
    data = get_prosol_summary_metrics(DEFAULT_MONTH_LABEL, snapshot_path=snapshot_path)
    indicators = _indicator_map(data)
    produced_gwh = float(indicators.get(INDICATOR_PRODUCTION, {}).get("since_2011", 0))
    injected_gwh = float(indicators.get(INDICATOR_INJECTION, {}).get("since_2011", 0))

    parts = [
        render_head(
            report_period=data.get("report_period", DEFAULT_MONTH_LABEL),
            installed_capacity_mw=float(indicators.get(INDICATOR_CAPACITY, {}).get("since_2011", 0)),
            installed_sites=int(indicators.get(INDICATOR_INSTALLATIONS, {}).get("since_2011", 0)),
            injection_rate=(injected_gwh / produced_gwh * PERCENT) if produced_gwh else 0,
            injected_gwh=injected_gwh,
            avoided_fuel_cost_mdt=float(indicators.get(INDICATOR_FUEL_COST, {}).get("since_2011", 0)),
        ),
        *(render_indicator_row(indicator) for indicator in data["indicators"]),
        DIRECTION_TABLE_START,
        *(render_direction_row(name, info) for name, info in direction_summary().items()),
        render_direction_total_row(
            district_count=len(STEG_DISTRICTS),
            national_capacity_mwc=NATIONAL_ROOFTOP_PV_MWC,
            pending_dossiers=sum(district.pending_dossiers for district in STEG_DISTRICTS),
        ),
        EXECUTION_TABLE_START,
        *(render_district_rate_row(district, RATE_CLASS_LEADERS) for district in data["top_five_districts"]),
        LAGGARD_TABLE_START,
        *(render_district_rate_row(district, RATE_CLASS_LAGGARDS) for district in data["last_five_districts"]),
        render_footer(data["emission_date"]),
    ]
    html = "".join(parts)

    if output_path:
        write_text_atomic(output_path, html)
    return html


if __name__ == "__main__":
    report_path = write_text_atomic(PROSOL_HTML_REPORT_PATH, generate_html_prosol_report())
    print(f"Generated official STEG Prosol report at: {report_path.resolve()}")
