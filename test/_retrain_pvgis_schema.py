"""Retrain the production model on the PVGIS feature schema the dashboard scores with.

``models.retrain_historical`` builds its frame through the measurement adapter,
which carries only GHI/temperature/cloud; the deployed scoring paths
(``models.history``, ``models.validation_report``, the horizon backtest) feed the
real PVGIS ``dni/dhi/wind_speed`` columns instead. Training and scoring must see
the same feature distributions, so this driver passes the hourly dataset through
``load_hourly_dataset`` — byte-identical to what history scores.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pathlib import Path

import pandas as pd

from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.pvgis_dataset import load_hourly_dataset
from models.retrain import append_retrain_log, check_drift_and_retrain

SOURCE_LABEL = "pvgis_hourly_schema"


def main() -> None:
    frame = load_hourly_dataset(Path("results/datasets/rooftop_actual_hourly.csv"))
    result = check_drift_and_retrain(frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP)
    result["timestamp"] = pd.Timestamp.now().isoformat()
    result["source"] = SOURCE_LABEL
    append_retrain_log(result)
    print(result)


if __name__ == "__main__":
    main()
