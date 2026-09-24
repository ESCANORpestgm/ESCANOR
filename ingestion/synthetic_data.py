"""
Synthetic hourly weather + PV production generator.

Purpose: let the rest of the pipeline (physics model, ML model, API,
dashboard) be built and demoed end-to-end WITHOUT live internet access
or real STEG metering data. It mimics the shape of real Tunisian solar
climatology (strong seasonal cycle, clear daytime bell curve, cloud
noise) closely enough to validate the pipeline logic.

Swap this module out for `weather_client.py` (real Open-Meteo/PVGIS
calls) + real metering data as soon as those are available — every
downstream module consumes the same columns (``ingestion.settings``), so
nothing else changes.
"""

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data.climate import (
    EQUINOX_ANCHOR_DAY_OF_YEAR,
    NOCT_CELL_TEMP_RISE,
    REFERENCE_LATITUDE_DEG,
    SOLAR_DECLINATION_AMPLITUDE_DEG,
    STC_REFERENCE_CELL_TEMP_C,
    SYSTEM_LOSS_PCT,
    TEMP_COEFFICIENT_PER_C,
)
from ingestion.settings import (
    CLOUD_COVER_PCT,
    DISTRICT,
    GOVERNORATE,
    DIRECTION,
    GHI_WM2,
    PRODUCTION_MW,
    STEG_DISTRICT,
    TEMP_C,
    TIMESTAMP,
)

RNG = np.random.default_rng(42)

# ── Climatology of the synthetic generator ───────────────────────────────────
# Peak clear-sky irradiance reached at solar noon on the clearest summer day.
PEAK_CLEAR_SKY_GHI_WM2 = 950.0
SOLAR_NOON_LOCAL_HOUR = 12.5
# Exponent shaping the morning/afternoon roll-off of the clear-sky bell curve.
DAYLIGHT_SHAPE_EXPONENT = 1.3
# Fraction of peak irradiance lost to a fully overcast sky.
CLOUD_ATTENUATION_FACTOR = 0.75
# Seasonal temperature cycle: mean, amplitude and the day of the yearly maximum.
SEASONAL_MEAN_TEMP_C = 18.0
SEASONAL_TEMP_AMPLITUDE_C = 10.0
SUMMER_SOLSTICE_DAY = 172
# Day of the yearly temperature maximum (lags the irradiance maximum by ~3 weeks).
TEMPERATURE_PEAK_DAY = 202
DIURNAL_TEMP_AMPLITUDE_C = 6.0
CLOUD_COVER_MEAN_PCT = 30.0
CLOUD_COVER_STD_PCT = 25.0
TEMP_NOISE_STD_C = 1.5
GHI_NOISE_RELATIVE_STD = 0.05
PV_NOISE_RELATIVE_STD = 0.03
W_M2_PER_KW_M2 = 1000.0
KW_PER_MWC = 1000.0
MAX_HORIZON_HOURS = 78.0
DEFAULT_CAPACITY_MWC = 10.0
# NWP skill degrades roughly linearly with lead time; this is the reference
# horizon at which forecast noise equals the nowcast noise.
HORIZON_NOISE_SCALING_HOURS = 20.0
# Lead-time buckets used by ``horizon_bucket_label``.
HORIZON_BUCKETS = [
    ("nowcast", 0, 1),
    ("+6h", 1, 6),
    ("J+1", 6, 30),
    ("J+2", 30, 54),
    ("J+3", 54, 78),
]
OUTER_BUCKET_LABEL = "J+3"


def _daylength_hours(day_of_year: int, lat: float = REFERENCE_LATITUDE_DEG) -> float:
    """Rough day length approximation (hours) from latitude + day of year."""
    decl = SOLAR_DECLINATION_AMPLITUDE_DEG * np.sin(
        np.radians(360 / 365 * (day_of_year - EQUINOX_ANCHOR_DAY_OF_YEAR))
    )
    lat_r, decl_r = np.radians(lat), np.radians(decl)
    cos_h = -np.tan(lat_r) * np.tan(decl_r)
    cos_h = np.clip(cos_h, -1, 1)
    return 2 * np.degrees(np.arccos(cos_h)) / 15


