"""Compare two normalized Prosol rooftop-PV snapshots.

Usage:
    python -m reports.prosol_report_compare \
        reports/generated/prosol_2026-03_v1.json \
        reports/generated/prosol_2026-03_v2.json \
        --output reports/generated/prosol_2026-03_comparison.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
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
            for key in (
                "current_month",
                "previous_year_month",
                "current_year_to_date",
                "previous_year_to_date",
                "since_program_start",
            )
            if before.get(key) != after.get(key)
        }
        if changed:
            metric_differences.append({"name": name, "changes": changed})

    left_districts = {row["name"] for row in left["districts"]}
    right_districts = {row["name"] for row in right["districts"]}
    return {
        "scope": "rooftop_pv",
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

    result = compare(load(args.left), load(args.right))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Compared {args.left.name} with {args.right.name} -> {args.output}")
    print(f"National metric differences: {len(result['national_metric_differences'])}")
    print(f"Districts added: {len(result['districts_added'])}")
    print(f"Districts removed: {len(result['districts_removed'])}")


if __name__ == "__main__":
    main()
