"""Forecast and forecast-export endpoints."""

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.responses import StreamingResponse

from api.core import (
    CAPACITY_LOOKUP,
    DISTRICT_CAPACITY_LOOKUP,
    METER_BUFFER,
    compute_bias_correction,
    get_forecast_frame,
    require_api_key,
    _state,
)
from data.steg_districts import DISTRICT_BY_NAME, DIRECTIONS
from models.aggregation import aggregate

router = APIRouter(prefix="/forecast", tags=["Forecast"])
grid_router = APIRouter(tags=["Grid Integration"])


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


@router.get("/map")
def forecast_map(horizon_hours: int = 0):
    forecast = get_forecast_frame(max(1, horizon_hours // 24 + 1))
    target = pd.Timestamp.now().floor("h") + pd.Timedelta(hours=horizon_hours)
    snapshot = forecast[forecast.timestamp == target]
    if snapshot.empty:
        snapshot = forecast[forecast.timestamp == forecast.timestamp.min()]
    output = []
    for _, row in snapshot.iterrows():
        name = row.get("steg_district") or row.get("governorate")
        district = DISTRICT_BY_NAME.get(name)
        capacity = district.installed_capacity_mwc if district else 10.0
        direction = district.direction if district else "Tunis"
        output.append({
            "governorate": name, "steg_district": name, "district": direction, "direction": direction,
            "installed_capacity_mwc": capacity,
            "forecast_p50_mw": round(row["forecast_p50_mw"], 2),
            "forecast_p10_mw": round(row["forecast_p10_mw"], 2),
            "forecast_p90_mw": round(row["forecast_p90_mw"], 2),
            "uncertainty_mw": round(row["forecast_p90_mw"] - row["forecast_p10_mw"], 2),
            "uncertainty_ratio": round((row["forecast_p90_mw"] - row["forecast_p10_mw"]) / row["forecast_p50_mw"], 3) if row["forecast_p50_mw"] > 0 else 0,
            "utilization_pct": round(100 * row["forecast_p50_mw"] / capacity, 1) if capacity else 0,
            "temp_c": round(float(row.get("temp_c", 20.0)), 1),
            "cloud_cover_pct": round(float(row.get("cloud_cover_pct", 30.0)), 0),
            "ghi_wm2": round(float(row.get("ghi_wm2", 0.0)), 0),
            "wind_speed_ms": round(float(row.get("wind_speed_ms", 3.0)), 1),
        })
    return {"timestamp": str(target), "data_source": _state["data_source"], "governorates": output, "districts": output}


@router.get("/timelapse")
def forecast_timelapse(hours: int = 48):
    hours = max(1, min(hours, 78))
    forecast = get_forecast_frame(max(1, hours // 24 + 1))
    frames = []
    for timestamp in sorted(forecast.timestamp.unique())[:hours]:
        snapshot = forecast[forecast.timestamp == timestamp]
        districts = []
        total = 0.0
        for _, row in snapshot.iterrows():
            name = row.get("steg_district") or row.get("governorate")
            district = DISTRICT_BY_NAME.get(name)
            capacity = district.installed_capacity_mwc if district else 10.0
            direction = district.direction if district else "Tunis"
            p50, p10, p90 = round(row["forecast_p50_mw"], 2), round(row["forecast_p10_mw"], 2), round(row["forecast_p90_mw"], 2)
            total += p50
            districts.append({"governorate": name, "direction": direction, "p50": p50, "p10": p10, "p90": p90, "uncertainty_ratio": round((p90 - p10) / p50, 3) if p50 > 0 else 0, "utilization_pct": round(100 * p50 / capacity, 1) if capacity else 0, "cloud_cover_pct": round(float(row.get("cloud_cover_pct", 0)), 0), "ghi_wm2": round(float(row.get("ghi_wm2", 0)), 0), "temp_c": round(float(row.get("temp_c", 20.0)), 1)})
        frames.append({"timestamp": str(timestamp), "governorates": districts, "national_total_mw": round(total, 1)})
    return frames


@router.post("/refresh", tags=["Grid Integration"])
def force_refresh(_key: str = Security(require_api_key)):
    _state["cache_time"] = None
    forecast = get_forecast_frame(3)
    return {"refreshed": True, "data_source": _state["data_source"], "rows": len(forecast), "cache_time": str(_state["cache_time"])}


@grid_router.get("/export/forecast")
def export_forecast(level: str = Query("national", enum=["national", "direction", "district", "steg_district"]), fmt: str = Query("csv", enum=["csv", "xml"]), horizon_days: int = 3):
    dataframe = aggregate(get_forecast_frame(horizon_days), level)
    dataframe["timestamp"] = dataframe["timestamp"].astype(str)
    if fmt == "csv":
        buffer = io.StringIO()
        dataframe.to_csv(buffer, index=False)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=presol_forecast_{level}.csv"})
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<forecast>"]
    for _, row in dataframe.iterrows():
        lines.append(f"  <row>{''.join(f'<{key}>{value}</{key}>' for key, value in row.items())}</row>")
    lines.append("</forecast>")
    return StreamingResponse(io.StringIO("\n".join(lines)), media_type="application/xml", headers={"Content-Disposition": f"attachment; filename=presol_forecast_{level}.xml"})
