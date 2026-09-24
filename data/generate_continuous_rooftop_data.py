"""Generate the aggregate 15-minute rooftop-PV training dataset.

PVGIS is the default district-level source. Synthetic generation remains
available explicitly with ``--source synthetic`` for offline pipeline tests.
Rows are always aggregate STEG-district fleets, never individual rooftops.

Example:
    python -m data.generate_continuous_rooftop_data \
        --start 2020-01-01 --end 2025-01-01
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

from data.generate_pvgis_rooftop_data import generate_pvgis_dataset
from data.generate_rooftop_dataset import generate_rooftop_dataset
from data.io import write_dataframe
from data import paths


def build_dataset(source: str, start: str, end: str, seed: int, cache_dir: Path) -> "object":
    """Dispatch to the requested aggregate-district dataset source."""
    if source == "pvgis":
        return generate_pvgis_dataset(start, end, cache_dir)
    frame = generate_rooftop_dataset(start, end, seed, frequency="15min")
    frame["source"] = "synthetic_steg_style"
    frame["dataset_version"] = "rooftop_aggregate_15min_v1"
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2021-01-01")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source", choices=["pvgis", "synthetic"], default="pvgis")
    parser.add_argument("--cache-dir", type=Path, default=paths.PVGIS_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=paths.ROOFTOP_TRAINING_DATASET_PATH)
    args = parser.parse_args()

    frame = build_dataset(args.source, args.start, args.end, args.seed, args.cache_dir)
    saved = write_dataframe(frame, args.output)
    print(f"Generated {len(frame):,} 15-minute aggregate rows across {frame['district'].nunique()} districts")
    print(f"Saved {args.source} dataset: {saved}")


if __name__ == "__main__":
    main()
