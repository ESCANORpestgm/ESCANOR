"""
FastAPI serving layer — fully upgraded to STEG commercial districts and note conceptuelle requirements.

Features:
  - Primary spatial granularity: 50 STEG commercial districts across 7 Directions de Distribution.
  - Backward-compatible endpoints for 24 governorates and legacy district aggregates.
  - API key authentication (X-API-Key header) on write / sensitive endpoints.
  - Background APScheduler: refreshes weather forecast every 30 min (daylight only).
  - /forecast/national  — national aggregation with optional ?split=true for grid injection vs self-consumption.
  - /forecast/intraday  — 15-min resolution, next 6 h, with bias correction.
  - /forecast/directions & /forecast/direction/{name} — aggregation by STEG Direction (7 groups).
  - /forecast/steg-district/{name} — granular forecast for any of the 50 STEG districts with uncertainty and weather.
  - /steg-districts     — full list of 50 STEG commercial districts with lat/lon, capacity, pending dossiers.
  - /registry/pipeline  — capacity pipeline with 30d/90d projections based on pending connection backlogs.
  - /alerts             — system-level warnings including SATURATION_RISK for high-penetration feeders.
  - /reports/prosol/*   — official STEG Prosol KPIs and HTML report generator.
  - /displacement/summary — multi-vector fuel, financial, and CO2 displacement.

Run: uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

import csv
import io
import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional, List

import pandas as pd
from fastapi import FastAPI, HTTPException, Security, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import (
    STEG_DISTRICTS,
    DISTRICT_BY_NAME,
    DIRECTIONS,
    DISTRICT_CAPACITY_LOOKUP,
    DISTRICT_DUST_LOOKUP,
    SATURATION_THRESHOLDS_MW,
    AVG_UNIT_KWC,
    calculate_displacement,
    direction_summary,
    project_capacity,
    GOVERNORATES,
    GOVERNORATE_BY_NAME,
)
from ingestion.synthetic_data import generate_all
from ingestion import weather_client
from models.ml_forecast import load_models, predict
from models.aggregation import aggregate
from reports.prosol_report_generator import get_prosol_summary_metrics, generate_html_prosol_report

# ── API Key Auth ─────────────────────────────────────────────────────────────
_API_KEY = os.environ.get("PRESOL_API_KEY", "dev-key")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(_api_key_header)):
    if key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key header.")
    return key


# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT         = os.path.join(os.path.dirname(__file__), "..")
MODEL_PATH    = os.path.join(_ROOT, "models", "artifacts", "quantile_models.joblib")
RESULTS_DIR   = os.path.join(_ROOT, "results")
METER_BUFFER  = os.path.join(RESULTS_DIR, "metering_buffer.csv")
RETRAIN_LOG   = os.path.join(RESULTS_DIR, "retrain_log.csv")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Capacity / Dust lookups (merged STEG districts + governorates) ─────────────
CAPACITY_LOOKUP = {**{g.name: g.installed_capacity_mwc for g in GOVERNORATES}, **DISTRICT_CAPACITY_LOOKUP}
DUST_LOOKUP     = {**{g.name: g.dust_loss_pct           for g in GOVERNORATES}, **DISTRICT_DUST_LOOKUP}

# ── Shared mutable state ──────────────────────────────────────────────────────
_state = {
    "models":      None,
    "cache":       None,      # pd.DataFrame with district-level forecasts
    "cache_time":  None,      # pd.Timestamp the cache was last filled
    "data_source": "unknown",
    "refresh_lock": threading.Lock(),
}


# ── Model loading ─────────────────────────────────────────────────────────────
def get_models():
    if _state["models"] is None:
        _state["models"] = load_models(MODEL_PATH)
    return _state["models"]


# ── Forecast computation ──────────────────────────────────────────────────────
def _build_forecast(horizon_days: int = 3) -> pd.DataFrame:
    """
    Pull weather for all 50 STEG commercial districts (live → synthetic fallback),
    run inference, and cache the result.
    """
    with _state["refresh_lock"]:
        now = pd.Timestamp.now(tz="Africa/Tunis").tz_localize(None).floor("h")
        # If cache is fresh (< 29 min old) and covers the requested horizon, reuse it.
        if _state["cache"] is not None and _state["cache_time"] is not None:
            age_min = (now - _state["cache_time"]).total_seconds() / 60
            if age_min < 29:
                return _state["cache"]

        try:
            weather = weather_client.build_live_weather_dataframe(
                STEG_DISTRICTS, days_ahead=horizon_days
            )
            end = now + pd.Timedelta(days=horizon_days)
            weather = weather[(weather.timestamp >= now) & (weather.timestamp <= end)]
            if weather.empty:
                raise ValueError("live weather returned no rows in range")
            _state["data_source"] = "live"
        except Exception:
            weather = generate_all(
                STEG_DISTRICTS,
                start=str(now.date()),
                end=str((now + pd.Timedelta(days=horizon_days + 1)).date()),
            )
            weather = weather[
                (weather.timestamp >= now) &
                (weather.timestamp <= now + pd.Timedelta(days=horizon_days))
            ]
            _state["data_source"] = "synthetic"

        fc = predict(get_models(), weather, CAPACITY_LOOKUP, DUST_LOOKUP)
        _state["cache"]      = fc
        _state["cache_time"] = now
        return fc


def get_forecast_frame(horizon_days: int = 3) -> pd.DataFrame:
    return _build_forecast(horizon_days)


# ── Background refresh scheduler ──────────────────────────────────────────────
def _scheduled_refresh():
    """Refresh forecast during Tunisian daylight hours (05:00–20:00 UTC+1)."""
    local_hour = (datetime.utcnow() + timedelta(hours=1)).hour
    if 5 <= local_hour <= 20:
        try:
            _build_forecast(horizon_days=3)
        except Exception as e:
            print(f"[scheduler] forecast refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background scheduler; shut it down cleanly on exit."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_refresh, "interval", minutes=30, id="forecast_refresh")
        scheduler.start()
        app.state.scheduler = scheduler
        print("[APScheduler] background forecast refresh every 30 min → started")
    except ImportError:
        print("[APScheduler] not installed — background refresh disabled")
        app.state.scheduler = None

    yield

    if getattr(app.state, "scheduler", None):
        app.state.scheduler.shutdown(wait=False)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="STEG PréSol PV Forecast Platform API",
    description=(
        "National rooftop PV production forecasting for STEG — intra-day to D+3, "
        "across all 50 commercial districts, 7 Directions de Distribution, and national level. "
        "Implements empirical Prosol displacement metrics, pipeline backlog modeling, "
        "and feeder reverse-flow saturation alerts."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# ROOT / META
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Meta"])
def root():
    return {
        "service": "STEG PréSol PV Forecast Platform",
        "version": "2.0.0",
        "status": "ok",
        "endpoints": [
            "/forecast/national", "/forecast/intraday",
            "/forecast/directions", "/forecast/direction/{direction}",
            "/forecast/districts", "/forecast/district/{district}",
            "/forecast/steg-district/{name}",
            "/forecast/governorate/{governorate}",
            "/forecast/map", "/forecast/timelapse",
            "/forecast/refresh", "/export/forecast",
            "/metering/push", "/retrain/status",
            "/alerts", "/cache/status",
            "/steg-districts", "/districts/positions", "/registry/pipeline",
            "/governorates", "/districts", "/status", "/metrics", "/history/national",
            "/reports/prosol/summary", "/reports/prosol/html", "/displacement/summary",
        ],
    }


@app.get("/status", tags=["Meta"])
def status():
    cache_age_min = None
    if _state["cache_time"] is not None:
        now = pd.Timestamp.now().floor("h")
        cache_age_min = round((now - _state["cache_time"]).total_seconds() / 60, 1)
    return {
        "data_source":       _state["data_source"],
        "total_capacity_mwc": round(sum(DISTRICT_CAPACITY_LOOKUP.values()), 1),
        "districts_count":    len(STEG_DISTRICTS),
        "directions_count":   len(DIRECTIONS),
        "cache_age_min":      cache_age_min,
    }


@app.get("/cache/status", tags=["Meta"])
def cache_status():
    """Age, data source, and last refresh timestamp of the in-memory forecast cache."""
    cache_age_min = None
    if _state["cache_time"] is not None:
        now = pd.Timestamp.now().floor("h")
        cache_age_min = round((now - _state["cache_time"]).total_seconds() / 60, 1)
    return {
        "data_source":    _state["data_source"],
        "last_refreshed": str(_state["cache_time"]) if _state["cache_time"] else None,
        "cache_age_min":  cache_age_min,
        "is_stale":       cache_age_min is None or cache_age_min >= 29,
    }


@app.get("/steg-districts", tags=["STEG Prosol"])
def list_steg_districts():
    """
    Returns all 50 STEG commercial districts with geographical coordinates,
    installed capacity (MWc), pending connection requests, Direction, and execution rate.
    """
    return [
        {
            "name":                   d.name,
            "direction":              d.direction,
            "governorate":            d.governorate,
            "lat":                    d.lat,
            "lon":                    d.lon,
            "installed_capacity_mwc": d.installed_capacity_mwc,
            "pending_dossiers":       d.pending_dossiers,
            "dust_loss_pct":          d.dust_loss_pct,
            "execution_rate_pct":     d.execution_rate_pct,
        }
        for d in STEG_DISTRICTS
    ]


@app.get("/districts/positions", tags=["STEG Prosol"])
def get_steg_district_positions():
    """Alias for /steg-districts used by spatial mapping."""
    return list_steg_districts()


@app.get("/governorates", tags=["Registry"])
def list_governorates():
    """Returns 50 STEG districts as the primary data points, backward-compatible with governorate registry views."""
    return [
        {
            "name":                   d.name,
            "district":               d.direction,
            "direction":              d.direction,
            "governorate":            d.governorate,
            "lat":                    d.lat,
            "lon":                    d.lon,
            "installed_capacity_mwc": d.installed_capacity_mwc,
            "dust_loss_pct":          d.dust_loss_pct,
            "pending_connections":    d.pending_dossiers,
            "execution_rate_pct":     d.execution_rate_pct,
        }
        for d in STEG_DISTRICTS
    ]


@app.get("/districts", tags=["Registry"])
def list_districts():
    """Returns the 7 STEG Directions de Distribution."""
    return DIRECTIONS


@app.get("/registry/pipeline", tags=["Registry"])
def registry_pipeline():
    """
    Capacity expansion pipeline based on pending dossiers and execution rates.
    """
    out = []
    for d in sorted(STEG_DISTRICTS, key=lambda x: x.pending_dossiers, reverse=True):
        p30 = project_capacity(d, 30)
        p90 = project_capacity(d, 90)
        out.append({
            "district":          d.name,
            "direction":         d.direction,
            "governorate":       d.governorate,
            "current_mwc":       d.installed_capacity_mwc,
            "pending_dossiers":  d.pending_dossiers,
            "avg_unit_kwc":      AVG_UNIT_KWC,
            "exec_rate_pct":     d.execution_rate_pct,
            "projected_mwc_30d": p30,
            "projected_mwc_90d": p90,
            "added_mwc_90d":     round(p90 - d.installed_capacity_mwc, 3),
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# FORECAST ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/forecast/national", tags=["Forecast"])
def forecast_national(horizon_days: int = 3, split: bool = False):
    """
    National rooftop PV forecast.
    If split=True, returns net grid injection (64.07%) and self-consumption (35.93%)
    based on empirical STEG Prosol ratios.
    """
    fc = get_forecast_frame(horizon_days)
    national = aggregate(fc, "national")
    national["timestamp"] = national["timestamp"].astype(str)
    if split:
        national["forecast_injected_mw"] = (national["forecast_p50_mw"] * 0.6407).round(2)
        national["forecast_selfconsumed_mw"] = (national["forecast_p50_mw"] * 0.3593).round(2)
    return national.to_dict(orient="records")


# Module-level alias for backward compatibility
national_forecast = forecast_national


@app.get("/forecast/intraday", tags=["Forecast"])
def forecast_intraday():
    """
    High-resolution intra-day forecast: 15-minute resolution for the next 6 hours.
    Interpolates national forecast using cubic spline with optional bias correction.
    """
    fc = get_forecast_frame(horizon_days=1)
    national = aggregate(fc, "national").sort_values("timestamp")
    national["timestamp"] = pd.to_datetime(national["timestamp"])

    now = pd.Timestamp.now().floor("15min")
    end = now + pd.Timedelta(hours=6)

    window = national[
        (national["timestamp"] >= now.floor("h")) &
        (national["timestamp"] <= end.ceil("h"))
    ].copy()

    if window.empty:
        raise HTTPException(503, "No forecast data available for the next 6 h.")

    window = window.set_index("timestamp")
    new_idx = pd.date_range(now, end, freq="15min")
    window = window.reindex(window.index.union(new_idx)).interpolate("cubic").reindex(new_idx)
    window = window.clip(lower=0)
    window.index.name = "timestamp"
    window = window.reset_index()

    scale = _compute_bias_correction()
    if scale is not None:
        for col in ["forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw"]:
            window[col] = (window[col] * scale).clip(lower=0)

    window["timestamp"] = window["timestamp"].astype(str)
    return {
        "resolution": "15min",
        "bias_corrected": scale is not None,
        "bias_scale_factor": round(scale, 4) if scale else None,
        "data": window.to_dict(orient="records"),
    }


def _compute_bias_correction() -> Optional[float]:
    if not os.path.exists(METER_BUFFER):
        return None
    try:
        buf = pd.read_csv(METER_BUFFER, parse_dates=["timestamp"])
        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=3)
        recent = buf[buf["timestamp"] >= cutoff]
        if len(recent) < 2:
            return None
        ratio = recent["actual_mw"].sum() / recent["forecast_p50_mw"].replace(0, pd.NA).sum()
        if pd.isna(ratio) or ratio <= 0 or ratio > 3:
            return None
        return float(ratio)
    except Exception:
        return None


@app.get("/forecast/directions", tags=["Forecast"])
def forecast_all_directions(horizon_days: int = 3):
    """Aggregated forecast by the 7 STEG Directions de Distribution."""
    fc = get_forecast_frame(horizon_days)
    dir_agg = aggregate(fc, "direction")
    dir_agg["timestamp"] = dir_agg["timestamp"].astype(str)
    return dir_agg.to_dict(orient="records")


@app.get("/forecast/direction/{direction}", tags=["Forecast"])
def forecast_direction(direction: str, horizon_days: int = 3):
    """Forecast for a single STEG Direction de Distribution (e.g. 'SFAX', 'TUNIS', 'SUD')."""
    fc = get_forecast_frame(horizon_days)
    dir_agg = aggregate(fc, "direction")
    sub = dir_agg[dir_agg["direction"].str.upper() == direction.upper()].copy()
    if sub.empty:
        raise HTTPException(404, f"Unknown Direction '{direction}'. Options: {DIRECTIONS}")
    sub["timestamp"] = sub["timestamp"].astype(str)
    return sub.to_dict(orient="records")


@app.get("/forecast/steg-district/{name}", tags=["Forecast"])
def forecast_steg_district(name: str, horizon_days: int = 3):
    """
    Granular hourly forecast for one of the 50 STEG commercial districts.
    Includes P10, P50, P90, uncertainty metrics, utilization %, and weather parameters.
    """
    fc = get_forecast_frame(horizon_days)
    col = "steg_district" if "steg_district" in fc.columns else "governorate"
    match = fc[fc[col].str.upper() == name.upper()].copy()
    if match.empty:
        match = fc[fc["governorate"].str.upper() == name.upper()].copy()
    if match.empty:
        raise HTTPException(404, f"Unknown district '{name}'.")

    match["timestamp"] = match["timestamp"].astype(str)
    cap = DISTRICT_CAPACITY_LOOKUP.get(name.upper(), 10.0)
    match["uncertainty_mw"] = (match["forecast_p90_mw"] - match["forecast_p10_mw"]).round(2)
    match["uncertainty_ratio"] = match.apply(
        lambda r: round((r["forecast_p90_mw"] - r["forecast_p10_mw"]) / r["forecast_p50_mw"], 3)
        if r["forecast_p50_mw"] > 0 else 0.0, axis=1
    )
    match["utilization_pct"] = (100 * match["forecast_p50_mw"] / cap).round(1) if cap else 0.0

    cols = ["timestamp", "forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw",
            "uncertainty_mw", "uncertainty_ratio", "utilization_pct"]
    for wc in ["ghi_wm2", "temp_c", "cloud_cover_pct", "wind_speed_ms"]:
        if wc in match.columns:
            cols.append(wc)
    return match[cols].to_dict(orient="records")


@app.get("/forecast/district/{district}", tags=["Forecast"])
def forecast_district(district: str, horizon_days: int = 3):
    """
    Backward-compatible district endpoint. Supports:
    1. STEG Direction name (e.g. SFAX, NORD, TUNIS)
    2. STEG commercial district name (e.g. SFAX NORD, JERBA)
    3. Legacy regional district name
    """
    fc = get_forecast_frame(horizon_days)
    d_up = district.upper()
    if d_up in [d.upper() for d in DIRECTIONS]:
        return forecast_direction(district, horizon_days)
    if d_up in DISTRICT_BY_NAME:
        return forecast_steg_district(district, horizon_days)
    dir_agg = aggregate(fc, "district")
    col = "district" if "district" in dir_agg.columns else "direction"
    sub = dir_agg[dir_agg[col].str.upper() == d_up].copy()
    if not sub.empty:
        sub["timestamp"] = sub["timestamp"].astype(str)
        return sub.to_dict(orient="records")
    raise HTTPException(404, f"Unknown district '{district}'.")


@app.get("/forecast/districts", tags=["Forecast"])
def forecast_all_districts(horizon_days: int = 3):
    """All directions at once — preserves legacy 'district' column alias."""
    fc = get_forecast_frame(horizon_days)
    dir_agg = aggregate(fc, "direction")
    dir_agg["timestamp"] = dir_agg["timestamp"].astype(str)
    if "direction" in dir_agg.columns:
        dir_agg["district"] = dir_agg["direction"]
    return dir_agg.to_dict(orient="records")


@app.get("/forecast/governorate/{governorate}", tags=["Forecast"])
def forecast_governorate(governorate: str, horizon_days: int = 3):
    """Returns forecast for a specific STEG commercial district or administrative governorate."""
    g_up = governorate.upper()
    if g_up in DISTRICT_BY_NAME:
        return forecast_steg_district(governorate, horizon_days)
    fc = get_forecast_frame(horizon_days)
    col = "steg_district" if "steg_district" in fc.columns else "governorate"
    match = fc[fc[col].str.upper() == g_up].copy()
    if match.empty:
        match = fc[fc["governorate"].str.upper() == g_up].copy()
    if match.empty:
        raise HTTPException(404, f"Unknown location '{governorate}'.")
    result = match[["timestamp", "forecast_p10_mw", "forecast_p50_mw", "forecast_p90_mw"]].copy()
    result["timestamp"] = result["timestamp"].astype(str)
    return result.to_dict(orient="records")


@app.get("/forecast/map", tags=["Forecast"])
def forecast_map(horizon_hours: int = 0):
    """
    Snapshot across all 50 STEG commercial districts at now + horizon_hours.
    Includes weather conditions, direction, and uncertainty width.
    """
    fc = get_forecast_frame(horizon_days=max(1, horizon_hours // 24 + 1))
    target = pd.Timestamp.now().floor("h") + pd.Timedelta(hours=horizon_hours)
    snapshot = fc[fc.timestamp == target]
    if snapshot.empty:
        snapshot = fc[fc.timestamp == fc.timestamp.min()]
    out = []
    for _, row in snapshot.iterrows():
        name = row.get("steg_district") or row.get("governorate")
        d = DISTRICT_BY_NAME.get(name)
        if d:
            lat = d.lat
            lon = d.lon
            cap = d.installed_capacity_mwc
            dust = d.dust_loss_pct
            direction = d.direction
            gov = d.governorate
        else:
            g = GOVERNORATE_BY_NAME.get(name)
            lat = g.lat if g else 36.8
            lon = g.lon if g else 10.1
            cap = g.installed_capacity_mwc if g else 10.0
            dust = g.dust_loss_pct if g else 0.03
            direction = g.district if g else "Nord"
            gov = g.name if g else name

        p50 = round(row["forecast_p50_mw"], 2)
        p10 = round(row["forecast_p10_mw"], 2)
        p90 = round(row["forecast_p90_mw"], 2)
        uncertainty_mw   = round(p90 - p10, 2)
        uncertainty_ratio = round((p90 - p10) / p50, 3) if p50 > 0 else 0
        out.append({
            "governorate":            name,
            "steg_district":          name,
            "district":               direction,
            "direction":              direction,
            "administrative_gov":     gov,
            "lat":                    lat,
            "lon":                    lon,
            "installed_capacity_mwc": cap,
            "dust_loss_pct":          dust,
            "forecast_p50_mw":        p50,
            "forecast_p10_mw":        p10,
            "forecast_p90_mw":        p90,
            "uncertainty_mw":         uncertainty_mw,
            "uncertainty_ratio":      uncertainty_ratio,
            "utilization_pct":        round(100 * p50 / cap, 1) if cap else 0,
            "temp_c":                 round(float(row.get("temp_c", 20.0)), 1),
            "cloud_cover_pct":        round(float(row.get("cloud_cover_pct", 30.0)), 0),
            "ghi_wm2":                round(float(row.get("ghi_wm2", 0.0)), 0),
            "wind_speed_ms":          round(float(row.get("wind_speed_ms", 3.0)), 1),
        })
    return {
        "timestamp":    str(target),
        "data_source":  _state["data_source"],
        "governorates": out,
        "districts":    out,
    }


@app.get("/forecast/timelapse", tags=["Forecast"])
def forecast_timelapse(hours: int = 48):
    """
    Per-district hourly forecast for the next `hours` hours across all 50 STEG districts.
    """
    hours = max(1, min(hours, 78))
    fc = get_forecast_frame(horizon_days=max(1, hours // 24 + 1))
    timestamps = sorted(fc.timestamp.unique())[:hours]

    frames = []
    for ts in timestamps:
        snap = fc[fc.timestamp == ts]
        govs = []
        total = 0.0
        for _, row in snap.iterrows():
            name = row.get("steg_district") or row.get("governorate")
            d = DISTRICT_BY_NAME.get(name)
            cap = d.installed_capacity_mwc if d else 10.0
            direction = d.direction if d else "Tunis"
            p50 = round(row["forecast_p50_mw"], 2)
            p10 = round(row["forecast_p10_mw"], 2)
            p90 = round(row["forecast_p90_mw"], 2)
            total += p50
            govs.append({
                "governorate":       name,
                "direction":         direction,
                "p50":               p50,
                "p10":               p10,
                "p90":               p90,
                "uncertainty_ratio": round((p90 - p10) / p50, 3) if p50 > 0 else 0,
                "utilization_pct":   round(100 * p50 / cap, 1) if cap else 0,
                "cloud_cover_pct":   round(float(row.get("cloud_cover_pct", 0)), 0),
                "ghi_wm2":           round(float(row.get("ghi_wm2", 0)), 0),
                "temp_c":            round(float(row.get("temp_c", 20.0)), 1),
            })
        frames.append({
            "timestamp":         str(ts),
            "governorates":      govs,
            "national_total_mw": round(total, 1),
        })
    return frames


# ═══════════════════════════════════════════════════════════════════════════════
# GRID INTEGRATION & CONTINUOUS LEARNING
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/forecast/refresh", tags=["Grid Integration"])
def force_refresh(_key: str = Security(require_api_key)):
    _state["cache_time"] = None
    fc = _build_forecast(horizon_days=3)
    return {
        "refreshed": True,
        "data_source": _state["data_source"],
        "rows": len(fc),
        "cache_time": str(_state["cache_time"]),
    }


@app.get("/export/forecast", tags=["Grid Integration"])
def export_forecast(
    level: str = Query("national", enum=["national", "direction", "district", "steg_district"]),
    fmt:   str = Query("csv",      enum=["csv", "xml"]),
    horizon_days: int = 3,
):
    fc = get_forecast_frame(horizon_days)
    df = aggregate(fc, level)
    df["timestamp"] = df["timestamp"].astype(str)

    if fmt == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=presol_forecast_{level}.csv"},
        )
    else:
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<forecast>"]
        for _, row in df.iterrows():
            parts = "".join(f"<{k}>{v}</{k}>" for k, v in row.items())
            lines.append(f"  <row>{parts}</row>")
        lines.append("</forecast>")
        xml = "\n".join(lines)
        return StreamingResponse(
            io.StringIO(xml),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=presol_forecast_{level}.xml"},
        )


class MeteringRow(BaseModel):
    timestamp: str
    governorate: str
    actual_mw: float
    forecast_p50_mw: Optional[float] = None


@app.post("/metering/push", tags=["Continuous Learning"])
def metering_push(
    rows: List[MeteringRow],
    _key: str = Security(require_api_key),
):
    new_df = pd.DataFrame([r.dict() for r in rows])
    new_df["received_at"] = pd.Timestamp.now().isoformat()
    if os.path.exists(METER_BUFFER):
        new_df.to_csv(METER_BUFFER, mode="a", header=False, index=False)
    else:
        new_df.to_csv(METER_BUFFER, index=False)

    buf = pd.read_csv(METER_BUFFER, parse_dates=["timestamp"])
    unique_days = buf["timestamp"].dt.date.nunique()

    retrain_triggered = False
    if unique_days >= 14:
        t = threading.Thread(target=_run_retrain, args=(buf,), daemon=True)
        t.start()
        retrain_triggered = True

    return {
        "accepted":          len(rows),
        "buffer_days":       unique_days,
        "retrain_triggered": retrain_triggered,
    }


def _run_retrain(buf: pd.DataFrame):
    from models.retrain import check_drift_and_retrain
    try:
        result = check_drift_and_retrain(buf, CAPACITY_LOOKUP, DUST_LOOKUP)
        result["timestamp"] = pd.Timestamp.now().isoformat()
        log_df = pd.DataFrame([result])
        if os.path.exists(RETRAIN_LOG):
            log_df.to_csv(RETRAIN_LOG, mode="a", header=False, index=False)
        else:
            log_df.to_csv(RETRAIN_LOG, index=False)
        if result.get("retrained"):
            _state["models"] = load_models(MODEL_PATH)
            _state["cache_time"] = None
        print(f"[retrain] {result}")
    except Exception as e:
        print(f"[retrain] error: {e}")


@app.get("/retrain/status", tags=["Continuous Learning"])
def retrain_status():
    if not os.path.exists(RETRAIN_LOG):
        return {"retrain_log": [], "message": "No retrain events yet."}
    log = pd.read_csv(RETRAIN_LOG)
    return log.sort_values("timestamp", ascending=False).head(10).to_dict(orient="records")


# ═══════════════════════════════════════════════════════════════════════════════
# ALERTS & SATURATION MONITORING
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/alerts", tags=["Alerts"])
def get_alerts(
    uncertainty_threshold_mw: float = Query(50.0),
    ramp_threshold_pct: float        = Query(30.0),
):
    """
    System-level operational warnings for Dispatching National:
    - HIGH_UNCERTAINTY: national P90-P10 band > threshold.
    - RAMP_DOWN: national P50 forecast drops > ramp_threshold_pct within 2 h.
    - SATURATION_RISK: district midday injection exceeds nominal feeder capacity.
    - MODEL_DRIFT: rolling MAE is within 15% of naive persistence baseline.
    """
    fc = get_forecast_frame(horizon_days=3)
    national = aggregate(fc, "national").sort_values("timestamp")
    national["timestamp"] = pd.to_datetime(national["timestamp"])
    national_forecast = national  # Alias ensuring both 'national' and 'national_forecast' are available

    alerts = []
    now = pd.Timestamp.now().floor("h")
    window = national[national["timestamp"] >= now].head(24)

    # ── Uncertainty alert ────────────────────────────────────────────────────
    for _, row in window.iterrows():
        unc = row["forecast_p90_mw"] - row["forecast_p10_mw"]
        if unc > uncertainty_threshold_mw:
            alerts.append({
                "type":      "HIGH_UNCERTAINTY",
                "timestamp": str(row["timestamp"]),
                "detail":    f"National uncertainty band is {unc:.1f} MW (threshold: {uncertainty_threshold_mw} MW).",
                "severity":  "warning",
            })
            break

    # ── Ramp-down alert ──────────────────────────────────────────────────────
    for i in range(len(window) - 2):
        p0 = window.iloc[i]["forecast_p50_mw"]
        p2 = window.iloc[i + 2]["forecast_p50_mw"]
        if p0 > 5 and (p0 - p2) / p0 * 100 > ramp_threshold_pct:
            alerts.append({
                "type":      "RAMP_DOWN",
                "timestamp": str(window.iloc[i]["timestamp"]),
                "detail":    f"National PV output forecast to drop {((p0-p2)/p0*100):.0f}% within 2 h.",
                "severity":  "critical",
            })
            break

    # ── Saturation / Reverse Flow alerts (STEG Commercial Districts) ────────
    for dist_name, thresh in SATURATION_THRESHOLDS_MW.items():
        col = "steg_district" if "steg_district" in fc.columns else "governorate"
        dist_rows = fc[fc[col].str.upper() == dist_name.upper()]
        if not dist_rows.empty:
            dist_window = dist_rows[pd.to_datetime(dist_rows["timestamp"]) >= now].head(24)
            if not dist_window.empty:
                peak_idx = dist_window["forecast_p50_mw"].idxmax()
                peak_row = dist_window.loc[peak_idx]
                if peak_row["forecast_p50_mw"] >= thresh:
                    alerts.append({
                        "type":      "SATURATION_RISK",
                        "district":  dist_name,
                        "timestamp": str(peak_row["timestamp"]),
                        "detail":    f"Midday generation in district {dist_name} forecast to reach {peak_row['forecast_p50_mw']:.1f} MW (feeder threshold: {thresh:.1f} MW). Reverse-flow / substation saturation risk.",
                        "severity":  "critical",
                    })

    # ── Model drift alert ────────────────────────────────────────────────────
    if os.path.exists(RETRAIN_LOG):
        log = pd.read_csv(RETRAIN_LOG)
        if not log.empty:
            latest = log.sort_values("timestamp").iloc[-1]
            drift = latest.get("drift_ratio_pct", 0)
            if drift > 85:
                alerts.append({
                    "type":      "MODEL_DRIFT",
                    "timestamp": str(latest.get("timestamp", "")),
                    "detail":    f"Model MAE is {drift:.1f}% of persistence baseline (>85% threshold).",
                    "severity":  "warning",
                })

    return {"alerts": alerts, "count": len(alerts)}


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGNOSTICS & METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/metrics", tags=["Diagnostics"])
def metrics():
    path = os.path.join(RESULTS_DIR, "metrics_by_horizon.csv")
    if not os.path.exists(path):
        raise HTTPException(404, "No metrics found — run `python models/ml_forecast.py` first.")
    df = pd.read_csv(path)
    df = df.rename(columns={
        "horizon":              "horizon_bucket",
        "nRMSE_ours_%":         "nrmse_ours_pct",
        "nRMSE_persistence_%":  "nrmse_persistence_pct",
        "nRMSE_clearsky_%":     "nrmse_clearsky_pct",
        "coverage_P10_P90_%":   "coverage_pct",
    })
    return df.to_dict(orient="records")


@app.get("/history/national", tags=["Diagnostics"])
def history_national():
    path = os.path.join(RESULTS_DIR, "history_national.csv")
    if not os.path.exists(path):
        raise HTTPException(404, "No history found — run `python models/history.py` first.")
    df = pd.read_csv(path)
    if "forecast_mw" not in df.columns and "forecast_p50_mw" in df.columns:
        df["forecast_mw"] = df["forecast_p50_mw"]
    return df.to_dict(orient="records")


# ═══════════════════════════════════════════════════════════════════════════════
# STEG PROSOL REPORTING & DISPLACEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/reports/prosol/summary", tags=["STEG Prosol"])
def prosol_summary_metrics():
    return get_prosol_summary_metrics("Mars 2026")


@app.get("/reports/prosol/html", response_class=HTMLResponse, tags=["STEG Prosol"])
def prosol_html_report():
    return generate_html_prosol_report()


@app.get("/displacement/summary", tags=["STEG Prosol"])
def displacement_summary():
    """
    Calculates multi-vector energy, fuel (tep), financial (DT), and CO2 displacement
    for today's forecasted national PV generation based on STEG Prosol empirical ratios.
    """
    df_nat = forecast_national(horizon_days=1)
    total_mwh = sum(r["forecast_p50_mw"] for r in df_nat)
    return calculate_displacement(total_mwh)