def _clear_sky_ghi(hour: float, day_of_year: int, lat: float) -> float:
    """Clear-sky bell curve (W/m²), zero outside the daylight window."""
    half_day = _daylength_hours(day_of_year, lat) / 2
    if abs(hour - SOLAR_NOON_LOCAL_HOUR) > half_day:
        return 0.0
    x = (hour - SOLAR_NOON_LOCAL_HOUR) / half_day
    bell = PEAK_CLEAR_SKY_GHI_WM2 * np.cos(x * np.pi / 2) ** DAYLIGHT_SHAPE_EXPONENT
    seasonal = 0.75 + 0.25 * np.cos(2 * np.pi * (day_of_year - SUMMER_SOLSTICE_DAY) / 365)
    return float(bell * seasonal)


def _air_temperature(hour: float, day_of_year: int) -> float:
    """Seasonal + diurnal temperature cycle (°C) for one hour of one day."""
    seasonal = SEASONAL_MEAN_TEMP_C + SEASONAL_TEMP_AMPLITUDE_C * np.cos(
        2 * np.pi * (day_of_year - TEMPERATURE_PEAK_DAY) / 365
    )
    diurnal = DIURNAL_TEMP_AMPLITUDE_C * np.sin((hour - 6) / 24 * 2 * np.pi)
    return float(seasonal + diurnal)


def generate_hourly_weather(
    lat: float,
    lon: float,
    start: str,
    end: str,
    frequency: str = "h",
) -> pd.DataFrame:
    """Synthetic weather series; defaults to hourly and supports 15-minute data."""
    idx = pd.date_range(start, end, freq=frequency, inclusive="left")
    rows = []
    for ts in idx:
        doy = ts.dayofyear
        hour = ts.hour + ts.minute / 60
        clear_sky = _clear_sky_ghi(hour, doy, lat)

        cloud_cover = float(np.clip(RNG.normal(CLOUD_COVER_MEAN_PCT, CLOUD_COVER_STD_PCT), 0, 100))
        cloud_atten = 1 - CLOUD_ATTENUATION_FACTOR * (cloud_cover / 100) ** 1.5
        ghi = max(0.0, clear_sky * cloud_atten * RNG.normal(1.0, GHI_NOISE_RELATIVE_STD))
        temp = _air_temperature(hour, doy) + RNG.normal(0, TEMP_NOISE_STD_C)

        rows.append((ts, ghi, temp, cloud_cover))

    return pd.DataFrame(
        rows,
        columns=[TIMESTAMP, GHI_WM2, TEMP_C, CLOUD_COVER_PCT],
    )


def ghi_to_pv_output_kw(
    ghi_wm2,
    temp_c,
    capacity_kwc: float,
    system_loss_pct: float = SYSTEM_LOSS_PCT,
    temp_coeff: float = TEMP_COEFFICIENT_PER_C,
    dust_loss_pct: float = 0.0,
    noise: bool = True,
) -> np.ndarray:
    """Simple single-diode-inspired PV physics approximation.

    dust_loss_pct: soiling loss fraction (0-1), higher in Tunisia's arid south.
    """
    ghi_wm2 = np.asarray(ghi_wm2, dtype=float)
    temp_c = np.asarray(temp_c, dtype=float)
    cell_temp = temp_c + NOCT_CELL_TEMP_RISE * ghi_wm2  # NOCT-style approximation
    temp_derate = 1 + temp_coeff * (cell_temp - STC_REFERENCE_CELL_TEMP_C)
    dc_kw = capacity_kwc * (ghi_wm2 / W_M2_PER_KW_M2) * temp_derate
    ac_kw = dc_kw * (1 - system_loss_pct / 100.0) * (1 - dust_loss_pct)
    ac_kw = np.clip(ac_kw, 0, None)
    if noise:
        ac_kw *= RNG.normal(1.0, PV_NOISE_RELATIVE_STD, size=ac_kw.shape)
        ac_kw = np.clip(ac_kw, 0, None)
    return ac_kw


