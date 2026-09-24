"""Canonical column contract for aggregate district training datasets.

Every generator in ``data/`` produces exactly ``AGGREGATE_DATASET_COLUMNS`` in
that order, so a dataset built from synthetic weather, from PVGIS, or from a
future STEG metering export feeds the same training adapter without
per-source special-casing.

Rows are always one aggregate STEG commercial district × one timestamp — the
platform never materialises individual rooftop systems.
"""

from __future__ import annotations

import pandas as pd

from data.steg_districts import AVG_UNIT_KWC, StegDistrict
from ingestion.settings import (
    CLOUD_COVER_PCT,
    GHI_WM2,
    TEMP_C,
    TIMESTAMP_UTC,
    WIND_SPEED_MS,
)

# ── Identity / provenance ────────────────────────────────────────────────────
DISTRICT_ID = "district"
DIRECTION_ID = "direction"
LOCATION_ID = "location_id"
DATASET_VERSION = "dataset_version"
SOURCE = "source"
QUALITY_STATUS = "quality_status"

# ── Irradiance decomposition ─────────────────────────────────────────────────
# The synthetic source reports GHI only; beam/diffuse are split with the ratio
# used everywhere in the platform (0.60 direct / 0.40 diffuse of GHI).
DNI_SHARE = 0.60
DHI_SHARE = 1.0 - DNI_SHARE
DEFAULT_WIND_SPEED_MS = 3.0

KW_PER_MW = 1000.0

AGGREGATE_DATASET_COLUMNS: tuple[str, ...] = (
    TIMESTAMP_UTC, LOCATION_ID, DISTRICT_ID, DIRECTION_ID, "pv_count",
    "system_size_kwc", "installed_capacity_kwp", "tilt_deg", "azimuth_deg",
    GHI_WM2, "dni_wm2", "dhi_wm2", TEMP_C, CLOUD_COVER_PCT,
    WIND_SPEED_MS, "horizon_hours",
    "hour_sin", "hour_cos", "day_of_year_sin", "day_of_year_cos",
    "power_kw", "energy_kwh", QUALITY_STATUS, SOURCE, DATASET_VERSION,
)


def make_location_id(district: str) -> str:
    """Stable join key between forecasts, measurements and district metadata."""
    return f"district:{district}"


def implied_pv_count(capacity_kwp: float) -> int:
    """Rooftop units represented by an aggregate district capacity."""
    return int(round(capacity_kwp / AVG_UNIT_KWC))


def energy_from_power(power_kw: pd.Series, interval: float) -> pd.Series:
    """Energy produced in one sampling interval (kWh) from average power (kW)."""
    return power_kw * interval


def interval_hours(frequency: str) -> float:
    """Sampling interval of a pandas frequency alias, in hours (``"15min"`` → 0.25)."""
    delta = pd.Timedelta("1h") if frequency in {"h", "H", "1h"} else pd.Timedelta(frequency)
    return delta.total_seconds() / 3600.0


def add_district_metadata(
    frame: pd.DataFrame,
    district: StegDistrict,
    *,
    horizon_hours: float | pd.Series,
    energy_interval_hours: float,
    source: str,
    dataset_version: str,
) -> pd.DataFrame:
    """Attach the aggregate fleet columns shared by every district dataset."""
    capacity_kwp = district.installed_capacity_mwc * KW_PER_MW
    frame[DISTRICT_ID] = district.name
    frame[DIRECTION_ID] = district.direction
    frame[LOCATION_ID] = make_location_id(district.name)
    frame["pv_count"] = implied_pv_count(capacity_kwp)
    frame["system_size_kwc"] = AVG_UNIT_KWC
    frame["installed_capacity_kwp"] = capacity_kwp
    frame["tilt_deg"] = district.tilt_deg
    frame["azimuth_deg"] = district.azimuth_deg
    frame["horizon_hours"] = horizon_hours
    frame["energy_kwh"] = energy_from_power(frame["power_kw"], energy_interval_hours)
    frame[QUALITY_STATUS] = "valid"
    frame[SOURCE] = source
    frame[DATASET_VERSION] = dataset_version
    return frame


def add_irradiance_decomposition(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive DNI/DHI/wind columns when the upstream source reports GHI only."""
    if "dni_wm2" not in frame.columns:
        frame["dni_wm2"] = frame[GHI_WM2] * DNI_SHARE
    if "dhi_wm2" not in frame.columns:
        frame["dhi_wm2"] = frame[GHI_WM2] * DHI_SHARE
    if WIND_SPEED_MS not in frame.columns:
        frame[WIND_SPEED_MS] = DEFAULT_WIND_SPEED_MS
    return frame


def select_dataset_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Project to ``AGGREGATE_DATASET_COLUMNS``, failing loudly on a broken source."""
    missing = [column for column in AGGREGATE_DATASET_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")
    return frame[list(AGGREGATE_DATASET_COLUMNS)]


__all__ = [
    "AGGREGATE_DATASET_COLUMNS",
    "DATASET_VERSION",
    "DEFAULT_WIND_SPEED_MS",
    "DHI_SHARE",
    "DISTRICT_ID",
    "DIRECTION_ID",
    "DNI_SHARE",
    "KW_PER_MW",
    "LOCATION_ID",
    "QUALITY_STATUS",
    "SOURCE",
    "add_district_metadata",
    "add_irradiance_decomposition",
    "energy_from_power",
    "implied_pv_count",
    "interval_hours",
    "make_location_id",
    "select_dataset_columns",
]
