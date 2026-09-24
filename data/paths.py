"""Central artifact-path registry — the single source of truth for on-disk locations.

Every module that reads or writes a generated artifact imports it from here
instead of building ``Path(__file__).parents[...]`` strings. Two consequences:

- ``results/`` is organised by artifact *category* (datasets, model artifacts,
  history, evaluations, …) and moving a category is a one-line change here.
- ``resolve()`` falls back to the pre-reorganisation flat layout, so artifacts
  produced before the restructure are still found without a data migration.

This module lives in ``data`` — the lowest layer of the platform — and imports
nothing from the project, so ``models``, ``reports`` and ``api`` can all depend
on it without creating a cycle.

Override the roots with ``PRESOL_RESULTS_DIR`` (artifacts) or ``PRESOL_ROOT``
(project root, used by tests and alternate deployments).
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Roots ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("PRESOL_ROOT", Path(__file__).resolve().parents[1])).resolve()
RESULTS_ROOT = Path(os.environ.get("PRESOL_RESULTS_DIR", PROJECT_ROOT / "results")).resolve()

# ── Artifact categories ──────────────────────────────────────────────────────

DATASETS_DIR = RESULTS_ROOT / "datasets"
PVGIS_CACHE_DIR = DATASETS_DIR / "pvgis_cache"
MODEL_ARTIFACTS_DIR = RESULTS_ROOT / "model_artifacts"
REGISTRY_DIR = MODEL_ARTIFACTS_DIR / "model_registry"
# Immutable candidate bundles produced by each retraining run.
REGISTRY_ARTIFACTS_DIR = REGISTRY_DIR / "artifacts"
HISTORY_DIR = RESULTS_ROOT / "history"
EVALUATIONS_DIR = RESULTS_ROOT / "evaluations"
MEASUREMENTS_DIR = RESULTS_ROOT / "measurements"
PROSOL_DIR = RESULTS_ROOT / "prosol"
REPORTS_DIR = RESULTS_ROOT / "reports"
FIGURES_DIR = RESULTS_ROOT / "figures"

# Where generated Prosol JSON snapshots are dropped for the history importer.
PROSOL_SNAPSHOT_DIR = PROJECT_ROOT / "reports" / "generated"

# Extra roots searched for evaluation summaries (legacy/external locations).
EXTRA_EVALUATION_ROOTS: tuple[Path, ...] = (PROJECT_ROOT / "evaluations",)

# ── Individual artifacts ─────────────────────────────────────────────────────

MODEL_PATH = PROJECT_ROOT / "models" / "artifacts" / "quantile_models.joblib"
CALIBRATION_PATH = MODEL_ARTIFACTS_DIR / "calibration.json"
TRAINING_METRICS_PATH = HISTORY_DIR / "metrics_by_horizon.csv"
VALIDATION_METRICS_PATH = MODEL_ARTIFACTS_DIR / "model_validation_metrics.json"
NATIONAL_HISTORY_PATH = HISTORY_DIR / "history_national.csv"
DAILY_HISTORY_PATH = HISTORY_DIR / "history_daily.csv"
TRAINING_PROGRESSION_PATH = HISTORY_DIR / "training_progression.csv"
RETRAIN_LOG_PATH = HISTORY_DIR / "retrain_log.csv"
RETRAIN_STATE_PATH = HISTORY_DIR / "retrain_state.json"
METER_BUFFER_PATH = MEASUREMENTS_DIR / "metering_buffer.csv"
ROOFTOP_TRAINING_DATASET_PATH = DATASETS_DIR / "rooftop_actual_15min.csv"
PROSOL_HISTORY_DB_PATH = PROSOL_DIR / "prosol_history.db"
PROSOL_UPDATES_PATH = PROSOL_DIR / "installation_updates.jsonl"
PROSOL_HTML_REPORT_PATH = REPORTS_DIR / "steg_prosol_mars_2026.html"

# ── ``results/`` layout reorganisation ───────────────────────────────────────
# Artifacts produced before the categorisation carry their flat path, and JSON
# records persisted that flat path as a string. Both directions are described by
# this single table: ``legacy → current``.
LEGACY_RELOCATIONS: dict[str, str] = {
    "calibration.json": "model_artifacts/calibration.json",
    "model_validation_metrics.json": "model_artifacts/model_validation_metrics.json",
    "model_registry": "model_artifacts/model_registry",
    "forecast_evaluations": "evaluations",
    "history_daily.csv": "history/history_daily.csv",
    "history_national.csv": "history/history_national.csv",
    "metrics_by_horizon.csv": "history/metrics_by_horizon.csv",
    "retrain_log.csv": "history/retrain_log.csv",
    "retrain_state.json": "history/retrain_state.json",
    "training_progression.csv": "history/training_progression.csv",
    "metering_buffer.csv": "measurements/metering_buffer.csv",
    "presol.db": "prosol/presol.db",
    "prosol_history.db": "prosol/prosol_history.db",
    "prosol_updates/installation_updates.jsonl": "prosol/installation_updates.jsonl",
    "steg_prosol_mars_2026.html": "reports/steg_prosol_mars_2026.html",
}

_CURRENT_TO_LEGACY: dict[str, str] = {current: legacy for legacy, current in LEGACY_RELOCATIONS.items()}


def _relocate(relative: str, table: dict[str, str]) -> str:
    """Rewrite a ``results/``-relative path through ``table``, longest prefix first."""
    parts = relative.split("/")
    for depth in range(len(parts), 0, -1):
        replacement = table.get("/".join(parts[:depth]))
        if replacement:
            return "/".join(replacement.split("/") + parts[depth:])
    return relative


def _results_relative(path: Path) -> str | None:
    """Path of ``path`` relative to ``results/``, tolerating a moved checkout."""
    try:
        return str(path.resolve().relative_to(RESULTS_ROOT))
    except ValueError:
        pass
    parts = path.parts
    directory = RESULTS_ROOT.name
    if directory in parts:
        start = len(parts) - 1 - parts[::-1].index(directory)
        return "/".join(parts[start + 1:])
    return None


def _reanchor(path: Path) -> Path | None:
    """Re-anchor a path recorded by another checkout onto this project root.

    Absolute paths baked into persisted records break when the repository is
    moved or renamed; matching on the trailing path components recovers them.
    """
    parts = path.parts
    for depth in range(1, min(4, len(parts)) + 1):
        candidate = PROJECT_ROOT.joinpath(*parts[-depth:])
        if candidate.exists():
            return candidate
    return None


def resolve(path: str | Path) -> Path:
    """Return the location at which ``path`` actually exists on disk.

    Relative paths are read against the project root. Resolution tries, in
    order: the path as given, its current location when ``results/`` was still
    flat, its former flat location when only the categorised copy exists, and
    finally the same trailing components under this project root (records
    written by a moved checkout).
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    if candidate.exists():
        return candidate
    relative = _results_relative(candidate)
    if relative is not None:
        for table in (LEGACY_RELOCATIONS, _CURRENT_TO_LEGACY):
            relocated = RESULTS_ROOT / _relocate(relative, table)
            if relocated.exists():
                return relocated
    return _reanchor(candidate) or candidate


