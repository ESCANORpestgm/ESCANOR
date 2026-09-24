"""
Real weather/irradiance data clients — async-first, concurrent fetching.

Changes vs. original:
- fetch_all_governorates_concurrent(): uses httpx + asyncio.gather so all
  24 governorate requests fire in parallel (O(latency) instead of O(N*latency)).
- build_live_weather_dataframe() now wraps the async version for synchronous
  callers (the FastAPI lifespan scheduler, retrain scripts, etc.).
- DNI and wind_speed_10m are now included in the returned DataFrame so the
  ML model can use them as features.

Sources:
- Open-Meteo: free, no API key, hourly forecast up to 16 days.
- PVGIS (JRC): free, no API key, historical hourly irradiance.
"""

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import asyncio
from datetime import date, timedelta

import httpx
import pandas as pd

from ingestion.settings import (
    CLOUD_COVER_PCT,
    DIRECTION,
    DISTRICT,
    DHI_WM2,
    DNI_WM2,
    GHI_WM2,
    GOVERNORATE,
    LOCAL_TIMEZONE,
    MAX_FORECAST_DAYS,
    MISSING_CLOUD_COVER_PCT,
    MISSING_GHI_WM2,
    MISSING_TEMP_C,
    MISSING_WIND_SPEED_MS,
    OPEN_METEO_URL,
    STEG_DISTRICT,
    TEMP_C,
    TIMESTAMP,
    WEATHER_SINGLE_FETCH_TIMEOUT_SECONDS,
    WEATHER_TIMEOUT_SECONDS,
    WIND_SPEED_MS,
)

# Extended variable set — DNI, DHI, and wind speed are now included so the
# ML feature engineering step can use them.
HOURLY_VARS = [
    "shortwave_radiation",          # GHI (W/m²)
    "diffuse_radiation",            # DHI (W/m²)
    "direct_normal_irradiance",     # DNI (W/m²)
    "temperature_2m",
    "cloud_cover",
    "wind_speed_10m",
]


def _forecast_params(lat: float, lon: float, days_ahead: int) -> dict:
    """Shared Open-Meteo query parameters for the async and sync fetchers."""
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "forecast_days": min(days_ahead + 1, MAX_FORECAST_DAYS),
        "timezone": LOCAL_TIMEZONE,
    }


async def _fetch_one_async(client: httpx.AsyncClient, lat: float, lon: float,
                           days_ahead: int) -> dict:
    """Single async GET to Open-Meteo for one location."""
    resp = await client.get(OPEN_METEO_URL, params=_forecast_params(lat, lon, days_ahead))
    resp.raise_for_status()
    return resp.json()


async def fetch_all_governorates_concurrent(governorates, days_ahead: int = 3) -> dict:
    """
    Fetch Open-Meteo forecasts for ALL districts/governorates concurrently.
    Accepts Governorate objects or StegDistrict objects (duck-typed: needs .name, .lat, .lon).
    Returns {name: forecast_json | {"error": str}}.
    Total wall-clock time ≈ single-request latency (≈1-2 s) regardless of N.
    """
    async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT_SECONDS) as client:
        tasks = {
            g.name: _fetch_one_async(client, g.lat, g.lon, days_ahead)
            for g in governorates
        }
        names = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    out = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            out[name] = {"error": str(result)}
        else:
            out[name] = result
    return out


def build_live_weather_dataframe(governorates, days_ahead: int = 3) -> pd.DataFrame:
    """
    Fetch REAL Open-Meteo forecasts for every district/governorate concurrently
    and assemble them into the shared pipeline schema:

        timestamp, ghi_wm2, dni_wm2, dhi_wm2, wind_speed_ms,
        temp_c, cloud_cover_pct, governorate (or steg_district name),
        district (Direction for StegDistrict, regional group for Governorate),
        steg_district (same as governorate field for STEG district pipeline),
        direction (Direction de Distribution, if available)

    Accepts either Governorate or StegDistrict objects (duck-typed).
    Raises httpx.HTTPError / RuntimeError if the network/API is unavailable —
    callers should catch this and fall back to synthetic data.
    """
    raw = asyncio.run(fetch_all_governorates_concurrent(governorates, days_ahead))

    gov_map = {g.name: g for g in governorates}
    rows = []
    for name, data in raw.items():
        if "error" in data:
            raise RuntimeError(f"Weather fetch failed for {name}: {data['error']}")
        g = gov_map[name]
        hourly = data["hourly"]
        times = hourly.get("time", [])
        ghi   = hourly.get("shortwave_radiation",     [None] * len(times))
        dhi   = hourly.get("diffuse_radiation",       [None] * len(times))
        dni   = hourly.get("direct_normal_irradiance", [None] * len(times))
        temp  = hourly.get("temperature_2m",          [None] * len(times))
        cloud = hourly.get("cloud_cover",             [None] * len(times))
        wind  = hourly.get("wind_speed_10m",          [None] * len(times))

        # Detect StegDistrict vs Governorate by checking for .direction attribute
        direction = getattr(g, "direction", None) or getattr(g, "district", "Unknown")

        for t, gh, dh, dn, tp, cl, ws in zip(times, ghi, dhi, dni, temp, cloud, wind):
            rows.append({
                TIMESTAMP:       pd.Timestamp(t),
                GHI_WM2:         float(gh) if gh is not None else MISSING_GHI_WM2,
                DHI_WM2:         float(dh) if dh is not None else MISSING_GHI_WM2,
                DNI_WM2:         float(dn) if dn is not None else MISSING_GHI_WM2,
                WIND_SPEED_MS:   float(ws) if ws is not None else MISSING_WIND_SPEED_MS,
                TEMP_C:          float(tp) if tp is not None else MISSING_TEMP_C,
                CLOUD_COVER_PCT: float(cl) if cl is not None else MISSING_CLOUD_COVER_PCT,
                # 'governorate' keeps the site name for model feature lookup
                GOVERNORATE:     name,
                # 'district' = Direction (7 groups) or regional group
                DISTRICT:        direction,
                # New columns for the STEG-district pipeline
                STEG_DISTRICT:   name,
                DIRECTION:       direction,
            })

    return pd.DataFrame(rows)


# ── Legacy sync fetch (kept for compatibility with any scripts that import it) ──

def fetch_forecast(lat: float, lon: float, days_ahead: int = 3) -> dict:
    """Synchronous single-location fetch (for scripts / tests)."""
    import requests

    resp = requests.get(
        OPEN_METEO_URL,
        params=_forecast_params(lat, lon, days_ahead),
        timeout=WEATHER_SINGLE_FETCH_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # Quick manual test (requires internet access)

    from data.steg_districts import STEG_DISTRICTS

    frame = build_live_weather_dataframe(STEG_DISTRICTS[:5], days_ahead=1)
    print(frame.head())
    print(frame.dtypes)
    print(f"\nDistricts fetched: {frame[STEG_DISTRICT].unique()[:5]}")
