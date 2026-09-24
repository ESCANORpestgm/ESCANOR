"""Metering, retraining, and model-registry endpoints."""

import io
import json
import threading
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Security, UploadFile, File
from pydantic import BaseModel

from api.config import (
    MEASUREMENTS_DIR,
    METER_BUFFER,
    MODEL_PATH,
    RETRAIN_LOG,
    RETRAIN_STATE_PATH,
    require_api_key,
)
from api.services import _state
from data.io import append_dataframe, write_json_atomic
from data.paths import relative_to_project
from models.model_registry import (
    current_production,
    ensure_initial_production,
    list_model_versions,
    list_training_runs,
)
from models.rooftop_training_adapter import build_training_frame
from reports.measurement_importer import VALIDATED_FILENAME

router = APIRouter(tags=["Continuous Learning"])
_RETRAIN_LOCK = threading.Lock()


def _write_retrain_state(state: dict[str, object]) -> None:
    """Persist the retraining progress markers read by ``/alerts``."""
    write_json_atomic(RETRAIN_STATE_PATH, state)


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
        append_dataframe(log_frame, RETRAIN_LOG)
        if result.get("retrained"):
            _state["models"] = None
            _state["cache_time"] = None
            _state["calibration"] = None
        _write_retrain_state({"status": "completed", "finished_at": pd.Timestamp.now().isoformat(), "result": result})
        print(f"[retrain] {result}")
    except Exception as error:
        _write_retrain_state({"status": "failed", "finished_at": pd.Timestamp.now().isoformat(), "error": str(error)})
        print(f"[retrain] error: {error}")


@router.post("/metering/push")
def metering_push(rows: list[MeteringRow], _key: str = Security(require_api_key)):
    new_frame = pd.DataFrame([row.model_dump() for row in rows])
    new_frame["received_at"] = pd.Timestamp.now().isoformat()
    append_dataframe(new_frame, METER_BUFFER)
    buffer = pd.read_csv(METER_BUFFER, parse_dates=["timestamp"])
    return {
        "accepted": len(rows),
        "buffer_days": int(buffer["timestamp"].dt.date.nunique()),  # type: ignore[arg-type]
        "retrain_triggered": False,
        "message": "Legacy metering rows were stored; import a validated rooftop snapshot before retraining.",
    }


