"""Generate aggregate 15-minute rooftop production from PVGIS district estimates.

PVGIS is queried once per STEG commercial district using the district
coordinate and aggregate installed capacity. The resulting rows remain
aggregate district observations; no individual rooftop geometry is modeled.

Example:
    python -m data.generate_pvgis_rooftop_data \
        --start 2020-01-01 --end 2025-01-01
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import re
from pathlib import Path

import pandas as pd

from data.features import add_cyclic_time_features
from data.io import write_dataframe
from data.schema import (
    AGGREGATE_DATASET_COLUMNS,
    add_district_metadata,
)
from data.steg_districts import STEG_DISTRICTS
from ingestion.pvgis_client import fetch_district_hourly
from data import paths

DATASET_VERSION = "rooftop_aggregate_15min_pvgis_v1"
SOURCE = "pvgis_district_model"


def _cache_filename(district_name: str, start_year: int, end_year: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", district_name.lower())
    return f"{slug}_{start_year}_{end_year}.json"


def _resample_to_15min(hourly: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    """Interpolate an hourly PVGIS frame onto the requested 15-minute UTC grid."""
    hourly = hourly.set_index("timestamp_utc")
    target_index = pd.date_range(
        start=max(start_ts, pd.Timestamp(hourly.index.min())),
        end=min(end_ts - pd.Timedelta(minutes=15), pd.Timestamp(hourly.index.max())),
        freq="15min",
        tz="UTC",
    )
    if target_index.empty:
        return pd.DataFrame()
    resampled = (
        hourly.reindex(hourly.index.union(target_index)).sort_index().interpolate(method="time")
    ).reindex(target_index).reset_index(names="timestamp_utc")
    return resampled


def generate_pvgis_dataset(
    start: str,
    end: str,
    cache_dir: Path = paths.PVGIS_CACHE_DIR,
) -> pd.DataFrame:
    """Build the canonical training schema from cached/fetched PVGIS data."""
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    if end_ts <= start_ts:
        raise ValueError("end must be later than start")
    start_year = int(start_ts.year)
    end_year = int((end_ts - pd.Timedelta(seconds=1)).year)
    frames: list[pd.DataFrame] = []

    for district in STEG_DISTRICTS:
        hourly = fetch_district_hourly(
            latitude=district.lat,
            longitude=district.lon,
            start_year=start_year,
            end_year=end_year,
            tilt=district.tilt_deg,
            azimuth=district.azimuth_deg,
            peak_power_kwp=district.installed_capacity_mwc * 1000,
            cache_path=Path(cache_dir) / _cache_filename(district.name, start_year, end_year),
        )
        resampled = _resample_to_15min(hourly, start_ts, end_ts)
        if resampled.empty:
            continue
        add_district_metadata(
            resampled,
            district,
            horizon_hours=0.0,
            energy_interval_hours=0.25,
            source=SOURCE,
            dataset_version=DATASET_VERSION,
        )
        frames.append(resampled)

    if not frames:
        raise ValueError("PVGIS returned no rows for the requested date range")
    result = pd.concat(frames, ignore_index=True)
    result = add_cyclic_time_features(result, "timestamp_utc")
    return result[list(AGGREGATE_DATASET_COLUMNS)].sort_values(
        ["district", "timestamp_utc"]
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2021-01-01")
    parser.add_argument("--output", type=Path, default=paths.ROOFTOP_TRAINING_DATASET_PATH)
    parser.add_argument("--cache-dir", type=Path, default=paths.PVGIS_CACHE_DIR)
    args = parser.parse_args()

    frame = generate_pvgis_dataset(args.start, args.end, args.cache_dir)
    saved = write_dataframe(frame, args.output)
    print(f"Generated {len(frame):,} PVGIS-derived 15-minute aggregate rows across {frame['district'].nunique()} districts")
    print(f"Saved PVGIS dataset: {saved}")


if __name__ == "__main__":
    main()
