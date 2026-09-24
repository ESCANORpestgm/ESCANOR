"""PVGIS district-level production ingestion.

PVGIS is queried once per STEG commercial district using its representative
coordinate and aggregate installed capacity. It is deliberately not queried
for individual rooftops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pandas as pd
import requests

from data.climate import SYSTEM_LOSS_PCT
from ingestion.settings import (
    CLOUD_COVER_PCT,
    DHI_WM2,
    DNI_WM2,
    GHI_WM2,
    PVGIS_HISTORICAL_TIMEOUT_SECONDS,
    PVGIS_HOURLY_URL,
    PVGIS_TIMEOUT_SECONDS,
    TEMP_C,
    TIMESTAMP_UTC,
    WIND_SPEED_MS,
)

# Columns of the district-level frame produced below.
POWER_KW = "power_kw"
PV_COMPONENT_COLUMNS = (POWER_KW, GHI_WM2, DNI_WM2, DHI_WM2, TEMP_C, WIND_SPEED_MS)


def fetch_historical_pv_profile(
    latitude: float,
    longitude: float,
    start_year: int,
    end_year: int,
    *,
    peak_power_kwc: float = 1.0,
    system_loss_pct: float = SYSTEM_LOSS_PCT,
) -> dict:
    """Raw hourly PV simulation payload for a reference system at a site.

    Useful as ground truth for training/validation before real STEG metering
    data is available. Callers normally want :func:`fetch_district_hourly`,
    which parses this payload into a DataFrame.
    """
    params = {
        "lat": latitude,
        "lon": longitude,
        "startyear": start_year,
        "endyear": end_year,
        "pvcalculation": 1,
        "peakpower": peak_power_kwc,
        "loss": system_loss_pct,
        "outputformat": "json",
        "mountingplace": "building",
    }
    response = requests.get(PVGIS_HOURLY_URL, params=params, timeout=PVGIS_HISTORICAL_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _numeric_column(hourly: pd.DataFrame, name: str) -> pd.Series:
    values = hourly[name] if name in hourly.columns else pd.Series(0.0, index=hourly.index)
    numeric = pd.to_numeric(pd.Series(values, index=hourly.index), errors="coerce").fillna(0.0)
    return cast(pd.Series, numeric)


def fetch_district_hourly(
    *,
    latitude: float,
    longitude: float,
    start_year: int,
    end_year: int,
    tilt: float,
    azimuth: float,
    peak_power_kwp: float,
    cache_path: Path,
    timeout_seconds: int = PVGIS_TIMEOUT_SECONDS,
) -> pd.DataFrame:
    """Fetch or load hourly PVGIS production for one aggregate district fleet."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.is_file():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        params = {
            "lat": latitude,
            "lon": longitude,
            "startyear": start_year,
            "endyear": end_year,
            "outputformat": "json",
            "angle": tilt,
            # PVGIS uses 0°=south, -90°=east, +90°=west; project metadata
            # uses compass bearings where 180° means south.
            "aspect": azimuth - 180.0,
            "pvcalculation": 1,
            "components": 1,
            "peakpower": peak_power_kwp,
            "loss": SYSTEM_LOSS_PCT,
            "localtime": 0,
        }
        response = requests.get(PVGIS_HOURLY_URL, params=params, timeout=timeout_seconds)
        if not response.ok:
            raise requests.HTTPError(
                f"PVGIS request failed ({response.status_code}): {response.text[:500]}",
                response=response,
            )
        payload = response.json()
        cache_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        hourly = pd.DataFrame(payload["outputs"]["hourly"])
    except (KeyError, TypeError) as exc:
        raise ValueError("PVGIS response did not contain outputs.hourly") from exc
    if hourly.empty or "time" not in hourly or "P" not in hourly:
        raise ValueError("PVGIS response did not contain hourly time and P values")

    timestamp = pd.to_datetime(hourly["time"], format="%Y%m%d:%H%M", utc=True).dt.floor("h")
    beam = _numeric_column(hourly, "Gb(i)")
    diffuse = _numeric_column(hourly, "Gd(i)")
    reflected = _numeric_column(hourly, "Gr(i)")
    frame = pd.DataFrame(
        {
            TIMESTAMP_UTC: timestamp,
            POWER_KW: pd.to_numeric(hourly["P"], errors="coerce"),
            GHI_WM2: beam + diffuse + reflected,
            DNI_WM2: beam,
            DHI_WM2: diffuse,
            TEMP_C: _numeric_column(hourly, "T2m"),
            WIND_SPEED_MS: _numeric_column(hourly, "WS10m"),
        }
    )
    frame[CLOUD_COVER_PCT] = 0.0
    for column in PV_COMPONENT_COLUMNS:
        frame[column] = frame[column].fillna(0.0)
    frame[POWER_KW] = frame[POWER_KW].clip(lower=0.0, upper=peak_power_kwp)
    return frame.sort_values(TIMESTAMP_UTC).drop_duplicates(TIMESTAMP_UTC).reset_index(drop=True)

