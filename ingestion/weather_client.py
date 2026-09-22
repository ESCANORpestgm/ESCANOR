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

import asyncio
from datetime import date, timedelta

import httpx
import pandas as pd

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
PVGIS_HOURLY_URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"

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


async def _fetch_one_async(client: httpx.AsyncClient, lat: float, lon: float,
                           days_ahead: int) -> dict:
    """Single async GET to Open-Meteo for one location."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "forecast_days": min(days_ahead + 1, 16),
        "timezone": "Africa/Tunis",
    }
    resp = await client.get(OPEN_METEO_URL, params=params)
    resp.raise_for_status()
    return resp.json()


async def fetch_all_governorates_concurrent(governorates, days_ahead: int = 3) -> dict:
    """
    Fetch Open-Meteo forecasts for ALL districts/governorates concurrently.
    Accepts Governorate objects or StegDistrict objects (duck-typed: needs .name, .lat, .lon).
    Returns {name: forecast_json | {"error": str}}.
    Total wall-clock time ≈ single-request latency (≈1-2 s) regardless of N.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
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
                "timestamp":       pd.Timestamp(t),
                "ghi_wm2":         float(gh) if gh is not None else 0.0,
                "dhi_wm2":         float(dh) if dh is not None else 0.0,
                "dni_wm2":         float(dn) if dn is not None else 0.0,
                "wind_speed_ms":   float(ws) if ws is not None else 3.0,
                "temp_c":          float(tp) if tp is not None else 20.0,
                "cloud_cover_pct": float(cl) if cl is not None else 30.0,
                # 'governorate' keeps the site name for model feature lookup
                "governorate":     name,
                # 'district' = Direction (7 groups) or regional group
                "district":        direction,
                # New columns for the STEG-district pipeline
                "steg_district":   name,
                "direction":       direction,
            })

    return pd.DataFrame(rows)


# ── Legacy sync fetch (kept for compatibility with any scripts that import it) ──

def fetch_forecast(lat: float, lon: float, days_ahead: int = 3) -> dict:
    """Synchronous single-location fetch (for scripts / tests)."""
    import requests
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "forecast_days": min(days_ahead + 1, 16),
        "timezone": "Africa/Tunis",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_pvgis_historical(lat: float, lon: float, start_year: int, end_year: int,
                            peak_power_kwc: float = 1.0, system_loss_pct: float = 14.0) -> dict:
    """
    Hourly PV production simulation from PVGIS for a 1 kWc reference system.
    Useful as ground truth for training/validation before real STEG metering
    data is available.
    """
    import requests
    params = {
        "lat": lat, "lon": lon,
        "startyear": start_year, "endyear": end_year,
        "pvcalculation": 1,
        "peakpower": peak_power_kwc,
        "loss": system_loss_pct,
        "outputformat": "json",
        "mountingplace": "building",
    }
    resp = requests.get(PVGIS_HOURLY_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # Quick manual test (requires internet access)
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.steg_districts import STEG_DISTRICTS
    df = build_live_weather_dataframe(STEG_DISTRICTS[:5], days_ahead=1)
    print(df.head())
    print(df.dtypes)
    print(f"\nDistricts fetched: {df['steg_district'].unique()[:5]}")
