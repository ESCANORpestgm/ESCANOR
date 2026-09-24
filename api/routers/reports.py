"""Prosol reports, evaluation, and displacement endpoints."""

import json
from typing import Any

import pandas as pd
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from api.config import PROJECT_ROOT
from api.services import get_forecast_frame
from data.steg_districts import calculate_displacement
from models.aggregation import aggregate
from reports.evaluation_registry import evaluation_values_path, get_evaluation, list_evaluations
from reports.prosol_history_db import (
    DEFAULT_DB_PATH,
    get_report as get_prosol_history_report,
    import_generated_snapshots,
    import_snapshot,
    list_reports as list_prosol_history_reports,
)
from reports.prosol_installation_export import (
    new_installations_by_district,
    rows_to_csv,
)
from reports.prosol_report_generator import (
    DEFAULT_SNAPSHOT_PATH,
    generate_html_prosol_report,
    get_prosol_summary_metrics,
)
from reports.prosol_updates import (
    CAPACITY_DECIMALS,
    add_installation_update,
    aggregate_updates,
    list_installation_updates,
)

router = APIRouter(tags=["STEG Prosol"])


@router.get("/reports/prosol/summary")
def prosol_summary_metrics():
    return get_prosol_summary_metrics()


@router.get("/reports/prosol/snapshot")
def prosol_report_snapshot():
    path = DEFAULT_SNAPSHOT_PATH
    if not path.exists():
        raise HTTPException(404, "No imported Prosol snapshot found — run the report importer first.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/reports/prosol/html", response_class=HTMLResponse)
def prosol_html_report():
    return generate_html_prosol_report()


@router.get("/reports/prosol/history", tags=["STEG Prosol History"])
def prosol_history():
    import_generated_snapshots()
    return {"reports": list_prosol_history_reports()}


@router.get("/reports/prosol/history/{snapshot_id}", tags=["STEG Prosol History"])
def prosol_history_detail(snapshot_id: str):
    import_generated_snapshots()
    report = get_prosol_history_report(snapshot_id)
    if report is None:
        raise HTTPException(404, "Prosol report snapshot not found")
    report["new_installations_by_district"] = new_installations_by_district(report)
    live_updates = aggregate_updates()
    for row in report["new_installations_by_district"]:
        update = live_updates.get(str(row["district"]).upper(), {})
        row["live_new_installations"] = int(update.get("new_installations", 0))
        row["live_installed_capacity_kwp"] = round(float(update.get("installed_capacity_kwp", 0)), CAPACITY_DECIMALS)
        row["current_new_installations_ytd"] = float(row["new_installations_ytd"]) + row["live_new_installations"]
    report["live_updates"] = list_installation_updates()
    return report


@router.get("/reports/prosol/updates", tags=["STEG Prosol History"])
def prosol_installation_updates():
    return {"updates": list_installation_updates(), "totals_by_district": aggregate_updates()}


@router.post("/reports/prosol/updates", tags=["STEG Prosol History"])
def add_prosol_installation_update(payload: dict[str, Any]):
    try:
        return add_installation_update(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/reports/prosol/history/{snapshot_id}/new-installations.csv", response_class=PlainTextResponse, tags=["STEG Prosol History"])
def prosol_new_installations_csv(snapshot_id: str):
    import_generated_snapshots()
    report = get_prosol_history_report(snapshot_id)
    if report is None:
        raise HTTPException(404, "Prosol report snapshot not found")
    rows = new_installations_by_district(report)
    live_updates = aggregate_updates()
    for row in rows:
        live = live_updates.get(str(row["district"]).upper(), {})
        row["live_new_installations"] = int(live.get("new_installations", 0))
        row["current_new_installations_ytd"] = float(row["new_installations_ytd"]) + row["live_new_installations"]
    return PlainTextResponse(
        rows_to_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{snapshot_id}_new_installations_by_district.csv"'},
    )


@router.post("/reports/prosol/history/import", tags=["STEG Prosol History"])
def import_prosol_history_snapshot(path: str = Body(..., embed=True)):
    """Import a snapshot that lives inside the project (no path traversal)."""
    snapshot_path = (PROJECT_ROOT / path).resolve()
    if not snapshot_path.is_relative_to(PROJECT_ROOT) or not snapshot_path.is_file():
        raise HTTPException(400, "Snapshot path must point to an existing project file")
    snapshot_id, inserted = import_snapshot(snapshot_path, DEFAULT_DB_PATH)
    return {"snapshot_id": snapshot_id, "inserted": inserted}


@router.get("/evaluations/history", tags=["Forecast Evaluation"])
def evaluation_history():
    return {"evaluations": list_evaluations()}


@router.get("/evaluations/{evaluation_id}", tags=["Forecast Evaluation"])
def evaluation_detail(evaluation_id: str):
    evaluation = get_evaluation(evaluation_id)
    if evaluation is None:
        raise HTTPException(404, "Forecast evaluation not found")
    return evaluation


@router.get("/evaluations/{evaluation_id}/values", tags=["Forecast Evaluation"])
def evaluation_values(evaluation_id: str):
    evaluation = get_evaluation(evaluation_id)
    if evaluation is None:
        raise HTTPException(404, "Forecast evaluation not found")
    values_path = evaluation_values_path(evaluation_id)
    if values_path is None:
        raise HTTPException(404, "Evaluated values are not available")
    return pd.read_csv(values_path).to_dict(orient="records")


@router.get("/displacement/summary")
def displacement_summary():
    national = aggregate(get_forecast_frame(1), "national")
    return calculate_displacement(sum(national["forecast_p50_mw"]))
