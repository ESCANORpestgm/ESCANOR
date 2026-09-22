"""File-based immutable model-version and training-run registry."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "results" / "model_registry"
MODEL_VERSIONS_PATH = REGISTRY_DIR / "model_versions.json"
TRAINING_RUNS_PATH = REGISTRY_DIR / "training_runs.json"
PRODUCTION_PATH = REGISTRY_DIR / "production_model.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: list[dict] | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def create_training_run(
    data_start: str | None,
    data_end: str | None,
    feature_version: str,
    schema_version: str,
    source: str,
) -> str:
    run_id = f"training_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}"
    runs = _read(TRAINING_RUNS_PATH)
    runs.append({
        "training_run_id": run_id,
        "status": "running",
        "started_at": _now(),
        "data_start": data_start,
        "data_end": data_end,
        "feature_version": feature_version,
        "schema_version": schema_version,
        "source": source,
    })
    _write(TRAINING_RUNS_PATH, runs)
    return run_id


def finish_training_run(training_run_id: str, status: str, model_version: str | None = None, metrics: dict | None = None, error: str | None = None) -> None:
    runs = _read(TRAINING_RUNS_PATH)
    for run in runs:
        if run.get("training_run_id") == training_run_id:
            run.update({"status": status, "finished_at": _now(), "model_version": model_version, "metrics": metrics or {}})
            if error:
                run["error"] = error
            break
    _write(TRAINING_RUNS_PATH, runs)


def register_model(
    training_run_id: str,
    artifact_path: str,
    metrics: dict,
    data_start: str | None,
    data_end: str | None,
    feature_version: str,
    schema_version: str,
    status: str = "candidate",
) -> str:
    model_version = f"model_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}"
    versions = _read(MODEL_VERSIONS_PATH)
    versions.append({
        "model_version": model_version,
        "training_run_id": training_run_id,
        "status": status,
        "created_at": _now(),
        "artifact_path": artifact_path,
        "data_start": data_start,
        "data_end": data_end,
        "feature_version": feature_version,
        "schema_version": schema_version,
        "metrics": metrics,
    })
    _write(MODEL_VERSIONS_PATH, versions)
    finish_training_run(training_run_id, "completed", model_version, metrics)
    return model_version


def current_production() -> dict | None:
    if not PRODUCTION_PATH.exists():
        return None
    return json.loads(PRODUCTION_PATH.read_text(encoding="utf-8"))


def promote_model(model_version: str, production_artifact: Path) -> dict:
    versions = _read(MODEL_VERSIONS_PATH)
    candidate = next((item for item in versions if item.get("model_version") == model_version), None)
    if candidate is None:
        raise ValueError(f"Unknown model version: {model_version}")

    candidate_mae = candidate.get("metrics", {}).get("MAE_MW")
    production = current_production()
    production_mae = production.get("metrics", {}).get("MAE_MW") if production else None
    if production_mae is not None and (candidate_mae is None or float(candidate_mae) >= float(production_mae)):
        raise ValueError("Candidate model does not outperform the current production model")

    source = Path(candidate["artifact_path"])
    if not source.exists():
        raise FileNotFoundError(f"Candidate artifact does not exist: {source}")
    production_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, production_artifact)

    for item in versions:
        if item.get("status") == "production":
            item["status"] = "archived"
        if item.get("model_version") == model_version:
            item["status"] = "production"
            item["promoted_at"] = _now()
    _write(MODEL_VERSIONS_PATH, versions)
    production_record = {**candidate, "status": "production", "promoted_at": _now(), "production_artifact": str(production_artifact)}
    _write(PRODUCTION_PATH, production_record)
    return production_record


def ensure_initial_production(artifact_path: Path, metrics: dict) -> dict:
    """Register the existing artifact once so later candidates have a baseline."""
    existing = current_production()
    if existing:
        if not existing.get("metrics") and metrics:
            existing["metrics"] = metrics
            versions = _read(MODEL_VERSIONS_PATH)
            for item in versions:
                if item.get("model_version") == existing.get("model_version"):
                    item["metrics"] = metrics
                    break
            _write(MODEL_VERSIONS_PATH, versions)
            _write(PRODUCTION_PATH, existing)
        return existing
    run_id = create_training_run(None, None, "legacy", "legacy", "existing production artifact")
    model_version = register_model(run_id, str(artifact_path), metrics, None, None, "legacy", "legacy", "production")
    record = next(item for item in _read(MODEL_VERSIONS_PATH) if item["model_version"] == model_version)
    _write(PRODUCTION_PATH, record)
    return record


def list_model_versions() -> list[dict]:
    return list(reversed(_read(MODEL_VERSIONS_PATH)))


def list_training_runs() -> list[dict]:
    return list(reversed(_read(TRAINING_RUNS_PATH)))
