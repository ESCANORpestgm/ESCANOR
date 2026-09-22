"""Run candidate retraining from the generated/validated rooftop history.

This is a workflow-validation command. Use a real validated measurement
snapshot instead of synthetic history before treating the result as useful.

Run:
    python -m models.retrain_historical
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from api.core import CAPACITY_LOOKUP, DUST_LOOKUP, RETRAIN_LOG
from models.retrain import check_drift_and_retrain
from models.rooftop_training_adapter import build_training_frame

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "results" / "datasets" / "rooftop_actual_15min.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()

    training_frame = build_training_frame(args.dataset)
    result = check_drift_and_retrain(training_frame, CAPACITY_LOOKUP, DUST_LOOKUP)
    result["timestamp"] = pd.Timestamp.now().isoformat()
    result["source"] = "synthetic_solnet_style"
    log_frame = pd.DataFrame([result])
    if RETRAIN_LOG.exists():
        log_frame.to_csv(RETRAIN_LOG, mode="a", header=False, index=False)
    else:
        log_frame.to_csv(RETRAIN_LOG, index=False)
    print(result)


if __name__ == "__main__":
    main()
