"""File-based immutable model-version and training-run registry.

Every record is a JSON document under ``data.paths.REGISTRY_DIR``; a model
version is only promoted when it strictly outperforms the incumbent, and every
write is atomic so a crash mid-promotion cannot corrupt the catalogue.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from data.io import write_json_atomic
from data.paths import REGISTRY_DIR, resolve, resolve_artifact, store_artifact

MODEL_VERSIONS_PATH = REGISTRY_DIR / "model_versions.json"
TRAINING_RUNS_PATH = REGISTRY_DIR / "training_runs.json"
PRODUCTION_PATH = REGISTRY_DIR / "production_model.json"

# Lifecycle of a training run / registered model version
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
# Registered model versions: a candidate becomes production only by promotion,
# which archives the incumbent.
STATUS_CANDIDATE = "candidate"
STATUS_PRODUCTION = "production"
STATUS_ARCHIVED = "archived"
# Provenance recorded for artifacts that predate the registry
LEGACY_VERSION = "legacy"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> list[dict]:
    source = resolve(path)
    if not source.exists():
        return []
    return json.loads(source.read_text(encoding="utf-8"))


def _write(path: Path, value: list[dict] | dict) -> None:
    write_json_atomic(path, value)


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
        "status": STATUS_RUNNING,
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
    artifact_path: str | Path,
    metrics: dict,
    data_start: str | None,
    data_end: str | None,
    feature_version: str,
    schema_version: str,
    status: str = STATUS_CANDIDATE,
) -> str:
    model_version = f"model_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}"
    versions = _read(MODEL_VERSIONS_PATH)
    versions.append({
        "model_version": model_version,
        "training_run_id": training_run_id,
        "status": status,
        "created_at": _now(),
        "artifact_path": store_artifact(artifact_path),
        "data_start": data_start,
        "data_end": data_end,
        "feature_version": feature_version,
        "schema_version": schema_version,
        "metrics": metrics,
    })
    _write(MODEL_VERSIONS_PATH, versions)
    finish_training_run(training_run_id, STATUS_COMPLETED, model_version, metrics)
    return model_version


def current_production() -> dict | None:
    source = resolve(PRODUCTION_PATH)
    if not source.exists():
        return None
    return json.loads(source.read_text(encoding="utf-8"))


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

    source = resolve_artifact(candidate["artifact_path"])
    if not source.exists():
        raise FileNotFoundError(f"Candidate artifact does not exist: {source}")
    production_artifact = Path(production_artifact)
    production_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, production_artifact)

    for item in versions:
        if item.get("status") == STATUS_PRODUCTION:
            item["status"] = STATUS_ARCHIVED
        if item.get("model_version") == model_version:
            item["status"] = STATUS_PRODUCTION
            item["promoted_at"] = _now()
    _write(MODEL_VERSIONS_PATH, versions)
    production_record = {**candidate, "status": STATUS_PRODUCTION, "promoted_at": _now(),
                         "production_artifact": store_artifact(production_artifact)}
    _write(PRODUCTION_PATH, production_record)
    return production_record


def ensure_initial_production(artifact_path: str | Path, metrics: dict) -> dict:
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
    run_id = create_training_run(None, None, LEGACY_VERSION, LEGACY_VERSION,
                                 "existing production artifact")
    model_version = register_model(run_id, artifact_path, metrics, None, None,
                                   LEGACY_VERSION, LEGACY_VERSION, STATUS_PRODUCTION)
    record = next(item for item in _read(MODEL_VERSIONS_PATH) if item["model_version"] == model_version)
    _write(PRODUCTION_PATH, record)
    return record


def list_model_versions() -> list[dict]:
    return list(reversed(_read(MODEL_VERSIONS_PATH)))


def list_training_runs() -> list[dict]:
    return list(reversed(_read(TRAINING_RUNS_PATH)))
