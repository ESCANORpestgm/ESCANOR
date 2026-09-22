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

import argparse
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from data.steg_districts import AVG_UNIT_KWC, STEG_DISTRICTS
from ingestion import synthetic_data
from ingestion.synthetic_data import generate_all


DATASET_VERSION = "rooftop_aggregate_v1"


def _cyclic_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    hour = timestamps.dt.hour + timestamps.dt.minute / 60
    day_of_year = timestamps.dt.dayofyear
    frame["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["day_of_year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    frame["day_of_year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    return frame


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
    selected = STEG_DISTRICTS
    if districts:
        requested = {name.upper() for name in districts}
        selected = [district for district in STEG_DISTRICTS if district.name.upper() in requested]
        missing = requested - {district.name.upper() for district in selected}
        if missing:
            raise ValueError(f"Unknown STEG districts: {sorted(missing)}")

    frame = generate_all(selected, start=start, end=end, frequency=frequency).copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frame["timestamp_utc"] = timestamps.astype(str)
    frame["location_id"] = "district:" + frame["steg_district"].astype(str)
    frame["district"] = frame["steg_district"]
    frame["direction"] = frame["direction"].astype(str)
    frame["system_size_kwc"] = AVG_UNIT_KWC
    capacity_by_name = {district.name: district.installed_capacity_mwc * 1000 for district in selected}
    frame["installed_capacity_kwp"] = frame["governorate"].map(lambda name: capacity_by_name.get(name))
    frame["pv_count"] = np.rint(frame["installed_capacity_kwp"] / AVG_UNIT_KWC).astype("int64")
    tilt_by_name = {district.name: district.tilt_deg for district in selected}
    azimuth_by_name = {district.name: district.azimuth_deg for district in selected}
    frame["tilt_deg"] = frame["governorate"].map(lambda name: tilt_by_name.get(name))
    frame["azimuth_deg"] = frame["governorate"].map(lambda name: azimuth_by_name.get(name))

    # These are standardized aggregate assumptions, not per-rooftop geometry.
    frame["dni_wm2"] = frame["ghi_wm2"] * 0.60
    frame["dhi_wm2"] = frame["ghi_wm2"] * 0.40
    frame["wind_speed_ms"] = 3.0
    frame["power_kw"] = frame["production_mw"] * 1000
    interval_hours = pd.Timedelta(frequency).total_seconds() / 3600
    frame["energy_kwh"] = frame["power_kw"] * interval_hours
    frame["quality_status"] = "valid"
    frame["source"] = "synthetic_solnet_style"
    frame["dataset_version"] = DATASET_VERSION
    frame = _cyclic_features(frame)

    columns = [
        "timestamp_utc", "location_id", "district", "direction", "pv_count",
        "system_size_kwc", "installed_capacity_kwp", "tilt_deg", "azimuth_deg",
        "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c", "cloud_cover_pct",
        "wind_speed_ms", "horizon_hours", "hour_sin", "hour_cos",
        "day_of_year_sin", "day_of_year_cos", "power_kw", "energy_kwh",
        "quality_status", "source", "dataset_version",
    ]
    return cast(pd.DataFrame, frame[columns].sort_values(["district", "timestamp_utc"]).reset_index(drop=True))


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == ".parquet":
        dataset.to_parquet(args.output, index=False)
    else:
        dataset.to_csv(args.output, index=False)
    print(f"Generated {len(dataset):,} aggregate rooftop-PV rows across {dataset['district'].nunique()} districts")
    print(f"Saved dataset: {args.output}")


if __name__ == "__main__":
    main()
