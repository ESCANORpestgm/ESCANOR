"""Regenerate metrics_by_horizon.csv from the production model on out-of-sample PVGIS hours."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pathlib import Path

import pandas as pd

from data.io import write_dataframe
from data.paths import MODEL_PATH, TRAINING_METRICS_PATH
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.artifacts import load_models
from models.evaluation import evaluate_by_horizon_with_baselines
from models.pvgis_dataset import load_hourly_dataset

models = load_models(MODEL_PATH)
# The hourly derivative of the 15-minute dataset — same rows, quarter the load.
frame = load_hourly_dataset(Path("results/datasets/rooftop_actual_hourly.csv"))
# Out-of-sample only: the promoted model trained through 2020-10-19.
frame = frame[pd.to_datetime(frame["timestamp"]) >= pd.Timestamp("2020-10-20")]
metrics = evaluate_by_horizon_with_baselines(models, frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP)
print(metrics.to_string(index=False))
write_dataframe(metrics, TRAINING_METRICS_PATH)
print("wrote", TRAINING_METRICS_PATH)
