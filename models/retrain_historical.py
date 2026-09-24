"""Run candidate retraining from the generated/validated rooftop history.

This is a workflow-validation command. Use a real validated measurement
snapshot instead of synthetic history before treating the result as useful.

The retrain decision log is appended to ``results/history/retrain_log.csv``,
the same file the API and the scheduler read.

Run:
    python -m models.retrain_historical
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

import pandas as pd

from data.paths import ROOFTOP_TRAINING_DATASET_PATH
from data.steg_districts import DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP
from models.retrain import append_retrain_log, check_drift_and_retrain
from models.rooftop_training_adapter import build_training_frame

# Provenance tag written with every log entry from this command
SOURCE_LABEL = "synthetic_solnet_style"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOFTOP_TRAINING_DATASET_PATH)
    args = parser.parse_args()

    training_frame = build_training_frame(args.dataset)
    result = check_drift_and_retrain(training_frame, DISTRICT_CAPACITY_LOOKUP, DISTRICT_DUST_LOOKUP)
    result["timestamp"] = pd.Timestamp.now().isoformat()
    result["source"] = SOURCE_LABEL
    append_retrain_log(result)
    print(result)


if __name__ == "__main__":
    main()