def _latest_training_frame() -> tuple[pd.DataFrame, Path] | None:
    snapshots = sorted(
        MEASUREMENTS_DIR.glob(f"*/{VALIDATED_FILENAME}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if MEASUREMENTS_DIR.exists() else []
    if not snapshots:
        return None
    return build_training_frame(snapshots[0]), snapshots[0]


def start_latest_retrain() -> dict[str, object] | None:
    """Start one retraining job from the latest validated snapshot."""
    if not _RETRAIN_LOCK.acquire(blocking=False):
        return {"accepted": False, "message": "Retraining already running."}
    try:
        latest = _latest_training_frame()
        if latest is None:
            _RETRAIN_LOCK.release()
            return None
        training_frame, snapshot = latest
        _write_retrain_state({
            "status": "started",
            "started_at": pd.Timestamp.now().isoformat(),
            "snapshot": relative_to_project(snapshot),
            "rows": len(training_frame),
        })
        def run_and_release() -> None:
            try:
                _run_retrain(training_frame)
            finally:
                _RETRAIN_LOCK.release()
        threading.Thread(target=run_and_release, daemon=True).start()
        return {
            "accepted": True,
            "message": "Retraining started from the latest validated rooftop snapshot.",
            "snapshot": relative_to_project(snapshot),
            "rows": len(training_frame),
            "locations": int(training_frame["governorate"].nunique()),  # type: ignore[arg-type]
        }
    except Exception:
        _RETRAIN_LOCK.release()
        raise


def scheduled_retrain() -> None:
    try:
        result = start_latest_retrain()
        if result is None:
            print("[retrain] daily check skipped: no validated rooftop snapshot")
        else:
            print(f"[retrain] daily check: {result}")
    except Exception as error:
        print(f"[retrain] daily check failed: {error}")


@router.post("/models/retrain", tags=["Model Registry"])
def trigger_manual_retrain():
    try:
        result = start_latest_retrain()
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if result is None:
        raise HTTPException(400, "Import a validated rooftop measurement snapshot before retraining")
    return result


def _save_and_start_retrain(measurement_csv: bytes, source_label: str) -> dict[str, object]:
    """Save a measurement CSV as a validated snapshot and start retraining."""
    if not _RETRAIN_LOCK.acquire(blocking=False):
        return {"accepted": False, "message": "Retraining already in progress."}
    try:
        timestamp = pd.Timestamp.now().strftime("%Y%m%dT%H%M%S")
        snapshot_dir = MEASUREMENTS_DIR / f"{source_label}_{timestamp}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        measurement_path = snapshot_dir / VALIDATED_FILENAME
        measurement_path.write_bytes(measurement_csv)
        training_frame = build_training_frame(measurement_path)
        rows = len(training_frame)
        locations = int(training_frame["governorate"].nunique())
        _write_retrain_state({
            "status": "started",
            "started_at": pd.Timestamp.now().isoformat(),
            "snapshot": relative_to_project(snapshot_dir),
            "rows": rows,
            "source": source_label,
        })

        def run_and_release() -> None:
            try:
                _run_retrain(training_frame)
            finally:
                _RETRAIN_LOCK.release()

        threading.Thread(target=run_and_release, daemon=True).start()
        return {
            "accepted": True,
            "message": f"Retraining started from {source_label} data.",
            "snapshot": relative_to_project(snapshot_dir),
            "rows": rows,
            "locations": locations,
        }
    except Exception as error:
        _RETRAIN_LOCK.release()
        raise HTTPException(400, str(error)) from error


@router.post("/models/retrain/upload", tags=["Model Registry"])
async def retrain_from_csv(file: UploadFile = File(...)):
    """Upload a CSV with rooftop measurements and trigger retraining.

    Expected columns: timestamp_utc, location_id, power_kw, district, direction,
    ghi_wm2, temp_c, cloud_cover_pct.  Optional: quality_status (rows with
    quality_status != 'valid' are filtered out).
    """
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty.")
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as error:
        raise HTTPException(400, f"Unable to parse CSV: {error}") from error
    required = {"timestamp_utc", "location_id", "power_kw", "district", "direction"}
    missing = required - set(frame.columns)
    if missing:
        raise HTTPException(400, f"CSV is missing required columns: {sorted(missing)}. "
                            f"Found: {sorted(frame.columns.tolist())}")
    weather_required = {"ghi_wm2", "temp_c", "cloud_cover_pct"}
    weather_missing = weather_required - set(frame.columns)
    if weather_missing:
        raise HTTPException(400, f"CSV is missing weather columns: {sorted(weather_missing)}.")
    try:
        return _save_and_start_retrain(content, "upload")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(400, str(error)) from error


@router.post("/models/retrain/synthetic", tags=["Model Registry"])
def retrain_from_synthetic(start_date: str = "2024-01-01", end_date: str = "2025-01-01"):
    """Generate synthetic training data for all STEG districts and trigger retraining."""
    from ingestion.synthetic_data import generate_all
    from data.steg_districts import STEG_DISTRICTS

    try:
        synthetic_frame = generate_all(STEG_DISTRICTS, start=start_date, end=end_date)
    except Exception as error:
        raise HTTPException(400, f"Synthetic data generation failed: {error}") from error

    # Convert synthetic schema (timestamp, governorate, production_mw) → training schema
    training_csv = io.BytesIO()
    out = pd.DataFrame()
    out["timestamp_utc"] = pd.to_datetime(synthetic_frame["timestamp"]).dt.tz_localize("UTC")
    out["location_id"] = synthetic_frame["district"] + "_synth"
    out["power_kw"] = synthetic_frame["production_mw"] * 1000.0
    out["district"] = synthetic_frame["district"]
    out["direction"] = synthetic_frame["direction"]
    out["ghi_wm2"] = synthetic_frame["ghi_wm2"]
    out["temp_c"] = synthetic_frame["temp_c"]
    out["cloud_cover_pct"] = synthetic_frame["cloud_cover_pct"]
    out["quality_status"] = "valid"
    out.to_csv(training_csv, index=False)

    return _save_and_start_retrain(training_csv.getvalue(), "synthetic")


@router.get("/retrain/status")
def retrain_status():
    schedule = {
        "enabled": True,
        "interval_days": 1,
        "source": "latest validated rooftop measurement snapshot",
        "promotion_policy": "promote only when candidate validation improves",
    }
    if not RETRAIN_LOG.exists():
        return {"retrain_log": [], "schedule": schedule, "message": "Continuous learning is waiting for a validated rooftop snapshot."}
    log = pd.read_csv(RETRAIN_LOG)
    # Enrich log entries with baseline breakdown when available
    records = []
    for _, row in log.sort_values("timestamp", ascending=False).head(10).iterrows():
        entry = row.to_dict()
        # Parse baseline_maes if stored as string
        if "baseline_maes" in entry and isinstance(entry.get("baseline_maes"), str):
            try:
                entry["baseline_maes"] = json.loads(entry["baseline_maes"].replace("'", '"'))
            except (json.JSONDecodeError, ValueError):
                entry["baseline_maes"] = {}
        records.append(entry)
    return {"retrain_log": records, "schedule": schedule}


@router.get("/models/production", tags=["Model Registry"])
def model_production():
    if MODEL_PATH.exists():
        ensure_initial_production(MODEL_PATH, {})
    return {"production": current_production()}


@router.get("/models/versions", tags=["Model Registry"])
def model_versions():
    return {"models": list_model_versions()}


@router.get("/models/training-runs", tags=["Model Registry"])
def model_training_runs():
    return {"training_runs": list_training_runs()}
