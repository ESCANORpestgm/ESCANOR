"""Generate aggregate 15-minute rooftop production from PVGIS district estimates.

PVGIS is queried once per STEG commercial district using the district
coordinate and aggregate installed capacity. The resulting rows remain
aggregate district observations; no individual rooftop geometry is modeled.

Example:
    python -m data.generate_pvgis_rooftop_data \
        --start 2020-01-01 --end 2025-01-01
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import cast

import numpy as np
import pandas as pd

from data.steg_districts import AVG_UNIT_KWC, STEG_DISTRICTS
from ingestion.pvgis_client import fetch_district_hourly

DATASET_VERSION = "rooftop_aggregate_15min_pvgis_v1"


def _cyclic_features(frame: pd.DataFrame) -> pd.DataFrame:
    timestamps = pd.to_datetime(frame["timestamp_utc"], utc=True)
    hour = timestamps.dt.hour + timestamps.dt.minute / 60
    day_of_year = timestamps.dt.dayofyear
    frame["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["day_of_year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    frame["day_of_year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    return frame


def generate_pvgis_dataset(
    start: str,
    end: str,
    cache_dir: Path = Path("results/datasets/pvgis_cache"),
) -> pd.DataFrame:
    """Build the existing training schema from cached/fetched PVGIS data."""
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    if end_ts <= start_ts:
        raise ValueError("end must be later than start")
    start_year = int(start_ts.year)
    end_year = int((end_ts - pd.Timedelta(seconds=1)).year)
    frames: list[pd.DataFrame] = []

    for district in STEG_DISTRICTS:
        filename = re.sub(r"[^A-Za-z0-9_-]+", "_", district.name.lower())
        hourly = fetch_district_hourly(
            latitude=district.lat,
            longitude=district.lon,
            start_year=start_year,
            end_year=end_year,
            tilt=district.tilt_deg,
            azimuth=district.azimuth_deg,
            peak_power_kwp=district.installed_capacity_mwc * 1000,
            cache_path=cache_dir / f"{filename}_{start_year}_{end_year}.json",
        )
        hourly = hourly.set_index("timestamp_utc")
        hourly_start = pd.Timestamp(hourly.index.min())
        hourly_end = pd.Timestamp(hourly.index.max())
        target_index = pd.date_range(
            start=max(start_ts, hourly_start),
            end=min(end_ts - pd.Timedelta(minutes=15), hourly_end),
            freq="15min",
            tz="UTC",
        )
        if target_index.empty:
            continue
        resampled = hourly.reindex(hourly.index.union(target_index)).sort_index().interpolate(method="time")
        resampled = resampled.reindex(target_index).reset_index(names="timestamp_utc")
        resampled["district"] = district.name
        resampled["direction"] = district.direction
        resampled["location_id"] = "district:" + district.name
        resampled["pv_count"] = round(district.installed_capacity_mwc * 1000 / AVG_UNIT_KWC)
        resampled["system_size_kwc"] = AVG_UNIT_KWC
        resampled["installed_capacity_kwp"] = district.installed_capacity_mwc * 1000
        resampled["tilt_deg"] = district.tilt_deg
        resampled["azimuth_deg"] = district.azimuth_deg
        resampled["horizon_hours"] = 0.0
        resampled["energy_kwh"] = resampled["power_kw"] * 0.25
        resampled["quality_status"] = "valid"
        resampled["source"] = "pvgis_district_model"
        resampled["dataset_version"] = DATASET_VERSION
        frames.append(resampled)

    if not frames:
        raise ValueError("PVGIS returned no rows for the requested date range")
    result = pd.concat(frames, ignore_index=True)
    selected = result[
        [
            "timestamp_utc", "location_id", "district", "direction", "pv_count",
            "system_size_kwc", "installed_capacity_kwp", "tilt_deg", "azimuth_deg",
            "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c", "cloud_cover_pct",
            "wind_speed_ms", "horizon_hours", "power_kw", "energy_kwh",
            "quality_status", "source", "dataset_version",
        ]
    ].sort_values(["district", "timestamp_utc"]).reset_index(drop=True)
    return _cyclic_features(cast(pd.DataFrame, selected))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2021-01-01")
    parser.add_argument("--output", type=Path, default=Path("results/datasets/rooftop_actual_15min.csv"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/datasets/pvgis_cache"))
    args = parser.parse_args()

    frame = generate_pvgis_dataset(args.start, args.end, args.cache_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == ".parquet":
        frame.to_parquet(args.output, index=False)
    else:
        frame.to_csv(args.output, index=False)
    print(f"Generated {len(frame):,} PVGIS-derived 15-minute aggregate rows across {frame['district'].nunique()} districts")
    print(f"Saved PVGIS dataset: {args.output}")


if __name__ == "__main__":
    main()
