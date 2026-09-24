"""Upstream endpoints, network budgets and the shared weather-dataframe schema.

Everything that a human might need to bump when an upstream API version changes
lives here, so no client module hardcodes a URL or a timeout.
"""

from __future__ import annotations

# ── Upstream services ────────────────────────────────────────────────────────
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
PVGIS_API_ROOT = "https://re.jrc.ec.europa.eu/api/v5_2"
PVGIS_HOURLY_URL = f"{PVGIS_API_ROOT}/seriescalc"

# ── Network budgets ──────────────────────────────────────────────────────────
# A forecast refresh runs on a 15-minute scheduler; a slow upstream must fail
# into the synthetic fallback long before the next tick rather than block it.
WEATHER_TIMEOUT_SECONDS = 30.0
WEATHER_SINGLE_FETCH_TIMEOUT_SECONDS = 20.0
PVGIS_TIMEOUT_SECONDS = 120
PVGIS_HISTORICAL_TIMEOUT_SECONDS = 60

# PVGIS rejects overlapping requests; keep a polite gap between calls.
PVGIS_MIN_REQUEST_INTERVAL_SECONDS = 1.0

# Open-Meteo publishes at most 16 days ahead.
MAX_FORECAST_DAYS = 16

# ── Shared dataframe contract ────────────────────────────────────────────────
# ``ingestion.weather_client`` (live), ``ingestion.synthetic_data`` (offline) and
# ``data.generate_*`` (training sets) all emit these column names so downstream
# feature engineering never branches on the data source.
TIMESTAMP = "timestamp"
TIMESTAMP_UTC = "timestamp_utc"
GHI_WM2 = "ghi_wm2"
DHI_WM2 = "dhi_wm2"
DNI_WM2 = "dni_wm2"
TEMP_C = "temp_c"
CLOUD_COVER_PCT = "cloud_cover_pct"
WIND_SPEED_MS = "wind_speed_ms"
GOVERNORATE = "governorate"
DIRECTION = "direction"
DISTRICT = "district"
STEG_DISTRICT = "steg_district"
PRODUCTION_MW = "production_mw"

WEATHER_COLUMNS: tuple[str, ...] = (
    GHI_WM2, DHI_WM2, DNI_WM2, TEMP_C, CLOUD_COVER_PCT, WIND_SPEED_MS,
)

# Physically plausible bounds used by the ingestion validators and the
# training-data quality gate (W/m², °C, %, m/s).
GHI_MAX_WM2 = 1400.0
TEMP_MIN_C = -20.0
TEMP_MAX_C = 60.0
WIND_MAX_MS = 40.0

# Defaults applied to a missing live reading so one gap does not zero a district.
MISSING_GHI_WM2 = 0.0
MISSING_TEMP_C = 20.0
MISSING_CLOUD_COVER_PCT = 30.0
MISSING_WIND_SPEED_MS = 3.0

# Local timezone of the whole deployment (Tunisia, no DST).
LOCAL_TIMEZONE = "Africa/Tunis"

__all__ = [
    "CLOUD_COVER_PCT",
    "DIRECTION",
    "DISTRICT",
    "GHI_MAX_WM2",
    "GHI_WM2",
    "DHI_WM2",
    "DNI_WM2",
    "GOVERNORATE",
    "LOCAL_TIMEZONE",
    "MAX_FORECAST_DAYS",
    "MISSING_CLOUD_COVER_PCT",
    "MISSING_GHI_WM2",
    "MISSING_TEMP_C",
    "MISSING_WIND_SPEED_MS",
    "OPEN_METEO_URL",
    "PRODUCTION_MW",
    "PVGIS_API_ROOT",
    "PVGIS_HISTORICAL_TIMEOUT_SECONDS",
    "PVGIS_HOURLY_URL",
    "PVGIS_MIN_REQUEST_INTERVAL_SECONDS",
    "PVGIS_TIMEOUT_SECONDS",
    "STEG_DISTRICT",
    "TEMP_C",
    "TEMP_MAX_C",
    "TEMP_MIN_C",
    "TIMESTAMP",
    "TIMESTAMP_UTC",
    "WEATHER_COLUMNS",
    "WEATHER_SINGLE_FETCH_TIMEOUT_SECONDS",
    "WEATHER_TIMEOUT_SECONDS",
    "WIND_MAX_MS",
    "WIND_SPEED_MS",
]
