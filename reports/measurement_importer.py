"""Validate and store aggregated rooftop-PV production measurements.

This is the pre-database ingestion layer. It keeps the original CSV untouched
and writes a validated snapshot with quality flags under
``data.paths.MEASUREMENTS_DIR``, one immutable directory per import.

Expected input columns:
    timestamp_utc, location_id, power_kw, energy_kwh,
    installed_capacity_kwp, source, quality_status

Usage:
    python -m reports.measurement_importer measurements.csv
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.io import write_dataframe, write_json_atomic
from data.paths import MEASUREMENTS_DIR

REQUIRED_COLUMNS = {"timestamp_utc", "location_id", "power_kw"}
OPTIONAL_COLUMNS = {
    "energy_kwh", "installed_capacity_kwp", "source", "quality_status",
    "district", "direction", "ghi_wm2", "temp_c", "cloud_cover_pct",
    "dni_wm2", "dhi_wm2", "wind_speed_ms", "horizon_hours",
}
# Rows with no explicit status are classified from their quality flags
STATUS_UNREVIEWED = "unreviewed"
STATUS_VALID = "valid"
STATUS_FLAGGED = "flagged"
# Quality flags written to ``quality_flags`` (semicolon-separated, additive)
FLAG_INVALID_TIMESTAMP = "invalid_timestamp"
FLAG_INVALID_POWER = "invalid_power"
FLAG_NEGATIVE_POWER = "negative_power"
FLAG_NEGATIVE_ENERGY = "negative_energy"
FLAG_ABOVE_CAPACITY = "above_capacity"
FLAG_DUPLICATE = "duplicate_timestamp"
FLAG_GAP = "missing_interval_before"
FLAG_SEPARATOR = ";"
# A meter may briefly exceed nameplate; only this multiple counts as impossible
CAPACITY_TOLERANCE_FACTOR = 1.2
# An interval longer than ``expected_minutes`` times this factor is a gap
GAP_TOLERANCE_FACTOR = 1.5
EXPECTED_INTERVAL_MINUTES = 60
SECONDS_PER_MINUTE = 60.0
SOURCE_HASH_LENGTH = 12  # leading hex characters of the source SHA-256
VALIDATED_FILENAME = "validated_measurements.csv"
AGGREGATED_FILENAME = "aggregated_by_district.csv"
REPORT_FILENAME = "quality_report.json"


def _snapshot_id(source: Path) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:SOURCE_HASH_LENGTH]
    return f"measurements_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{digest}"


def _flag(frame: pd.DataFrame, rows, flag: str) -> None:
    """Append one quality flag to the rows selected by ``rows`` (mask or label)."""
    frame.loc[rows, "quality_flags"] += flag + FLAG_SEPARATOR


def validate_measurements(source: Path,
                          expected_minutes: int = EXPECTED_INTERVAL_MINUTES) -> tuple[pd.DataFrame, dict]:
    """Read ``source``, coerce its types and classify every row's quality."""
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
    frame["quality_status"] = frame["quality_status"].fillna(STATUS_UNREVIEWED)
    frame["quality_flags"] = ""

    _flag(frame, frame["timestamp_utc"].isna(), FLAG_INVALID_TIMESTAMP)
    _flag(frame, frame["power_kw"].isna(), FLAG_INVALID_POWER)
    _flag(frame, frame["power_kw"] < 0, FLAG_NEGATIVE_POWER)
    _flag(frame, frame["energy_kwh"] < 0, FLAG_NEGATIVE_ENERGY)

    capacity_known = frame["installed_capacity_kwp"].notna()
    impossible = capacity_known & (frame["power_kw"] > frame["installed_capacity_kwp"] * CAPACITY_TOLERANCE_FACTOR)
    _flag(frame, impossible, FLAG_ABOVE_CAPACITY)

    duplicate_mask = frame.duplicated(["location_id", "timestamp_utc"], keep=False)
    _flag(frame, duplicate_mask, FLAG_DUPLICATE)

    frame = frame.sort_values(["location_id", "timestamp_utc"]).reset_index(drop=True)
    gaps = []
    for location_id, group in frame.groupby("location_id", dropna=False):
        deltas = group["timestamp_utc"].diff().dt.total_seconds().div(SECONDS_PER_MINUTE)
        gap_rows = group.index[deltas > expected_minutes * GAP_TOLERANCE_FACTOR]
        for row_index in gap_rows:
            gaps.append({"location_id": location_id, "row": int(row_index),
                         "gap_minutes": float(deltas[row_index])})
            _flag(frame, row_index, FLAG_GAP)

    invalid = frame["quality_flags"].ne("")
    frame.loc[~invalid & frame["quality_status"].eq(STATUS_UNREVIEWED), "quality_status"] = STATUS_VALID
    frame.loc[invalid & frame["quality_status"].eq(STATUS_UNREVIEWED), "quality_status"] = STATUS_FLAGGED

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


def import_measurements(source: Path,
                        measurements_root: Path = MEASUREMENTS_DIR) -> tuple[Path, Path]:
    """Validate ``source`` and write an immutable snapshot directory for it."""
    frame, report = validate_measurements(source)
    snapshot_dir = measurements_root / _snapshot_id(source)
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    validated_path = snapshot_dir / VALIDATED_FILENAME
    report_path = snapshot_dir / REPORT_FILENAME
    write_dataframe(frame, validated_path)

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
        write_dataframe(grouped, snapshot_dir / AGGREGATED_FILENAME)
        report["aggregated_by_district_rows"] = len(grouped)
    else:
        report["aggregation_status"] = "skipped: district and direction columns were not supplied"

    write_json_atomic(report_path, report)
    return validated_path, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--measurements-root", type=Path, default=MEASUREMENTS_DIR)
    args = parser.parse_args()

    validated, report = import_measurements(args.source, args.measurements_root)
    print(f"Validated measurements: {validated}")
    print(f"Quality report: {report}")


if __name__ == "__main__":
    main()
