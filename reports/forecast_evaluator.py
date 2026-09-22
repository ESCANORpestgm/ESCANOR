"""Store immutable forecast snapshots and evaluate them against actual data.

Forecast CSV columns:
    forecast_created_at, target_timestamp_utc, location_id,
    forecast_p10_kw, forecast_p50_kw, forecast_p90_kw

Actual CSV columns:
    timestamp_utc, location_id, power_kw

Usage:
    python -m reports.forecast_evaluator \
        --forecast forecast.csv \
        --actual results/measurements/.../validated_measurements.csv \
        --output results/forecast_evaluations/run.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd


def save_forecast_snapshot(
    forecast: pd.DataFrame,
    output_root: Path,
    model_version: str,
    report_snapshot: str | None = None,
    weather_source: str | None = None,
) -> Path:
    """Save a forecast run and values without overwriting previous runs."""
    required = {
        "forecast_created_at",
        "target_timestamp_utc",
        "location_id",
        "forecast_p10_kw",
        "forecast_p50_kw",
        "forecast_p90_kw",
    }
    missing = required - set(forecast.columns)
    if missing:
        raise ValueError(f"Missing forecast columns: {sorted(missing)}")

    run_id = f"forecast_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}"
    run_dir = output_root / "forecast_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    values = forecast.copy()
    values["forecast_created_at"] = pd.to_datetime(values["forecast_created_at"], utc=True)
    values["target_timestamp_utc"] = pd.to_datetime(values["target_timestamp_utc"], utc=True)
    values["run_id"] = run_id
    values["lead_time_minutes"] = (
        values["target_timestamp_utc"] - values["forecast_created_at"]
    ).dt.total_seconds().div(60)
    values.to_csv(run_dir / "forecast_values.csv", index=False)

    metadata = {
        "run_id": run_id,
        "model_version": model_version,
        "report_snapshot": report_snapshot,
        "weather_source": weather_source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(values),
        "locations": int(values["location_id"].nunique()),  # type: ignore[arg-type]
        "target_start": values["target_timestamp_utc"].min().isoformat(),
        "target_end": values["target_timestamp_utc"].max().isoformat(),
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return run_dir


def _horizon_bucket(minutes: float) -> str:
    if minutes < 60:
        return "nowcast_0_1h"
    if minutes < 6 * 60:
        return "short_term_1_6h"
    if minutes < 24 * 60:
        return "day_ahead_6_24h"
    return "extended_24h_plus"


def _metric_row(group: pd.DataFrame, group_name: str, value: object) -> dict:
    actual_mean = float(group["power_kw"].abs().mean())  # type: ignore[arg-type]
    rmse = float(np.sqrt(group["squared_error_kw"].mean()))
    return {
        group_name: value,
        "rows_evaluated": len(group),
        "mae_kw": group["absolute_error_kw"].mean(),
        "rmse_kw": rmse,
        "nrmse_pct": rmse / actual_mean * 100 if actual_mean else None,
        "bias_kw": group["error_kw"].mean(),
        "p10_p90_coverage_pct": group["covered_by_p10_p90"].mean() * 100,
        "mean_interval_width_kw": group["interval_width_kw"].mean(),
        "mean_lead_time_minutes": group["lead_time_minutes"].mean(),
    }


def _validate_evaluation_schema(forecast: pd.DataFrame, actual: pd.DataFrame) -> None:
    forecast_required = {
        "forecast_created_at", "target_timestamp_utc", "location_id",
        "forecast_p10_kw", "forecast_p50_kw", "forecast_p90_kw",
    }
    actual_required = {"timestamp_utc", "location_id", "power_kw"}
    missing_forecast = forecast_required - set(forecast.columns)
    missing_actual = actual_required - set(actual.columns)
    if missing_forecast:
        raise ValueError(f"Forecast is missing required kW columns: {sorted(missing_forecast)}")
    if missing_actual:
        raise ValueError(f"Actual measurements are missing required kW columns: {sorted(missing_actual)}")
    if any(column.endswith("_mw") for column in forecast.columns) or "power_mw" in actual.columns:
        raise ValueError("Mixed MW input detected. Forecast evaluation requires kW columns only.")


def evaluate_forecast(forecast_path: Path, actual_path: Path, output_dir: Path) -> Path:
    forecast = pd.read_csv(forecast_path)
    actual = pd.read_csv(actual_path)
    _validate_evaluation_schema(forecast, actual)
    forecast["target_timestamp_utc"] = pd.to_datetime(forecast["target_timestamp_utc"], utc=True)
    actual["timestamp_utc"] = pd.to_datetime(actual["timestamp_utc"], utc=True)

    actual_columns = ["location_id", "timestamp_utc", "power_kw"]
    for column in ("district", "direction"):
        if column in actual.columns and column not in forecast.columns:
            actual_columns.append(column)

    merged = forecast.merge(
        actual[actual_columns],
        left_on=["location_id", "target_timestamp_utc"],
        right_on=["location_id", "timestamp_utc"],
        how="inner",
    )
    if merged.empty:
        raise ValueError("No forecast rows matched actual measurements")

    merged["error_kw"] = merged["forecast_p50_kw"] - merged["power_kw"]
    merged["absolute_error_kw"] = merged["error_kw"].abs()
    merged["squared_error_kw"] = merged["error_kw"] ** 2
    merged["covered_by_p10_p90"] = merged["power_kw"].between(
        merged["forecast_p10_kw"], merged["forecast_p90_kw"], inclusive="both"
    )
    merged["interval_width_kw"] = merged["forecast_p90_kw"] - merged["forecast_p10_kw"]
    merged["lead_time_minutes"] = (
        pd.to_datetime(merged["target_timestamp_utc"], utc=True)
        - pd.to_datetime(merged["forecast_created_at"], utc=True)
    ).dt.total_seconds().div(60)
    merged["horizon_bucket"] = merged["lead_time_minutes"].map(_horizon_bucket)

    location_metrics = [
        _metric_row(group, "location_id", location_id)
        for location_id, group in merged.groupby("location_id")
    ]
    horizon_metrics = [
        _metric_row(group, "horizon_bucket", bucket)
        for bucket, group in merged.groupby("horizon_bucket", sort=False)
    ]

    group_columns = [column for column in ("direction", "district") if column in merged.columns]
    geographic_metrics = []
    if group_columns:
        for group_values, group in merged.groupby(group_columns, dropna=False):
            if not isinstance(group_values, tuple):
                group_values = (group_values,)
            metric = _metric_row(group, "group", " / ".join(str(value) for value in group_values))
            metric.update(dict(zip(group_columns, group_values)))
            geographic_metrics.append(metric)

    output_dir.mkdir(parents=True, exist_ok=True)
    evaluated_path = output_dir / "evaluated_values.csv"
    summary_path = output_dir / "summary.json"
    merged.to_csv(evaluated_path, index=False)
    summary = {
        "evaluation_id": output_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "forecast_source": str(forecast_path),
        "actual_source": str(actual_path),
        "power_unit": "kW",
        "rows_matched": len(merged),
        "metrics": location_metrics,
        "horizon_metrics": horizon_metrics,
    }
    if geographic_metrics:
        summary["geographic_metrics"] = geographic_metrics
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Evaluation summary: {evaluate_forecast(args.forecast, args.actual, args.output)}")


if __name__ == "__main__":
    main()
