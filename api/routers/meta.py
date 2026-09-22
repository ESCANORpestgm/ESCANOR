"""Metadata, cache, district, and registry endpoints."""

import pandas as pd
from fastapi import APIRouter

from api.core import DISTRICT_CAPACITY_LOOKUP, _state
from data.steg_districts import AVG_UNIT_KWC, DIRECTIONS, STEG_DISTRICTS, project_capacity

router = APIRouter(tags=["Meta"])


@router.get("/")
def root():
    return {
        "service": "STEG PréSol PV Forecast Platform",
        "version": "2.0.0",
        "status": "ok",
        "endpoints": [
            "/status", "/cache/status", "/steg-districts", "/districts/positions",
            "/governorates", "/districts", "/registry/pipeline",
            "/forecast/national", "/forecast/intraday", "/forecast/directions",
            "/forecast/direction/{direction}", "/forecast/steg-district/{name}",
            "/forecast/district/{district}", "/forecast/districts",
            "/forecast/governorate/{governorate}", "/forecast/map", "/forecast/timelapse",
            "/forecast/refresh", "/export/forecast", "/metering/push", "/models/retrain",
            "/retrain/status", "/alerts", "/metrics", "/history/national", "/history/rooftop",
            "/reports/prosol/summary", "/reports/prosol/snapshot", "/reports/prosol/html",
            "/reports/prosol/history", "/evaluations/history", "/models/production",
            "/models/versions", "/models/training-runs", "/displacement/summary",
        ],
    }


@router.get("/status")
def status():
    cache_age = None
    if _state["cache_time"] is not None:
        cache_age = round((pd.Timestamp.now().floor("h") - _state["cache_time"]).total_seconds() / 60, 1)
    return {
        "data_source": _state["data_source"],
        "total_capacity_mwc": round(sum(DISTRICT_CAPACITY_LOOKUP.values()), 1),
        "districts_count": len(STEG_DISTRICTS),
        "directions_count": len(DIRECTIONS),
        "cache_age_min": cache_age,
    }


@router.get("/cache/status")
def cache_status():
    cache_age = None
    if _state["cache_time"] is not None:
        cache_age = round((pd.Timestamp.now().floor("h") - _state["cache_time"]).total_seconds() / 60, 1)
    return {
        "data_source": _state["data_source"],
        "last_refreshed": str(_state["cache_time"]) if _state["cache_time"] else None,
        "cache_age_min": cache_age,
        "is_stale": cache_age is None or cache_age >= 29,
    }


@router.get("/steg-districts", tags=["STEG Prosol"])
def list_steg_districts():
    return [
        {
            "name": district.name,
            "direction": district.direction,
            "governorate": district.governorate,
            "lat": district.lat,
            "lon": district.lon,
            "installed_capacity_mwc": district.installed_capacity_mwc,
            "pending_dossiers": district.pending_dossiers,
            "dust_loss_pct": district.dust_loss_pct,
            "execution_rate_pct": district.execution_rate_pct,
        }
        for district in STEG_DISTRICTS
    ]


@router.get("/districts/positions", tags=["STEG Prosol"])
def district_positions():
    return list_steg_districts()


@router.get("/governorates", tags=["Registry"])
def list_governorates():
    return [
        {
            "name": district.name,
            "district": district.direction,
            "direction": district.direction,
            "governorate": district.governorate,
            "lat": district.lat,
            "lon": district.lon,
            "installed_capacity_mwc": district.installed_capacity_mwc,
            "dust_loss_pct": district.dust_loss_pct,
            "pending_connections": district.pending_dossiers,
            "execution_rate_pct": district.execution_rate_pct,
        }
        for district in STEG_DISTRICTS
    ]


@router.get("/districts", tags=["Registry"])
def list_districts():
    return DIRECTIONS


@router.get("/registry/pipeline", tags=["Registry"])
def registry_pipeline():
    output = []
    for district in sorted(STEG_DISTRICTS, key=lambda item: item.pending_dossiers, reverse=True):
        projected_30 = project_capacity(district, 30)
        projected_90 = project_capacity(district, 90)
        output.append({
            "district": district.name,
            "direction": district.direction,
            "governorate": district.governorate,
            "current_mwc": district.installed_capacity_mwc,
            "pending_dossiers": district.pending_dossiers,
            "avg_unit_kwc": AVG_UNIT_KWC,
            "exec_rate_pct": district.execution_rate_pct,
            "projected_mwc_30d": projected_30,
            "projected_mwc_90d": projected_90,
            "added_mwc_90d": round(projected_90 - district.installed_capacity_mwc, 3),
        })
    return output
