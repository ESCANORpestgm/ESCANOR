"""Generate reproducible aggregated rooftop-PV training data.

This follows the useful SolNet pattern—historical hourly weather, forecast-like
weather noise that grows with lead time, and cyclical time features—while keeping
this project at STEG district aggregation. It never creates individual rooftop
geometry or individual PV-system rows.

Example:
    python -m data.generate_rooftop_dataset \
        --start 2024-01-01 --end 2025-01-01 \
        --output results/datasets/rooftop_training.csv
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from data.features import add_cyclic_time_features
from data.io import write_dataframe
from data.schema import (
    AGGREGATE_DATASET_COLUMNS,
    add_irradiance_decomposition,
    implied_pv_count,
    interval_hours,
    make_location_id,
)
from data.steg_districts import AVG_UNIT_KWC, STEG_DISTRICTS
from ingestion import synthetic_data
from ingestion.synthetic_data import generate_all

DATASET_VERSION = "rooftop_aggregate_v1"


def _select_districts(districts: list[str] | None):
    """Resolve requested district names, failing on any unknown label."""
    if not districts:
        return STEG_DISTRICTS
    requested = {name.upper() for name in districts}
    selected = [d for d in STEG_DISTRICTS if d.name.upper() in requested]
    missing = requested - {d.name.upper() for d in selected}
    if missing:
        raise ValueError(f"Unknown STEG districts: {sorted(missing)}")
    return selected


def generate_rooftop_dataset(
    start: str,
    end: str,
    seed: int = 42,
    districts: list[str] | None = None,
    frequency: str = "h",
) -> pd.DataFrame:
    """Generate one aggregate row per STEG district at the requested frequency.

    The synthetic source produces true production from standardized rooftop
    assumptions and noisy forecast weather features. PV count is inferred from
    aggregate capacity using the official Prosol average unit size of 3.62 kWc.
    """
    synthetic_data.RNG = np.random.default_rng(seed)
    selected = _select_districts(districts)

    frame = generate_all(selected, start=start, end=end, frequency=frequency).copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp"], utc=True).astype(str)
    frame["location_id"] = frame["steg_district"].map(make_location_id)
    frame["district"] = frame["steg_district"]

    capacity_by_name = {d.name: d.installed_capacity_mwc * 1000 for d in selected}
    tilt_by_name = {d.name: d.tilt_deg for d in selected}
    azimuth_by_name = {d.name: d.azimuth_deg for d in selected}
    frame["system_size_kwc"] = AVG_UNIT_KWC
    frame["installed_capacity_kwp"] = frame["district"].map(capacity_by_name)
    frame["pv_count"] = frame["installed_capacity_kwp"].map(implied_pv_count)
    frame["tilt_deg"] = frame["district"].map(tilt_by_name)
    frame["azimuth_deg"] = frame["district"].map(azimuth_by_name)

    # Standardized aggregate assumptions, not per-rooftop geometry.
    add_irradiance_decomposition(frame)
    frame["power_kw"] = frame["production_mw"] * 1000
    frame["energy_kwh"] = frame["power_kw"] * interval_hours(frequency)
    frame["quality_status"] = "valid"
    frame["source"] = "synthetic_solnet_style"
    frame["dataset_version"] = DATASET_VERSION
    frame = add_cyclic_time_features(frame, "timestamp_utc")

    return frame[list(AGGREGATE_DATASET_COLUMNS)].sort_values(
        ["district", "timestamp_utc"]
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-01-01")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--district", action="append", dest="districts")
    parser.add_argument("--output", type=Path, default=Path("results/datasets/rooftop_training.csv"))
    parser.add_argument("--frequency", default="h", choices=["h", "15min"], help="Sampling interval for simulated observations")
    args = parser.parse_args()

    dataset = generate_rooftop_dataset(args.start, args.end, args.seed, args.districts, args.frequency)
    saved = write_dataframe(dataset, args.output)
    print(f"Generated {len(dataset):,} aggregate rooftop-PV rows across {dataset['district'].nunique()} districts")
    print(f"Saved dataset: {saved}")


if __name__ == "__main__":
    main()
