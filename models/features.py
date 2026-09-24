"""Model feature contract: which columns the LightGBM models see, and how they
are derived from a weather/production frame.

The encodings here are *fitted into the persisted model artifacts*, so they are
deliberately frozen: changing a formula silently invalidates every saved model
and the calibration computed against it. Anything that adjusts this module must
be followed by a full retrain.

Note that the dataset generators in ``data/`` use a slightly different (finer)
cyclical encoding; the two are not interchangeable and the model always
recomputes its own features from the raw weather columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.climate import (
    CLEAR_SKY_GHI_WM2,
    EQUINOX_ANCHOR_DAY_OF_YEAR,
    NIGHT_END_HOUR,
    NIGHT_PRODUCTION_TOLERANCE_MW,
    NIGHT_START_HOUR,
    REFERENCE_LATITUDE_DEG,
    SOLAR_DECLINATION_AMPLITUDE_DEG,
    SOLAR_HOUR_ANGLE_DEG_PER_HOUR,
    SOLAR_NOON_CLOCK_HOUR,
    STC_REFERENCE_CELL_TEMP_C,
    ZONE_IDS,
    district_to_zone,
)
from data.schema import DEFAULT_WIND_SPEED_MS, DHI_SHARE, DNI_SHARE

# ── Feature column lists ─────────────────────────────────────────────────────
# Tier 1: always available from either the live weather feed or the district
# metadata. Tier 2: derived from the irradiance decomposition. Tier 3: physics
# and spatial priors added in feature-engineering v2.
BASE_FEATURES = [
    "ghi_wm2", "temp_c", "cloud_cover_pct",
    "hour", "day_of_year_sin", "day_of_year_cos", "capacity_mwc",
    "dust_loss_pct", "horizon_hours",
]
EXTENDED_FEATURES = [
    "dni_wm2", "dhi_wm2", "wind_speed_ms",
    "ghi_x_temp",       # GHI × (temp_c - 25): temperature efficiency interaction
    "rolling_ghi_3h",   # 3-hour rolling average GHI (per governorate)
]
PHYSICS_FEATURES = [
    "cos_zenith",       # Solar elevation proxy (Tunisia ~35°N)
    "clearsky_index",   # GHI / theoretical clear-sky GHI
    "hour_sin",         # Cyclical hour encoding (sin)
    "hour_cos",         # Cyclical hour encoding (cos)
    "climate_zone_id",  # 0=coastal_north, 1=central_coastal, 2=inland, 3=south
]

# v1 feature list, kept for artifacts persisted before the physics tier existed.
FEATURE_COLS = BASE_FEATURES + EXTENDED_FEATURES

# Fallbacks applied when a district is missing from a lookup table.
DEFAULT_CAPACITY_MWC = 10.0
DEFAULT_DUST_LOSS_PCT = 0.02
# Districts outside the four mapped climate zones (model-side convention: the
# inland cluster, deliberately different from ``data.climate``'s default).
FALLBACK_CLIMATE_ZONE = "inland_central"

# Data-quality gate thresholds.
PRODUCTION_OVER_CAPACITY_RATIO = 1.15   # inverter headroom, DC/AC + tolerance
NIGHT_MIN_PRODUCTION_MW = 0.5           # reported output tolerated at night

# Feature-engineering parameters.
ROLLING_GHI_WINDOW_HOURS = 3
CLEARSKY_INDEX_MAX = 2.0
DAY_OF_YEAR_CYCLE_DAYS = 365.0
HOURS_IN_DAY = 24.0
DEGREES_PER_HOUR_TO_RADIANS = np.pi / 180.0


def get_feature_cols() -> list[str]:
    """Return the full v2 feature column list including physics features."""
    return BASE_FEATURES + EXTENDED_FEATURES + PHYSICS_FEATURES


def _get_climate_zone(governorate: str) -> int:
    """Integer climate zone for a district, defaulting to the inland cluster."""
    zone = district_to_zone(governorate) or FALLBACK_CLIMATE_ZONE
    return ZONE_IDS.get(zone, ZONE_IDS[FALLBACK_CLIMATE_ZONE])


def validate_training_data(df: pd.DataFrame, capacity_lookup: dict) -> pd.DataFrame:
    """Filter out physically impossible or suspicious rows before training.

    Removes:
    - Negative production
    - Production exceeding 115% of installed capacity
    - Nighttime rows (20:00–05:00) with significant reported production
    - Rows with missing weather or production values
    """
    df = df.copy()
    df = df[df["production_mw"] >= 0]
    df["cap_mwc"] = df["governorate"].map(capacity_lookup).fillna(DEFAULT_CAPACITY_MWC)
    df = df[df["production_mw"] <= df["cap_mwc"] * PRODUCTION_OVER_CAPACITY_RATIO]
    ts = pd.to_datetime(df["timestamp"])
    hour = ts.dt.hour
    night_mask = (hour >= NIGHT_START_HOUR) | (hour <= NIGHT_END_HOUR)
    df = df[~(night_mask & (df["production_mw"] > NIGHT_MIN_PRODUCTION_MW))]
    df = df.dropna(subset=["ghi_wm2", "temp_c", "production_mw"])
    df = df.drop(columns=["cap_mwc"])
    return df.reset_index(drop=True)


def _add_solar_position_features(df: pd.DataFrame, day_of_year: pd.Series) -> pd.DataFrame:
    """``cos_zenith`` + ``clearsky_index`` for the Tunisian reference latitude."""
    lat_rad = np.radians(REFERENCE_LATITUDE_DEG)
    decimal_hour = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    hour_angle = np.radians(
        SOLAR_HOUR_ANGLE_DEG_PER_HOUR * (decimal_hour - SOLAR_NOON_CLOCK_HOUR)
    )
    declination = np.radians(
        SOLAR_DECLINATION_AMPLITUDE_DEG
        * np.sin(2 * np.pi * (day_of_year - EQUINOX_ANCHOR_DAY_OF_YEAR) / DAY_OF_YEAR_CYCLE_DAYS)
    )
    cos_zenith = (
        np.sin(lat_rad) * np.sin(declination)
        + np.cos(lat_rad) * np.cos(declination) * np.cos(hour_angle)
    )
    df["cos_zenith"] = np.clip(cos_zenith, 0, 1)

    # Clear-sky index: ratio of actual GHI to theoretical clear-sky GHI.
    # Values > 1.0 indicate reflection/cloud-edge enhancement; < 0.5 thick clouds.
    clear_sky_ghi = CLEAR_SKY_GHI_WM2 * df["cos_zenith"]
    df["clearsky_index"] = np.clip(
        df["ghi_wm2"] / clear_sky_ghi.replace(0, np.nan), 0, CLEARSKY_INDEX_MAX
    ).fillna(1.0)
    return df


def add_time_features(
    df: pd.DataFrame,
    capacity_lookup: dict,
    dust_lookup: dict | None = None,
) -> pd.DataFrame:
    """Enrich df with all model features, handling missing optional columns gracefully."""
    df = df.copy()

    # Core time features
    df["hour"] = df["timestamp"].dt.hour
    doy = df["timestamp"].dt.dayofyear
    df["day_of_year_sin"] = np.sin(2 * np.pi * doy / DAY_OF_YEAR_CYCLE_DAYS)
    df["day_of_year_cos"] = np.cos(2 * np.pi * doy / DAY_OF_YEAR_CYCLE_DAYS)
    df["capacity_mwc"] = df["governorate"].map(capacity_lookup)

    if "dust_loss_pct" not in df.columns:
        df["dust_loss_pct"] = (
            df["governorate"].map(dust_lookup) if dust_lookup else DEFAULT_DUST_LOSS_PCT
        )

    if "horizon_hours" not in df.columns:
        now = pd.Timestamp.now().floor("h")
        df["horizon_hours"] = (df["timestamp"] - now).dt.total_seconds() / 3600.0
        df["horizon_hours"] = df["horizon_hours"].clip(lower=0)

    # Extended features (fill defaults if column absent)
    if "dni_wm2" not in df.columns:
        df["dni_wm2"] = df["ghi_wm2"] * DNI_SHARE
    if "dhi_wm2" not in df.columns:
        df["dhi_wm2"] = df["ghi_wm2"] * DHI_SHARE
    if "wind_speed_ms" not in df.columns:
        df["wind_speed_ms"] = DEFAULT_WIND_SPEED_MS

    # GHI × (temp - 25): captures efficiency loss at high temperature
    df["ghi_x_temp"] = df["ghi_wm2"] * (df["temp_c"] - STC_REFERENCE_CELL_TEMP_C)

    # 3-hour rolling average GHI per governorate (smooths cloud transients)
    df = df.sort_values(["governorate", "timestamp"])
    df["rolling_ghi_3h"] = (
        df.groupby("governorate")["ghi_wm2"]
        .transform(lambda s: s.rolling(ROLLING_GHI_WINDOW_HOURS, min_periods=1).mean())
    )

    # ── Solar physics + spatial priors ──────────────────────────────────────
    df = _add_solar_position_features(df, doy)

    # Cyclical hour encoding (captures smooth dawn/dusk transitions)
    df["hour_sin"] = np.sin(2 * np.pi * df["timestamp"].dt.hour / HOURS_IN_DAY)
    df["hour_cos"] = np.cos(2 * np.pi * df["timestamp"].dt.hour / HOURS_IN_DAY)

    # Climate zone ID (0-3) for spatial generalization
    df["climate_zone_id"] = df["governorate"].apply(_get_climate_zone).astype(float)

    return df


__all__ = [
    "BASE_FEATURES",
    "DEFAULT_CAPACITY_MWC",
    "DEFAULT_DUST_LOSS_PCT",
    "EXTENDED_FEATURES",
    "FEATURE_COLS",
    "PHYSICS_FEATURES",
    "add_time_features",
    "get_feature_cols",
    "validate_training_data",
]
