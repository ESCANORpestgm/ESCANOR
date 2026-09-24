"""Forecast query endpoints — national, direction, district, and governorate."""

import pandas as pd
from fastapi import APIRouter, HTTPException, Security

from api.config import DISTRICT_CAPACITY_LOOKUP, require_api_key
from api.services import compute_bias_correction, get_forecast_frame, _state
from data.steg_districts import DISTRICT_BY_NAME, DIRECTIONS
from models.aggregation import aggregate

router = APIRouter(prefix="/forecast", tags=["Forecast"])


# ── National ─────────────────────────────────────────────────────────────────


@router.get("/national")
def forecast_national(horizon_days: int = 3, split: bool = False):
    national = aggregate(get_forecast_frame(horizon_days), "national")
    national["timestamp"] = national["timestamp"].astype(str)
    if split:
        national["forecast_injected_mw"] = (national["forecast_p50_mw"] * 0.6407).round(2)
        national["forecast_selfconsumed_mw"] = (national["forecast_p50_mw"] * 0.3593).round(2)
    return national.to_dict(orient="records")


@router.get("/intraday")
def forecast_intraday():
    national = aggregate(get_forecast_frame(1), "national").sort_values("timestamp")
    national["timestamp"] = pd.to_datetime(national["timestamp"])
    now = pd.Timestamp.now().floor("15min")
    end = now + pd.Timedelta(hours=6)
    window = national[(national["timestamp"] >= now.floor("h")) & (national["timestamp"] <= end.ceil("h"))].copy()
    if window.empty:
        raise HTTPException(503, "No forecast data available for the next 6 h.")
    window = window.set_index("timestamp")
    new_index = pd.date_range(now, end, freq="15min")
    window = window.reindex(window.index.union(new_index)).interpolate("cubic").reindex(new_index).clip(lower=0)
    window.index.name = "timestamp"
    window = window.reset_index()
    scale = compute_bias_correction()
    if scale is not None:
        for column in ["forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw"]:
            window[column] = (window[column] * scale).clip(lower=0)
    window["timestamp"] = window["timestamp"].astype(str)
    return {"resolution": "15min", "bias_corrected": scale is not None, "bias_scale_factor": round(scale, 4) if scale else None, "data": window.to_dict(orient="records")}


# ── Direction ────────────────────────────────────────────────────────────────


@router.get("/directions")
def forecast_all_directions(horizon_days: int = 3):
    result = aggregate(get_forecast_frame(horizon_days), "direction")
    result["timestamp"] = result["timestamp"].astype(str)
    return result.to_dict(orient="records")


@router.get("/direction/{direction}")
def forecast_direction(direction: str, horizon_days: int = 3):
    result = aggregate(get_forecast_frame(horizon_days), "direction")
    result = result[result["direction"].str.upper() == direction.upper()].copy()
    if result.empty:
        raise HTTPException(404, f"Unknown Direction '{direction}'. Options: {DIRECTIONS}")
    result["timestamp"] = result["timestamp"].astype(str)
    return result.to_dict(orient="records")


# ── District / STEG district ────────────────────────────────────────────────


@router.get("/steg-district/{name}")
def forecast_steg_district(name: str, horizon_days: int = 3):
    forecast = get_forecast_frame(horizon_days)
    column = "steg_district" if "steg_district" in forecast.columns else "governorate"
    result = forecast[forecast[column].str.upper() == name.upper()].copy()
    if result.empty:
        result = forecast[forecast["governorate"].str.upper() == name.upper()].copy()
    if result.empty:
        raise HTTPException(404, f"Unknown district '{name}'.")
    result["timestamp"] = result["timestamp"].astype(str)
    capacity = DISTRICT_CAPACITY_LOOKUP.get(name.upper(), 10.0)
    result["uncertainty_mw"] = (result["forecast_p90_mw"] - result["forecast_p10_mw"]).round(2)
    result["uncertainty_ratio"] = result.apply(lambda row: round((row["forecast_p90_mw"] - row["forecast_p10_mw"]) / row["forecast_p50_mw"], 3) if row["forecast_p50_mw"] > 0 else 0.0, axis=1)
    result["utilization_pct"] = (100 * result["forecast_p50_mw"] / capacity).round(1) if capacity else 0.0
    columns = ["timestamp", "forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw", "uncertainty_mw", "uncertainty_ratio", "utilization_pct"]
    columns += [column for column in ["ghi_wm2", "temp_c", "cloud_cover_pct", "wind_speed_ms"] if column in result.columns]
    return result[columns].to_dict(orient="records")


@router.get("/district/{district}")
def forecast_district(district: str, horizon_days: int = 3):
    district_upper = district.upper()
    if district_upper in [item.upper() for item in DIRECTIONS]:
        return forecast_direction(district, horizon_days)
    if district_upper in DISTRICT_BY_NAME:
        return forecast_steg_district(district, horizon_days)
    result = aggregate(get_forecast_frame(horizon_days), "district")
    column = "district" if "district" in result.columns else "direction"
    result = result[result[column].str.upper() == district_upper].copy()
    if result.empty:
        raise HTTPException(404, f"Unknown district '{district}'.")
    result["timestamp"] = result["timestamp"].astype(str)
    return result.to_dict(orient="records")


@router.get("/districts")
def forecast_all_districts(horizon_days: int = 3):
    result = aggregate(get_forecast_frame(horizon_days), "direction")
    result["timestamp"] = result["timestamp"].astype(str)
    if "direction" in result.columns:
        result["district"] = result["direction"]
    return result.to_dict(orient="records")


@router.get("/governorate/{governorate}")
def forecast_governorate(governorate: str, horizon_days: int = 3):
    if governorate.upper() in DISTRICT_BY_NAME:
        return forecast_steg_district(governorate, horizon_days)
    forecast = get_forecast_frame(horizon_days)
    column = "steg_district" if "steg_district" in forecast.columns else "governorate"
    result = forecast[forecast[column].str.upper() == governorate.upper()].copy()
    if result.empty:
        raise HTTPException(404, f"Unknown location '{governorate}'.")
    result["timestamp"] = result["timestamp"].astype(str)
    return result[["timestamp", "forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw"]].to_dict(orient="records")


# ── Cache control ────────────────────────────────────────────────────────────


@router.post("/refresh", tags=["Grid Integration"])
def force_refresh(_key: str = Security(require_api_key)):
    _state["cache_time"] = None
    forecast = get_forecast_frame(3)
    return {"refreshed": True, "data_source": _state["data_source"], "rows": len(forecast), "cache_time": str(_state["cache_time"])}
