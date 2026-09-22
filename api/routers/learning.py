"""Metering, retraining, and model-registry endpoints."""

import threading

import pandas as pd
from fastapi import APIRouter, HTTPException, Security
from pydantic import BaseModel

from api.core import METER_BUFFER, MODEL_PATH, RESULTS_DIR, RETRAIN_LOG, require_api_key, _state
from models.model_registry import current_production, list_model_versions, list_training_runs
from models.rooftop_training_adapter import build_training_frame

router = APIRouter(tags=["Continuous Learning"])


class MeteringRow(BaseModel):
    timestamp: str
    governorate: str
    actual_mw: float
    forecast_p50_mw: float | None = None


def _run_retrain(training_frame: pd.DataFrame) -> None:
    from models.retrain import check_drift_and_retrain

    try:
        result = check_drift_and_retrain(training_frame, _state["capacity_lookup"], _state["dust_lookup"])
        result["timestamp"] = pd.Timestamp.now().isoformat()
        log_frame = pd.DataFrame([result])
        if RETRAIN_LOG.exists():
            log_frame.to_csv(RETRAIN_LOG, mode="a", header=False, index=False)
        else:
            log_frame.to_csv(RETRAIN_LOG, index=False)
        if result.get("retrained"):
            _state["models"] = None
            _state["cache_time"] = None
        print(f"[retrain] {result}")
    except Exception as error:
        print(f"[retrain] error: {error}")


@router.post("/metering/push")
def metering_push(rows: list[MeteringRow], _key: str = Security(require_api_key)):
    new_frame = pd.DataFrame([row.model_dump() for row in rows])
    new_frame["received_at"] = pd.Timestamp.now().isoformat()
    if METER_BUFFER.exists():
        new_frame.to_csv(METER_BUFFER, mode="a", header=False, index=False)
    else:
        new_frame.to_csv(METER_BUFFER, index=False)
    buffer = pd.read_csv(METER_BUFFER, parse_dates=["timestamp"])
    return {
        "accepted": len(rows),
        "buffer_days": int(buffer["timestamp"].dt.date.nunique()),  # type: ignore[arg-type]
        "retrain_triggered": False,
        "message": "Legacy metering rows were stored; import a validated rooftop snapshot before retraining.",
    }


@router.post("/models/retrain", tags=["Model Registry"])
def trigger_manual_retrain():
    measurement_root = RESULTS_DIR / "measurements"
    snapshots = sorted(measurement_root.glob("*/validated_measurements.csv"), key=lambda path: path.stat().st_mtime, reverse=True) if measurement_root.exists() else []
    if not snapshots:
        raise HTTPException(400, "Import a validated rooftop measurement snapshot before retraining")
    try:
        training_frame = build_training_frame(snapshots[0])
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    thread = threading.Thread(target=_run_retrain, args=(training_frame,), daemon=True)
    thread.start()
    return {
        "accepted": True,
        "message": "Manual retraining started from the latest validated rooftop snapshot; promotion requires validation improvement.",
        "snapshot": str(snapshots[0].relative_to(RESULTS_DIR.parent)),
        "rows": len(training_frame),
        "locations": int(training_frame["governorate"].nunique()),  # type: ignore[arg-type]
    }


@router.get("/retrain/status")
def retrain_status():
    if not RETRAIN_LOG.exists():
        return {"retrain_log": [], "message": "No retrain events yet."}
    log = pd.read_csv(RETRAIN_LOG)
    return {"retrain_log": log.sort_values("timestamp", ascending=False).head(10).to_dict(orient="records")}


@router.get("/models/production", tags=["Model Registry"])
def model_production():
    if MODEL_PATH.exists():
        from models.model_registry import ensure_initial_production
        ensure_initial_production(MODEL_PATH, {})
    return {"production": current_production()}


@router.get("/models/versions", tags=["Model Registry"])
def model_versions():
    return {"models": list_model_versions()}


@router.get("/models/training-runs", tags=["Model Registry"])
def model_training_runs():
    return {"training_runs": list_training_runs()}
