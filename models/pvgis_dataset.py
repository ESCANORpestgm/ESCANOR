"""Loader for the generated PVGIS rooftop dataset, shared by the history and
validation-report builders.

The dataset is written by ``data.generate_pvgis_rooftop_data`` at 15-minute
resolution, one row per (timestamp, district, direction). The model scores
hourly rows, so every consumer needs the same two steps:

  1. ``resample_hourly`` — average the numeric weather/production columns per
     (timestamp, district, direction), optionally keeping the descriptive columns
     that identify the installation.
  2. ``to_model_schema`` — rename the dataset columns to the names the feature
     builder expects (``timestamp``, ``governorate``, ``production_mw``).

``models.history`` keeps the descriptive columns (the dataset carries a real
``horizon_hours`` shading value per installation); ``models.validation_report``
drops them, because the deployed validation metrics were produced on the
weather-only frame and must stay comparable to the registry records.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from data.paths import ROOFTOP_TRAINING_DATASET_PATH

# Hourly resampling cadence applied to the 15-minute dataset
RESAMPLE_FREQUENCY = "h"
# Columns averaged over each (timestamp, district, direction) group
HOURLY_MEAN_COLUMNS = [
    "power_kw", "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c",
    "cloud_cover_pct", "wind_speed_ms", "energy_kwh",
]
# Columns constant within a group, carried through with their first value
HOURLY_FIRST_COLUMNS = [
    "location_id", "pv_count", "system_size_kwc", "installed_capacity_kwp",
    "tilt_deg", "azimuth_deg", "horizon_hours", "quality_status", "source", "dataset_version",
]
GROUP_KEYS = ["timestamp_utc", "district", "direction"]
# kW → MW, the unit the national aggregation and the model both work in
KW_PER_MW = 1000.0


def resample_hourly(raw: pd.DataFrame, *, include_descriptive_columns: bool = True) -> pd.DataFrame:
    """Average a 15-minute PVGIS frame into hourly rows, one per group.

    ``include_descriptive_columns`` carries the installation attributes (notably
    ``horizon_hours``, a model feature) through the aggregation. Turning it off
    reproduces the weather-only frame the deployed validation report was scored
    on, where ``horizon_hours`` is derived from the timestamp instead.
    """
    frame = cast(pd.DataFrame, raw.copy())
    frame["timestamp_utc"] = (
        pd.to_datetime(frame["timestamp_utc"], utc=True).dt.floor(RESAMPLE_FREQUENCY).astype(str)
    )
    hourly = frame.groupby(GROUP_KEYS, as_index=False)[HOURLY_MEAN_COLUMNS].mean()
    if not include_descriptive_columns:
        return hourly
    for column in HOURLY_FIRST_COLUMNS:
        if column in frame.columns:
            first = frame.groupby(GROUP_KEYS, as_index=False)[column].first()[column]
            hourly[column] = first.values
    return hourly


def to_model_schema(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename the PVGIS dataset columns onto the model's expected schema."""
    model_frame = cast(pd.DataFrame, frame.copy())
    model_frame["timestamp"] = pd.to_datetime(model_frame["timestamp_utc"], utc=True).dt.tz_localize(None)
    model_frame["governorate"] = model_frame["district"]
    model_frame["steg_district"] = model_frame["district"]
    model_frame["production_mw"] = model_frame["power_kw"] / KW_PER_MW
    return model_frame


def load_hourly_dataset(path: Path = ROOFTOP_TRAINING_DATASET_PATH, *,
                        include_descriptive_columns: bool = True) -> pd.DataFrame:
    """Read ``path`` and return the hourly frame in model schema."""
    if not path.is_file():
        raise FileNotFoundError(f"PVGIS dataset not found: {path}")
    return to_model_schema(resample_hourly(
        pd.read_csv(path), include_descriptive_columns=include_descriptive_columns
    ))


__all__ = [
    "GROUP_KEYS",
    "HOURLY_FIRST_COLUMNS",
    "HOURLY_MEAN_COLUMNS",
    "KW_PER_MW",
    "RESAMPLE_FREQUENCY",
    "load_hourly_dataset",
    "resample_hourly",
    "to_model_schema",
]
