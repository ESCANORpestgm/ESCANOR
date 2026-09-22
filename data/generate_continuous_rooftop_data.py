"""Generate the aggregate 15-minute rooftop-PV training dataset.

PVGIS is the default district-level source. Synthetic generation remains
available explicitly with ``--source synthetic`` for offline pipeline tests.
Rows are always aggregate STEG-district fleets, never individual rooftops.

Example:
    python -m data.generate_continuous_rooftop_data \
        --start 2020-01-01 --end 2025-01-01
"""

from __future__ import annotations

import argparse
from pathlib import Path

from data.generate_rooftop_dataset import generate_rooftop_dataset
from data.generate_pvgis_rooftop_data import generate_pvgis_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2021-01-01")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source", choices=["pvgis", "synthetic"], default="pvgis")
    parser.add_argument("--cache-dir", type=Path, default=Path("results/datasets/pvgis_cache"))
    parser.add_argument("--output", type=Path, default=Path("results/datasets/rooftop_actual_15min.csv"))
    args = parser.parse_args()

    if args.source == "pvgis":
        frame = generate_pvgis_dataset(args.start, args.end, args.cache_dir)
    else:
        frame = generate_rooftop_dataset(args.start, args.end, args.seed, frequency="15min")
        frame["source"] = "synthetic_steg_style"
        frame["dataset_version"] = "rooftop_aggregate_15min_v1"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == ".parquet":
        frame.to_parquet(args.output, index=False)
    else:
        frame.to_csv(args.output, index=False)
    print(f"Generated {len(frame):,} 15-minute aggregate rows across {frame['district'].nunique()} districts")
    print(f"Saved {args.source} dataset: {args.output}")


if __name__ == "__main__":
    main()
