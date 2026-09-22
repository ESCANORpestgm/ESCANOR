"""Evaluate the current model using the generated aggregate rooftop history.

This creates an immutable forecast-evaluation run from
``results/datasets/rooftop_actual_15min.csv``. The default source is the
PVGIS-derived aggregate district dataset; explicit synthetic datasets remain
available for offline pipeline validation.

Run:
    python -m reports.historical_evaluation
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.history import _to_model_schema
from models.ml_forecast import load_models, predict
from reports.forecast_evaluator import evaluate_forecast

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "artifacts" / "quantile_models.joblib"
DEFAULT_DATASET = ROOT / "results" / "datasets" / "rooftop_actual_15min.csv"
DEFAULT_OUTPUT = ROOT / "results" / "forecast_evaluations"


def evaluate_historical_dataset(dataset_path: Path = DEFAULT_DATASET, output_root: Path = DEFAULT_OUTPUT) -> Path:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Historical dataset not found: {dataset_path}")

    dataset = pd.read_csv(dataset_path)
    model_frame = _to_model_schema(dataset)
    models = load_models(str(MODEL_PATH))
    predictions = predict(models, model_frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP)

    source_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()[:12]
    evaluation_id = f"historical_{source_hash}"
    output_dir = output_root / evaluation_id
    output_dir.mkdir(parents=True, exist_ok=False)

    target = pd.to_datetime(dataset["timestamp_utc"], utc=True)
    horizon = pd.to_numeric(dataset.get("horizon_hours", 0), errors="coerce").fillna(0)
    created = target - pd.to_timedelta(horizon, unit="h")
    forecast = pd.DataFrame({
        "forecast_created_at": created.astype(str),
        "target_timestamp_utc": target.astype(str),
        "location_id": dataset["location_id"],
        "forecast_p10_kw": predictions["forecast_p10_mw"].to_numpy() * 1000,
        "forecast_p50_kw": predictions["forecast_p50_mw"].to_numpy() * 1000,
        "forecast_p90_kw": predictions["forecast_p90_mw"].to_numpy() * 1000,
        "source": "synthetic_solnet_style",
    })
    actual = dataset[["timestamp_utc", "location_id", "power_kw"]].copy()
    forecast_path = output_dir / "forecast.csv"
    actual_path = output_dir / "actual.csv"
    forecast.to_csv(forecast_path, index=False)
    actual.to_csv(actual_path, index=False)

    summary_path = evaluate_forecast(forecast_path, actual_path, output_dir)
    metadata = {
        "evaluation_id": evaluation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "synthetic_solnet_style",
        "dataset_path": str(dataset_path.relative_to(ROOT)),
        "forecast_path": str(forecast_path.relative_to(ROOT)),
        "actual_path": str(actual_path.relative_to(ROOT)),
        "rows": len(dataset),
        "note": "Synthetic historical evaluation for pipeline validation; not real STEG accuracy.",
    }
    import json
    (output_dir / "historical_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(f"Evaluation summary: {evaluate_historical_dataset(args.dataset, args.output_root)}")


if __name__ == "__main__":
    main()
