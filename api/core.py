"""Shared API state, paths, authentication, forecasting, and lifecycle services."""

from __future__ import annotations

import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import (
    DISTRICT_CAPACITY_LOOKUP,
    DISTRICT_DUST_LOOKUP,
    GOVERNORATES,
    STEG_DISTRICTS,
)
from ingestion import weather_client
from ingestion.synthetic_data import generate_all
from models.ml_forecast import load_models, predict
from reports.prosol_history_db import import_generated_snapshots

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "artifacts" / "quantile_models.joblib"
RESULTS_DIR = ROOT / "results"
METER_BUFFER = RESULTS_DIR / "metering_buffer.csv"
RETRAIN_LOG = RESULTS_DIR / "retrain_log.csv"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CAPACITY_LOOKUP = {
    **{item.name: item.installed_capacity_mwc for item in GOVERNORATES},
    **DISTRICT_CAPACITY_LOOKUP,
}
DUST_LOOKUP = {
    **{item.name: item.dust_loss_pct for item in GOVERNORATES},
    **DISTRICT_DUST_LOOKUP,
}

_API_KEY = os.environ.get("PRESOL_API_KEY", "dev-key")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(_api_key_header)) -> str:
    if key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key header.")
    return key


_state: dict[str, Any] = {
    "models": None,
    "cache": None,
    "cache_time": None,
    "data_source": "unknown",
    "refresh_lock": threading.Lock(),
    "capacity_lookup": CAPACITY_LOOKUP,
    "dust_lookup": DUST_LOOKUP,
}


def get_models() -> dict:
    if _state["models"] is None:
        _state["models"] = load_models(str(MODEL_PATH))
    return _state["models"]


def build_forecast(horizon_days: int = 3) -> pd.DataFrame:
    with _state["refresh_lock"]:
        now = pd.Timestamp.now(tz="Africa/Tunis").tz_localize(None).floor("h")
        if _state["cache"] is not None and _state["cache_time"] is not None:
            age_min = (now - _state["cache_time"]).total_seconds() / 60
            if age_min < 14:
                return _state["cache"]

        try:
            weather = weather_client.build_live_weather_dataframe(STEG_DISTRICTS, days_ahead=horizon_days)
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
            weather = weather[(weather.timestamp >= now) & (weather.timestamp <= now + pd.Timedelta(days=horizon_days))]
            _state["data_source"] = "synthetic"

        forecast = predict(get_models(), cast(pd.DataFrame, weather), CAPACITY_LOOKUP, DUST_LOOKUP)
        _state["cache"] = forecast
        _state["cache_time"] = now
        return forecast


def get_forecast_frame(horizon_days: int = 3) -> pd.DataFrame:
    return build_forecast(horizon_days)


def compute_bias_correction() -> float | None:
    if not METER_BUFFER.exists():
        return None
    try:
        buffer = pd.read_csv(METER_BUFFER, parse_dates=["timestamp"])
        recent = buffer[buffer["timestamp"] >= pd.Timestamp.now() - pd.Timedelta(hours=3)]
        if len(recent) < 2:
            return None
        denominator = float(cast(Any, recent["forecast_p50_mw"].sum()))
        if denominator == 0:
            return None
        ratio = float(cast(Any, recent["actual_mw"].sum())) / denominator
        if pd.isna(ratio) or ratio <= 0 or ratio > 3:
            return None
        return float(ratio)
    except Exception:
        return None


def scheduled_refresh() -> None:
    local_hour = (datetime.utcnow() + timedelta(hours=1)).hour
    if 5 <= local_hour <= 20:
        try:
            build_forecast(horizon_days=3)
        except Exception as error:
            print(f"[scheduler] forecast refresh failed: {error}")


def scheduled_retrain() -> None:
    try:
        from api.routers.learning import scheduled_retrain as run_scheduled_retrain
        run_scheduled_retrain()
    except Exception as error:
        print(f"[scheduler] hourly retraining failed: {error}")


@asynccontextmanager
async def lifespan(app: Any):
    try:
        import_generated_snapshots()
    except Exception as error:
        print(f"[Prosol history] snapshot import failed: {error}")

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(scheduled_refresh, "interval", minutes=15, id="forecast_refresh", coalesce=True, max_instances=1)
        scheduler.add_job(scheduled_retrain, "interval", days=1, id="daily_retrain", coalesce=True, max_instances=1)
        scheduler.start()
        app.state.scheduler = scheduler
        print("[APScheduler] forecast refresh every 15 min and validated-model retraining every day → started")
    except ImportError:
        app.state.scheduler = None
        print("[APScheduler] not installed — background refresh disabled")

    yield

    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)
