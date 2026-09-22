"""
Synthetic hourly weather + PV production generator.

Purpose: let the rest of the pipeline (physics model, ML model, API,
dashboard) be built and demoed end-to-end WITHOUT live internet access
or real STEG metering data. It mimics the shape of real Tunisian solar
climatology (strong seasonal cycle, clear daytime bell curve, cloud
noise) closely enough to validate the pipeline logic.

Swap this module out for `weather_client.py` (real Open-Meteo/PVGIS
calls) + real metering data as soon as those are available — every
downstream module consumes the same columns, so nothing else changes.
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)


def _daylength_hours(day_of_year: int, lat: float) -> float:
    """Rough day length approximation (hours) from latitude + day of year."""
    decl = 23.44 * np.sin(np.radians(360 / 365 * (day_of_year - 81)))
    lat_r, decl_r = np.radians(lat), np.radians(decl)
    cos_h = -np.tan(lat_r) * np.tan(decl_r)
    cos_h = np.clip(cos_h, -1, 1)
    return 2 * np.degrees(np.arccos(cos_h)) / 15


def generate_hourly_weather(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """Synthetic hourly GHI (W/m2), temperature (°C), cloud cover (%) series."""
    idx = pd.date_range(start, end, freq="h", inclusive="left")
    rows = []
    for ts in idx:
        doy = ts.dayofyear
        daylen = _daylength_hours(doy, lat)
        solar_noon = 12.5
        hour = ts.hour + ts.minute / 60
        half = daylen / 2
        # Clear-sky bell curve for GHI, zero outside daylight window
        if abs(hour - solar_noon) <= half:
            x = (hour - solar_noon) / half
            clear_sky_ghi = 950 * np.cos(x * np.pi / 2) ** 1.3
            # seasonal peak irradiance factor (higher in summer)
            seasonal = 0.75 + 0.25 * np.cos(2 * np.pi * (doy - 172) / 365)
            clear_sky_ghi *= seasonal
        else:
            clear_sky_ghi = 0.0

        cloud_cover = float(np.clip(RNG.normal(30, 25), 0, 100))
        cloud_atten = 1 - 0.75 * (cloud_cover / 100) ** 1.5
        ghi = max(0.0, clear_sky_ghi * cloud_atten * RNG.normal(1.0, 0.05))

        seasonal_temp = 18 + 10 * np.cos(2 * np.pi * (doy - 202) / 365)
        diurnal_temp = 6 * np.sin((hour - 6) / 24 * 2 * np.pi)
        temp = seasonal_temp + diurnal_temp + RNG.normal(0, 1.5)

        rows.append((ts, ghi, temp, cloud_cover))

    return pd.DataFrame(rows, columns=["timestamp", "ghi_wm2", "temp_c", "cloud_cover_pct"])


def ghi_to_pv_output_kw(ghi_wm2, temp_c, capacity_kwc: float,
                         system_loss_pct: float = 14.0, temp_coeff: float = -0.0038,
                         dust_loss_pct: float = 0.0, noise: bool = True) -> np.ndarray:
    """Simple single-diode-inspired PV physics approximation.
    dust_loss_pct: soiling loss fraction (0-1), higher in Tunisia's arid south."""
    ghi_wm2 = np.asarray(ghi_wm2, dtype=float)
    temp_c = np.asarray(temp_c, dtype=float)
    cell_temp = temp_c + 0.03 * ghi_wm2  # NOCT-style approximation
    temp_derate = 1 + temp_coeff * (cell_temp - 25)
    dc_kw = capacity_kwc * (ghi_wm2 / 1000.0) * temp_derate
    ac_kw = dc_kw * (1 - system_loss_pct / 100.0) * (1 - dust_loss_pct)
    ac_kw = np.clip(ac_kw, 0, None)
    if noise:
        ac_kw *= RNG.normal(1.0, 0.03, size=ac_kw.shape)
        ac_kw = np.clip(ac_kw, 0, None)
    return ac_kw


# ---- Horizon-dependent forecast noise ----
# Real weather forecasts get less accurate the further ahead they look
# (NWP skill degradation). We model this explicitly so the ML model learns
# that uncertainty should widen with lead time — matching what STEG's note
# calls for ("évaluation de l'incertitude") in a way that's physically
# grounded rather than an arbitrary constant band.
HORIZON_BUCKETS = [
    ("nowcast", 0, 1),
    ("+6h", 1, 6),
    ("J+1", 6, 30),
    ("J+2", 30, 54),
    ("J+3", 54, 78),
]

def horizon_bucket_label(horizon_hours) -> np.ndarray:
    horizon_hours = np.asarray(horizon_hours, dtype=float)
    labels = np.full(horizon_hours.shape, "J+3", dtype=object)
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
    scale = 1 + horizon_hours / 20.0  # ~1x at nowcast, ~4.9x at J+3 (78h)

    ghi_noisy = np.clip(ghi_true + RNG.normal(0, 25, size=ghi_true.shape) * scale, 0, None)
    temp_noisy = temp_true + RNG.normal(0, 0.8, size=temp_true.shape) * scale
    cloud_noisy = np.clip(cloud_true + RNG.normal(0, 8, size=cloud_true.shape) * scale, 0, 100)
    return ghi_noisy, temp_noisy, cloud_noisy


def generate_governorate_dataset(governorate, start="2023-01-01", end="2025-01-01") -> pd.DataFrame:
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
    df = generate_hourly_weather(governorate.lat, governorate.lon, start, end)
    df["governorate"] = governorate.name
    direction = getattr(governorate, "direction", None) or getattr(governorate, "district", "Unknown")
    df["district"] = direction
    df["direction"] = direction
    df["steg_district"] = governorate.name
    df["dust_loss_pct"] = governorate.dust_loss_pct

    cap_mwc = getattr(governorate, "installed_capacity_mwc", 10.0)
    df["production_mw"] = ghi_to_pv_output_kw(
        df["ghi_wm2"], df["temp_c"], capacity_kwc=cap_mwc * 1000,
        dust_loss_pct=governorate.dust_loss_pct,
    ) / 1000.0

    df["horizon_hours"] = RNG.uniform(0, 78, size=len(df))
    ghi_fc, temp_fc, cloud_fc = add_forecast_noise(
        df["ghi_wm2"].values, df["temp_c"].values, df["cloud_cover_pct"].values, df["horizon_hours"].values
    )
    df["ghi_wm2"] = ghi_fc
    df["temp_c"] = temp_fc
    df["cloud_cover_pct"] = cloud_fc

    return df


def generate_all(governorates, start="2023-01-01", end="2025-01-01") -> pd.DataFrame:
    return pd.concat([generate_governorate_dataset(g, start, end) for g in governorates],
                      ignore_index=True)


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.steg_districts import STEG_DISTRICTS

    df = generate_all(STEG_DISTRICTS, start="2024-06-01", end="2024-06-03")
    print(df.head(10))
    print(df.groupby("governorate")["production_mw"].max().sort_values(ascending=False).head())
