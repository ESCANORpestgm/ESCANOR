"""Prosol reports, evaluation, and displacement endpoints."""

import json
import pandas as pd
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse

from api.core import RESULTS_DIR, ROOT, get_forecast_frame
from data.steg_districts import calculate_displacement
from models.aggregation import aggregate
from reports.evaluation_registry import get_evaluation, list_evaluations

from reports.prosol_history_db import (
    DEFAULT_DB_PATH,
    get_report as get_prosol_history_report,
    import_generated_snapshots,
    import_snapshot,
    list_reports as list_prosol_history_reports,
)
from reports.prosol_report_generator import generate_html_prosol_report, get_prosol_summary_metrics

router = APIRouter(tags=["STEG Prosol"])


@router.get("/reports/prosol/summary")
def prosol_summary_metrics():
    return get_prosol_summary_metrics("Mars 2026")


@router.get("/reports/prosol/snapshot")
def prosol_report_snapshot():
    path = ROOT / "reports" / "generated" / "prosol_mars_2026.json"
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
    return report


@router.post("/reports/prosol/history/import", tags=["STEG Prosol History"])
def import_prosol_history_snapshot(path: str = Body(..., embed=True)):
    snapshot_path = (ROOT / path).resolve()
    if not str(snapshot_path).startswith(str(ROOT)) or not snapshot_path.is_file():
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
    for root in (RESULTS_DIR / "forecast_evaluations", ROOT / "evaluations"):
        path = root / evaluation_id / "evaluated_values.csv"
        if path.is_file():
            return pd.read_csv(path).to_dict(orient="records")
    raise HTTPException(404, "Evaluated values are not available")


@router.get("/displacement/summary")
def displacement_summary():
    national = aggregate(get_forecast_frame(1), "national")
    return calculate_displacement(sum(national["forecast_p50_mw"]))