def exists(path: str | Path) -> bool:
    """True when the artifact is present in its canonical or legacy location."""
    return resolve(path).exists()


def resolve_artifact(value: str | Path) -> Path:
    """Read a path persisted inside an artifact record as a current ``Path``.

    Records may hold an absolute path from a different checkout, a
    project-relative path, or a pre-reorganisation flat location; all three are
    mapped onto the file that exists today.
    """
    return resolve(value)


def store_artifact(path: str | Path) -> str:
    """Canonical string to persist for an artifact: project-relative and current.

    Storing relative paths keeps registry and evaluation records valid when the
    repository is cloned elsewhere or ``results/`` is remounted, and never
    persists a path from the pre-reorganisation layout.
    """
    resolved = resolve(path)
    relative = _results_relative(resolved)
    if relative is not None:
        resolved = RESULTS_ROOT / _relocate(relative, LEGACY_RELOCATIONS)
    return relative_to_project(resolved)


def relative_to_project(path: str | Path) -> str:
    """Project-relative display path (API payloads, CSV metadata columns)."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


__all__ = [
    "CALIBRATION_PATH",
    "DAILY_HISTORY_PATH",
    "DATASETS_DIR",
    "EVALUATIONS_DIR",
    "EXTRA_EVALUATION_ROOTS",
    "FIGURES_DIR",
    "HISTORY_DIR",
    "LEGACY_RELOCATIONS",
    "MEASUREMENTS_DIR",
    "METER_BUFFER_PATH",
    "MODEL_ARTIFACTS_DIR",
    "MODEL_PATH",
    "NATIONAL_HISTORY_PATH",
    "PROSOL_DIR",
    "PROSOL_HTML_REPORT_PATH",
    "PROSOL_HISTORY_DB_PATH",
    "PROSOL_SNAPSHOT_DIR",
    "PROSOL_UPDATES_PATH",
    "PROJECT_ROOT",
    "PVGIS_CACHE_DIR",
    "REGISTRY_ARTIFACTS_DIR",
    "REGISTRY_DIR",
    "REPORTS_DIR",
    "RESULTS_ROOT",
    "RETRAIN_LOG_PATH",
    "RETRAIN_STATE_PATH",
    "ROOFTOP_TRAINING_DATASET_PATH",
    "TRAINING_METRICS_PATH",
    "TRAINING_PROGRESSION_PATH",
    "VALIDATION_METRICS_PATH",
    "exists",
    "relative_to_project",
    "resolve",
    "resolve_artifact",
    "store_artifact",
]
