"""Compare two normalized Prosol rooftop-PV snapshots.

Usage:
    python -m reports.prosol_report_compare \
        reports/generated/prosol_2026-03_v1.json \
        reports/generated/prosol_2026-03_v2.json \
        --output reports/generated/prosol_2026-03_comparison.json
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import json
from pathlib import Path
from typing import Any

from data.io import write_json_atomic
from data.prosol_report_schema import REPORT_PERIOD_COLUMNS, SNAPSHOT_SCOPE

# Only the value columns are compared: the variance columns of a snapshot are
# derived from them, so comparing those too would report one change twice
COMPARED_VALUE_KEYS = REPORT_PERIOD_COLUMNS


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_rows = {row["name"]: row for row in left["national_rows"]}
    right_rows = {row["name"]: row for row in right["national_rows"]}
    metric_differences = []

    for name in sorted(set(left_rows) | set(right_rows)):
        before = left_rows.get(name)
        after = right_rows.get(name)
        if before is None or after is None:
            metric_differences.append({"name": name, "before": before, "after": after})
            continue
        changed = {
            key: {"before": before[key], "after": after[key]}
            for key in COMPARED_VALUE_KEYS
            if before.get(key) != after.get(key)
        }
        if changed:
            metric_differences.append({"name": name, "changes": changed})

    left_districts = {row["name"] for row in left["districts"]}
    right_districts = {row["name"] for row in right["districts"]}
    return {
        "scope": SNAPSHOT_SCOPE,
        "left_source": left["source_file"],
        "right_source": right["source_file"],
        "same_report_period": left["report_period"] == right["report_period"],
        "districts_added": sorted(right_districts - left_districts),
        "districts_removed": sorted(left_districts - right_districts),
        "national_metric_differences": metric_differences,
        "reconciliation": {
            "left_passed": left["reconciliation"]["passed"],
            "right_passed": right["reconciliation"]["passed"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compare(load_snapshot(args.left), load_snapshot(args.right))
    write_json_atomic(args.output, result)
    print(f"Compared {args.left.name} with {args.right.name} -> {args.output}")
    print(f"National metric differences: {len(result['national_metric_differences'])}")
    print(f"Districts added: {len(result['districts_added'])}")
    print(f"Districts removed: {len(result['districts_removed'])}")


if __name__ == "__main__":
    main()
