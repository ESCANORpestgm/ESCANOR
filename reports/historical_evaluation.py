"""Evaluate the current model using the generated aggregate rooftop history.

This creates an immutable forecast-evaluation run under
``data.paths.EVALUATIONS_DIR`` from
``results/datasets/rooftop_actual_15min.csv``. The default source is the
PVGIS-derived aggregate district dataset; explicit synthetic datasets remain
available for offline pipeline validation.

Run:
    python -m reports.historical_evaluation
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.io import write_dataframe, write_json_atomic
from data.paths import EVALUATIONS_DIR, MODEL_PATH, ROOFTOP_TRAINING_DATASET_PATH, relative_to_project
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.inference import FORECAST_P10_COLUMN, FORECAST_P50_COLUMN, FORECAST_P90_COLUMN, predict
from models.artifacts import load_models
from models.pvgis_dataset import to_model_schema
from reports.forecast_evaluator import evaluate_forecast

# Provenance tags recorded with the run; the dataset is PVGIS-derived synthetic
# data, so the accuracy is a pipeline check, not a STEG measurement.
SOURCE_LABEL = "synthetic_solnet_style"
# MW forecasts are exported in kW to match the metering schema
MW_TO_KW = 1000.0
FORECAST_COLUMNS = {
    "forecast_p10_kw": FORECAST_P10_COLUMN,
    "forecast_p50_kw": FORECAST_P50_COLUMN,
    "forecast_p90_kw": FORECAST_P90_COLUMN,
}
SOURCE_HASH_LENGTH = 12  # leading hex characters of the dataset SHA-256


def evaluate_historical_dataset(dataset_path: Path = ROOFTOP_TRAINING_DATASET_PATH,
                                output_root: Path = EVALUATIONS_DIR) -> Path:
    """Score the deployed model on a historical dataset as an immutable run."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"Historical dataset not found: {dataset_path}")

    dataset = pd.read_csv(dataset_path)
    model_frame = to_model_schema(dataset)
    models = load_models(MODEL_PATH)
    predictions = predict(models, model_frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP)

    source_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()[:SOURCE_HASH_LENGTH]
    evaluation_id = f"historical_{source_hash}"
    output_dir = output_root / evaluation_id
    output_dir.mkdir(parents=True, exist_ok=False)

    # A forecast is assumed to have been issued ``horizon_hours`` before its
    # target timestamp; datasets without a horizon column are treated as 0 h.
    target = pd.to_datetime(dataset["timestamp_utc"], utc=True)
    horizon = pd.to_numeric(dataset.get("horizon_hours", 0), errors="coerce").fillna(0)
    created = target - pd.to_timedelta(horizon, unit="h")
    forecast = pd.DataFrame({
        "forecast_created_at": created.astype(str),
        "target_timestamp_utc": target.astype(str),
        "location_id": dataset["location_id"],
        **{column: predictions[source].to_numpy() * MW_TO_KW
           for column, source in FORECAST_COLUMNS.items()},
        "source": SOURCE_LABEL,
    })
    actual = dataset[["timestamp_utc", "location_id", "power_kw"]].copy()
    forecast_path = output_dir / "forecast.csv"
    actual_path = output_dir / "actual.csv"
    write_dataframe(forecast, forecast_path)
    write_dataframe(actual, actual_path)

    summary_path = evaluate_forecast(forecast_path, actual_path, output_dir)
    write_json_atomic(output_dir / "historical_metadata.json", {
        "evaluation_id": evaluation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_LABEL,
        "dataset_path": relative_to_project(dataset_path),
        "forecast_path": relative_to_project(forecast_path),
        "actual_path": relative_to_project(actual_path),
        "rows": len(dataset),
        "note": "Synthetic historical evaluation for pipeline validation; not real STEG accuracy.",
    })
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOFTOP_TRAINING_DATASET_PATH)
    parser.add_argument("--output-root", type=Path, default=EVALUATIONS_DIR)
    args = parser.parse_args()
    print(f"Evaluation summary: {evaluate_historical_dataset(args.dataset, args.output_root)}")


if __name__ == "__main__":
    main()
