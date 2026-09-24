"""Atomic, crash-safe file helpers shared by every writer in the platform.

``write_json_atomic`` and ``write_text_atomic`` are the single implementations
used by the model registry, the evaluation writer, the Prosol reports and the
update log: a reader can never observe a half-written file, because the payload
is flushed to a temp sibling and then renamed (rename is atomic on POSIX).
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Callable
from io import TextIOBase
from pathlib import Path
from typing import Any

import pandas as pd


def _replace_atomically(target: Path, populate: Callable[[TextIOBase], None]) -> Path:
    """Run ``populate`` on a temp sibling of ``target``, then rename it into place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            populate(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return target


def _json_compliant(payload: Any) -> Any:
    """Recursively replace non-finite floats (NaN/±Inf) with ``None``.

    Python's ``json`` emits bare ``NaN``/``Infinity`` tokens which are not valid
    JSON: strict parsers (browsers' ``JSON.parse``, other services) reject them.
    Metrics from a degenerate training run can be NaN, so sanitise at the source.
    """
    if isinstance(payload, float) and not math.isfinite(payload):
        return None
    if isinstance(payload, dict):
        return {key: _json_compliant(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_json_compliant(value) for value in payload]
    return payload


def write_json_atomic(path: Path | str, payload: Any) -> Path:
    """Write ``payload`` as pretty JSON, replacing ``path`` atomically.

    Non-ASCII (French report labels) is kept readable rather than escaped; the
    result decodes identically either way.
    """
    return _replace_atomically(
        Path(path),
        lambda handle: json.dump(_json_compliant(payload), handle, indent=2, default=str, ensure_ascii=False, allow_nan=False),
    )


def write_text_atomic(path: Path | str, text: str) -> Path:
    """Replace ``path`` with ``text`` atomically (generated reports, exports)."""
    return _replace_atomically(Path(path), lambda handle: handle.write(text))


def read_json(path: Path | str, default: Any = None) -> Any:
    """Read JSON, returning ``default`` when the file is absent or unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_dataframe(frame: pd.DataFrame, path: Path | str) -> Path:
    """Write a dataframe as CSV, or Parquet when the target ends in ``.parquet``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() in {".parquet", ".pq"}:
        frame.to_parquet(target, index=False)
    else:
        frame.to_csv(target, index=False)
    return target


def append_dataframe(frame: pd.DataFrame, path: Path | str) -> Path:
    """Append rows to a CSV log, writing the header only when creating the file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, mode="a", header=not target.exists(), index=False)
    return target


__all__ = ["append_dataframe", "read_json", "write_dataframe", "write_json_atomic", "write_text_atomic"]
