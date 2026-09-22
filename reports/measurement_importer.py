"""Validate and store aggregated rooftop-PV production measurements.

This is the pre-database ingestion layer. It keeps the original CSV untouched
and writes a validated snapshot with quality flags under ``results/``.

Expected input columns:
    timestamp_utc, location_id, power_kw, energy_kwh,
    installed_capacity_kwp, source, quality_status

Usage:
    python -m reports.measurement_importer measurements.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"timestamp_utc", "location_id", "power_kw"}
OPTIONAL_COLUMNS = {
    "energy_kwh", "installed_capacity_kwp", "source", "quality_status",
    "district", "direction", "ghi_wm2", "temp_c", "cloud_cover_pct",
    "dni_wm2", "dhi_wm2", "wind_speed_ms", "horizon_hours",
}


def _snapshot_id(source: Path) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    return f"measurements_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{digest}"


def validate_measurements(source: Path, expected_minutes: int = 60) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(source)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required measurement columns: {sorted(missing)}")

    for column in OPTIONAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA

    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="coerce")
    frame["power_kw"] = pd.to_numeric(frame["power_kw"], errors="coerce")
    frame["energy_kwh"] = pd.to_numeric(frame["energy_kwh"], errors="coerce")
    frame["installed_capacity_kwp"] = pd.to_numeric(frame["installed_capacity_kwp"], errors="coerce")
    frame["quality_status"] = frame["quality_status"].fillna("unreviewed")
    frame["quality_flags"] = ""

    frame.loc[frame["timestamp_utc"].isna(), "quality_flags"] += "invalid_timestamp;"
    frame.loc[frame["power_kw"].isna(), "quality_flags"] += "invalid_power;"
    frame.loc[frame["power_kw"] < 0, "quality_flags"] += "negative_power;"
    frame.loc[frame["energy_kwh"] < 0, "quality_flags"] += "negative_energy;"

    capacity_known = frame["installed_capacity_kwp"].notna()
    impossible = capacity_known & (frame["power_kw"] > frame["installed_capacity_kwp"] * 1.2)
    frame.loc[impossible, "quality_flags"] += "above_capacity;"

    duplicate_mask = frame.duplicated(["location_id", "timestamp_utc"], keep=False)
    frame.loc[duplicate_mask, "quality_flags"] += "duplicate_timestamp;"

    frame = frame.sort_values(["location_id", "timestamp_utc"]).reset_index(drop=True)
    gaps = []
    for location_id, group in frame.groupby("location_id", dropna=False):
        deltas = group["timestamp_utc"].diff().dt.total_seconds().div(60)
        gap_rows = group.index[deltas > expected_minutes * 1.5]
        for row_index in gap_rows:
            gaps.append({"location_id": location_id, "row": int(row_index), "gap_minutes": float(deltas[row_index])})
            frame.loc[row_index, "quality_flags"] += "missing_interval_before;"

    invalid = frame["quality_flags"].ne("")
    frame.loc[~invalid & frame["quality_status"].eq("unreviewed"), "quality_status"] = "valid"
    frame.loc[invalid & frame["quality_status"].eq("unreviewed"), "quality_status"] = "flagged"

    report = {
        "source_file": source.name,
        "rows": len(frame),
        "locations": int(frame["location_id"].nunique()),  # type: ignore[arg-type]
        "flagged_rows": int(invalid.sum()),  # type: ignore[arg-type]
        "duplicate_rows": int(duplicate_mask.sum()),  # type: ignore[arg-type]
        "missing_interval_count": len(gaps),
        "gaps": gaps,
    }
    return frame, report


def import_measurements(source: Path, output_root: Path = Path("results")) -> tuple[Path, Path]:
    frame, report = validate_measurements(source)
    snapshot_id = _snapshot_id(source)
    snapshot_dir = output_root / "measurements" / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    validated_path = snapshot_dir / "validated_measurements.csv"
    report_path = snapshot_dir / "quality_report.json"
    frame.to_csv(validated_path, index=False)

    has_district = bool(frame["district"].notna().any())
    has_direction = bool(frame["direction"].notna().any())
    if has_district and has_direction:
        grouped = (
            frame.dropna(subset=["timestamp_utc", "district", "direction"])
            .groupby(["timestamp_utc", "district", "direction"], as_index=False)
            .agg(
                power_kw=("power_kw", "sum"),
                energy_kwh=("energy_kwh", "sum"),
                installed_capacity_kwp=("installed_capacity_kwp", "sum"),
            )
        )
        grouped.to_csv(snapshot_dir / "aggregated_by_district.csv", index=False)
        report["aggregated_by_district_rows"] = len(grouped)
    else:
        report["aggregation_status"] = "skipped: district and direction columns were not supplied"

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return validated_path, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("results"))
    args = parser.parse_args()

    validated, report = import_measurements(args.source, args.output_root)
    print(f"Validated measurements: {validated}")
    print(f"Quality report: {report}")


if __name__ == "__main__":
    main()
