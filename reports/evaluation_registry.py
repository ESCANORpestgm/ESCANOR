"""Discover immutable forecast evaluation summaries for the API and dashboard.

An evaluation run is a directory under ``data.paths.EVALUATIONS_DIR`` holding a
``summary.json`` (plus the optional ``historical_metadata.json`` written by
``reports.historical_evaluation``). Runs are returned newest first, and a
corrupt or unreadable summary is skipped rather than failing the endpoint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data.io import read_json
from data.paths import EVALUATIONS_DIR, EXTRA_EVALUATION_ROOTS, relative_to_project
from reports.forecast_evaluator import EVALUATED_VALUES_FILENAME

# Roots searched for evaluation runs, in priority order
EVALUATION_ROOTS: tuple[Path, ...] = (EVALUATIONS_DIR, *EXTRA_EVALUATION_ROOTS)
SUMMARY_FILENAME = "summary.json"
METADATA_FILENAME = "historical_metadata.json"


def _summary_paths() -> list[Path]:
    paths: list[Path] = []
    for root in EVALUATION_ROOTS:
        if not root.exists():
            continue
        paths.extend(root.glob(f"*/{SUMMARY_FILENAME}"))
        if (root / SUMMARY_FILENAME).is_file():
            paths.append(root / SUMMARY_FILENAME)
    return sorted(set(paths), key=lambda path: path.stat().st_mtime, reverse=True)


def _evaluation_id(path: Path) -> str:
    return path.parent.name


def _read_pair(summary_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Summary plus its metadata sidecar; metadata is empty when absent."""
    summary = read_json(summary_path, default=None)
    if not isinstance(summary, dict):
        return None, {}
    metadata = read_json(summary_path.parent / METADATA_FILENAME, default=None)
    return summary, metadata if isinstance(metadata, dict) else {}


def evaluation_values_path(evaluation_id: str) -> Path | None:
    """Row-level evaluated values of one run, or ``None`` when it has none."""
    for root in EVALUATION_ROOTS:
        path = root / evaluation_id / EVALUATED_VALUES_FILENAME
        if path.is_file():
            return path
    return None


def list_evaluations() -> list[dict[str, Any]]:
    records = []
    for path in _summary_paths():
        summary, metadata = _read_pair(path)
        if summary is None:
            continue
        records.append({
            "evaluation_id": _evaluation_id(path),
            "path": relative_to_project(path),
            "rows_matched": summary.get("rows_matched", 0),
            "created_at": summary.get("created_at"),
            "source": metadata.get("source"),
            "forecast_source": summary.get("forecast_source"),
            "actual_source": summary.get("actual_source"),
            "horizon_metrics": summary.get("horizon_metrics", []),
        })
    return records


def get_evaluation(evaluation_id: str) -> dict[str, Any] | None:
    for path in _summary_paths():
        if _evaluation_id(path) != evaluation_id:
            continue
        summary, metadata = _read_pair(path)
        if summary is None:
            return None
        if metadata:
            summary["metadata"] = metadata
            summary["source"] = metadata.get("source")
        return summary
    return None
