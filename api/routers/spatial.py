"""Spatial forecast endpoints — map snapshots, timelapse animations, and data export."""

import io

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.services import _state, get_forecast_frame
from data.steg_districts import DISTRICT_BY_NAME
from models.aggregation import aggregate

router = APIRouter(prefix="/forecast", tags=["Spatial"])
grid_router = APIRouter(tags=["Grid Integration"])


# ── Map snapshot ─────────────────────────────────────────────────────────────


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


# ── Timelapse ────────────────────────────────────────────────────────────────


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


# ── Export ────────────────────────────────────────────────────────────────────


@grid_router.get("/export/forecast")
def export_forecast(
    level: str = Query("national", enum=["national", "direction", "district", "steg_district"]),
    fmt: str = Query("csv", enum=["csv", "xml"]),
    horizon_days: int = 3,
):
    dataframe = aggregate(get_forecast_frame(horizon_days), level)
    dataframe["timestamp"] = dataframe["timestamp"].astype(str)
    if fmt == "csv":
        buffer = io.StringIO()
        dataframe.to_csv(buffer, index=False)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=escanor_forecast_{level}.csv"})
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<forecast>"]
    for _, row in dataframe.iterrows():
        lines.append(f"  <row>{''.join(f'<{key}>{value}</{key}>' for key, value in row.items())}</row>")
    lines.append("</forecast>")
    return StreamingResponse(io.StringIO("\n".join(lines)), media_type="application/xml", headers={"Content-Disposition": f"attachment; filename=escanor_forecast_{level}.xml"})
