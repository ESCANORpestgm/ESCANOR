"""Discover immutable forecast evaluation summaries for the API and dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOTS = (ROOT / "results" / "forecast_evaluations", ROOT / "evaluations")


def _summary_paths() -> list[Path]:
    paths = []
    for root in EVALUATION_ROOTS:
        if root.exists():
            paths.extend(root.glob("*/summary.json"))
            if (root / "summary.json").exists():
                paths.append(root / "summary.json")
    return sorted(set(paths), key=lambda path: path.stat().st_mtime, reverse=True)


def _evaluation_id(path: Path) -> str:
    return path.parent.name


def list_evaluations() -> list[dict[str, Any]]:
    records = []
    for path in _summary_paths():
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metadata_path = path.parent / "historical_metadata.json"
        metadata = {}
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
        records.append({
            "evaluation_id": _evaluation_id(path),
            "path": str(path.relative_to(ROOT)),
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
        if _evaluation_id(path) == evaluation_id:
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
                metadata_path = path.parent / "historical_metadata.json"
                if metadata_path.is_file():
                    try:
                        summary["metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
                        summary["source"] = summary["metadata"].get("source")
                    except (OSError, json.JSONDecodeError):
                        pass
                return summary
            except (OSError, json.JSONDecodeError):
                return None
    return None