# ---- Horizon-dependent forecast noise ----
# Real weather forecasts get less accurate the further ahead they look
# (NWP skill degradation). We model this explicitly so the ML model learns
# that uncertainty should widen with lead time — matching what STEG's note
# calls for ("évaluation de l'incertitude") in a way that's physically
# grounded rather than an arbitrary constant band.
def horizon_bucket_label(horizon_hours) -> np.ndarray:
    """Assign each lead time (h) to its forecast-horizon bucket label."""
    horizon_hours = np.asarray(horizon_hours, dtype=float)
    labels = np.full(horizon_hours.shape, OUTER_BUCKET_LABEL, dtype=object)
    for name, lo, hi in HORIZON_BUCKETS:
        mask = (horizon_hours >= lo) & (horizon_hours < hi)
        labels[mask] = name
    return labels


def add_forecast_noise(ghi_true, temp_true, cloud_true, horizon_hours):
    """
    Derive noisy 'forecast' weather from 'true' weather, with noise scaling
    with lead time — this simulates what a real NWP forecast issued now
    would look like for a target `horizon_hours` in the future.
    """
    horizon_hours = np.asarray(horizon_hours, dtype=float)
    scale = 1 + horizon_hours / HORIZON_NOISE_SCALING_HOURS  # ~1x nowcast, ~4.9x at J+3

    ghi_noisy = np.clip(ghi_true + RNG.normal(0, 25, size=ghi_true.shape) * scale, 0, None)
    temp_noisy = temp_true + RNG.normal(0, 0.8, size=temp_true.shape) * scale
    cloud_noisy = np.clip(cloud_true + RNG.normal(0, 8, size=cloud_true.shape) * scale, 0, 100)
    return ghi_noisy, temp_noisy, cloud_noisy


def generate_governorate_dataset(
    governorate,
    start: str = "2023-01-01",
    end: str = "2025-01-01",
    frequency: str = "h",
) -> pd.DataFrame:
    """
    Full synthetic hourly dataset for one governorate, structured to train a
    horizon-aware forecaster:
    - ghi_true/temp_true/cloud_true + dust loss -> production_mw (the target,
      i.e. what was actually produced)
    - a random horizon_hours per row (0-78h) simulates 'this row represents
      a forecast issued horizon_hours before this timestamp'
    - ghi_wm2/temp_c/cloud_cover_pct are the NOISY forecast versions of the
      true weather, with noise scaling with horizon_hours — these are what
      the model actually sees as input features, exactly as a real forecast
      pipeline would only have the (imperfect) NWP forecast to work with.
    """
    df = generate_hourly_weather(governorate.lat, governorate.lon, start, end, frequency=frequency)
    df[GOVERNORATE] = governorate.name
    direction = getattr(governorate, "direction", None) or getattr(governorate, "district", "Unknown")
    df[DISTRICT] = direction
    df[DIRECTION] = direction
    df[STEG_DISTRICT] = governorate.name
    df["dust_loss_pct"] = governorate.dust_loss_pct

    cap_mwc = getattr(governorate, "installed_capacity_mwc", DEFAULT_CAPACITY_MWC)
    df[PRODUCTION_MW] = ghi_to_pv_output_kw(
        df[GHI_WM2], df[TEMP_C], capacity_kwc=cap_mwc * KW_PER_MWC,
        dust_loss_pct=governorate.dust_loss_pct,
    ) / KW_PER_MWC

    df["horizon_hours"] = RNG.uniform(0, MAX_HORIZON_HOURS, size=len(df))
    ghi_fc, temp_fc, cloud_fc = add_forecast_noise(
        df[GHI_WM2].values, df[TEMP_C].values, df[CLOUD_COVER_PCT].values, df["horizon_hours"].values
    )
    df[GHI_WM2] = ghi_fc
    df[TEMP_C] = temp_fc
    df[CLOUD_COVER_PCT] = cloud_fc

    return df


def generate_all(
    governorates,
    start: str = "2023-01-01",
    end: str = "2025-01-01",
    frequency: str = "h",
) -> pd.DataFrame:
    """Concatenate the horizon-aware synthetic history of every district."""
    return pd.concat(
        [generate_governorate_dataset(g, start, end, frequency=frequency) for g in governorates],
        ignore_index=True,
    )


if __name__ == "__main__":
    from data.steg_districts import STEG_DISTRICTS

    frame = generate_all(STEG_DISTRICTS, start="2024-06-01", end="2024-06-03")
    print(frame.head(10))
    print(frame.groupby(GOVERNORATE)[PRODUCTION_MW].max().sort_values(ascending=False).head())
