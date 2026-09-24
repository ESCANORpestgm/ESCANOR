"""Runtime state, forecast pipeline, scheduler, and application lifecycle.

Depends only on ``api.config`` for paths and lookups.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any, cast

import pandas as pd

from api.config import (
    CALIBRATION_PATH,
    CAPACITY_LOOKUP,
    DUST_LOOKUP,
    METER_BUFFER,
    MODEL_PATH,
)
from data.steg_districts import STEG_DISTRICTS
from ingestion import weather_client
from ingestion.synthetic_data import generate_all
from models.artifacts import load_models
from models.calibration import load_calibration
from models.ml_forecast import predict
from reports.prosol_history_db import import_generated_snapshots

# ── Shared application state ────────────────────────────────────────────────

_state: dict[str, Any] = {
    "models": None,
    "cache": None,
    "cache_time": None,
    "data_source": "unknown",
    "refresh_lock": threading.Lock(),
    "capacity_lookup": CAPACITY_LOOKUP,
    "dust_lookup": DUST_LOOKUP,
    "calibration": None,
}

# ── Lazy loaders ────────────────────────────────────────────────────────────


def get_calibration() -> dict:
    """Cached conformal calibration of the production artifact."""
    if _state["calibration"] is None:
        _state["calibration"] = load_calibration(CALIBRATION_PATH)
    return _state["calibration"]


def get_models() -> dict:
    if _state["models"] is None:
        _state["models"] = load_models(MODEL_PATH)
    return _state["models"]


# ── Forecast pipeline ───────────────────────────────────────────────────────


def build_forecast(horizon_days: int = 3) -> pd.DataFrame:
    """Build (or return cached) national PV forecast for all STEG districts."""
    with _state["refresh_lock"]:
        now = pd.Timestamp.now(tz="Africa/Tunis").tz_localize(None).floor("h")
        if _state["cache"] is not None and _state["cache_time"] is not None:
            age_min = (now - _state["cache_time"]).total_seconds() / 60
            if age_min < 14:
                return _state["cache"]

        # Live weather → synthetic fallback
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

        calibration = get_calibration()
        forecast = predict(
            get_models(), cast(pd.DataFrame, weather), CAPACITY_LOOKUP, DUST_LOOKUP,
            conformal_q=calibration.get("conformal_q", 0.0),
            horizon_scales=calibration.get("horizon_scales"),
        )
        _state["cache"] = forecast
        _state["cache_time"] = now
        return forecast


def get_forecast_frame(horizon_days: int = 3) -> pd.DataFrame:
    """Public alias for ``build_forecast``."""
    return build_forecast(horizon_days)


# ── Bias correction ─────────────────────────────────────────────────────────


def compute_bias_correction() -> float | None:
    """Ratio of actual MW to forecast P50 over the last 3 hours, or ``None``."""
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


# ── Scheduled tasks ─────────────────────────────────────────────────────────


def scheduled_refresh() -> None:
    """Refresh the forecast cache, but only during Tunisian daylight hours."""
    local_hour = pd.Timestamp.now(tz="Africa/Tunis").hour
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


# ── Application lifespan ────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: Any):
    """FastAPI lifespan hook: import snapshots, start background scheduler."""
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
