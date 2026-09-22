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

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"
DEFAULT_LOSS_PCT = 14.0


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
    timeout_seconds: int = 120,
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
            "loss": DEFAULT_LOSS_PCT,
            "localtime": 0,
        }
        response = requests.get(PVGIS_URL, params=params, timeout=timeout_seconds)
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
            "timestamp_utc": timestamp,
            "power_kw": pd.to_numeric(hourly["P"], errors="coerce"),
            "ghi_wm2": beam + diffuse + reflected,
            "dni_wm2": beam,
            "dhi_wm2": diffuse,
            "temp_c": _numeric_column(hourly, "T2m"),
            "wind_speed_ms": _numeric_column(hourly, "WS10m"),
        }
    )
    frame["cloud_cover_pct"] = 0.0
    for column in ["power_kw", "ghi_wm2", "dni_wm2", "dhi_wm2", "temp_c", "wind_speed_ms"]:
        frame[column] = frame[column].fillna(0.0)
    frame["power_kw"] = frame["power_kw"].clip(lower=0.0, upper=peak_power_kwp)
    return frame.sort_values("timestamp_utc").drop_duplicates("timestamp_utc").reset_index(drop=True)
