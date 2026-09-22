"""Operational alerts and diagnostic metric endpoints."""

from typing import cast

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from api.core import RESULTS_DIR, RETRAIN_LOG, get_forecast_frame
from data.steg_districts import SATURATION_THRESHOLDS_MW
from models.aggregation import aggregate

router = APIRouter(tags=["Diagnostics"])


@router.get("/alerts", tags=["Alerts"])
def get_alerts(
    uncertainty_threshold_mw: float = Query(50.0),
    ramp_threshold_pct: float = Query(30.0),
):
    forecast = get_forecast_frame(3)
    national = aggregate(forecast, "national").sort_values("timestamp")
    national["timestamp"] = pd.to_datetime(national["timestamp"])
    now = pd.Timestamp.now().floor("h")
    window = cast(pd.DataFrame, national[national["timestamp"] >= now].head(24))
    alerts = []

    if not window.empty and (window["forecast_p90_mw"] - window["forecast_p10_mw"]).max() > uncertainty_threshold_mw:
        row = window.loc[(window["forecast_p90_mw"] - window["forecast_p10_mw"]).idxmax()]
        alerts.append({"type": "HIGH_UNCERTAINTY", "timestamp": str(row["timestamp"]), "detail": f"National uncertainty exceeds {uncertainty_threshold_mw:.1f} MW.", "severity": "warning"})

    for index in range(max(0, len(window) - 2)):
        first = window.iloc[index]["forecast_p50_mw"]
        later = window.iloc[index + 2]["forecast_p50_mw"]
        if first > 5 and (first - later) / first * 100 > ramp_threshold_pct:
            alerts.append({"type": "RAMP_DOWN", "timestamp": str(window.iloc[index]["timestamp"]), "detail": f"National PV output forecast to drop {((first - later) / first * 100):.0f}% within 2 h.", "severity": "critical"})
            break

    column = "steg_district" if "steg_district" in forecast.columns else "governorate"
    for district_name, threshold in SATURATION_THRESHOLDS_MW.items():
        rows = forecast[forecast[column].str.upper() == district_name.upper()]
        if rows.empty:
            continue
        future = cast(pd.DataFrame, rows[pd.to_datetime(rows["timestamp"]) >= now])
        if future.empty:
            continue
        peak = future.loc[future["forecast_p50_mw"].idxmax()]
        if peak["forecast_p50_mw"] >= threshold:
            alerts.append({"type": "SATURATION_RISK", "district": district_name, "timestamp": str(peak["timestamp"]), "detail": f"Generation in {district_name} may reach {peak['forecast_p50_mw']:.1f} MW.", "severity": "critical"})

    if RETRAIN_LOG.exists():
        log = pd.read_csv(RETRAIN_LOG)
        if not log.empty:
            latest = log.sort_values("timestamp").iloc[-1]
            drift = latest.get("drift_ratio_pct", 0)
            if drift > 85:
                alerts.append({"type": "MODEL_DRIFT", "timestamp": str(latest.get("timestamp", "")), "detail": f"Model MAE is {drift:.1f}% of persistence baseline.", "severity": "warning"})

    return {"alerts": alerts, "count": len(alerts)}


@router.get("/metrics")
def metrics():
    path = RESULTS_DIR / "metrics_by_horizon.csv"
    if not path.exists():
        raise HTTPException(404, "No metrics found — run `python models/ml_forecast.py` first.")
    frame = pd.read_csv(path).rename(columns={
        "horizon": "horizon_bucket",
        "nRMSE_ours_%": "nrmse_ours_pct",
        "nRMSE_persistence_%": "nrmse_persistence_pct",
        "nRMSE_clearsky_%": "nrmse_clearsky_pct",
        "coverage_P10_P90_%": "coverage_pct",
    })
    return frame.to_dict(orient="records")


@router.get("/history/national")
def history_national():
    path = RESULTS_DIR / "history_national.csv"
    if not path.exists():
        raise HTTPException(404, "No history found — run `python models/history.py` first.")
    frame = pd.read_csv(path)
    if "forecast_mw" not in frame.columns and "forecast_p50_mw" in frame.columns:
        frame["forecast_mw"] = frame["forecast_p50_mw"]
    return frame.to_dict(orient="records")
