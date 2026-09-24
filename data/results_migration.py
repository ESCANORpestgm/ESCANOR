"""Move a pre-categorisation ``results/`` tree onto the current layout.

``data.paths`` resolves both layouts at read time, so an old checkout keeps
working without this module. Running it makes the categorised layout *permanent*
instead of relying on that fallback on every read:

1. every artifact still sitting at its flat location is moved into its category
   directory (``paths.LEGACY_RELOCATIONS`` is the only table consulted);
2. every path *recorded inside* an artifact — model registry JSON, evaluation
   summaries, history CSV columns — is rewritten to the canonical form produced
   by ``paths.store_artifact``: project-relative and in the current layout.
   Records written by an earlier checkout of the repository, which baked in an
   absolute path, are normalised by the same rule.

Both steps are idempotent, so the migration can be re-run at any time, and it is
what a deployment should run after upgrading this repository.

Run:
    python -m data.results_migration            # migrate in place
    python -m data.results_migration --check    # report, change nothing
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import re
from pathlib import Path

from data.paths import (
    DATASETS_DIR,
    FIGURES_DIR,
    LEGACY_RELOCATIONS,
    MEASUREMENTS_DIR,
    RESULTS_ROOT,
    resolve,
    store_artifact,
)

RECORD_SUFFIXES = {".csv", ".json", ".jsonl"}
# Bulk-data directories hold datasets, weather caches and images: they never
# record a path, and scanning them would read hundreds of megabytes for nothing.
BULK_DATA_DIRS: tuple[Path, ...] = (DATASETS_DIR, MEASUREMENTS_DIR, FIGURES_DIR)
# A path recorded inside a record: an optional (absolute) directory prefix,
# including its leading ``/``, the ``results/`` directory, then the artifact
# path. Quotes and commas delimit records, so they are deliberately outside the
# character class.
RECORDED_PATH_RE = re.compile(r"(?:[A-Za-z0-9_.\-+]*/)*results/([A-Za-z0-9_.\-+/-]+)")


def plan_relocations(results_root: Path = RESULTS_ROOT) -> list[tuple[Path, Path]]:
    """Flat locations that still hold an artifact whose category path is free."""
    moves: list[tuple[Path, Path]] = []
    for legacy_relative, current_relative in LEGACY_RELOCATIONS.items():
        legacy = results_root / legacy_relative
        current = results_root / current_relative
        if legacy.exists() and not current.exists():
            moves.append((legacy, current))
    return sorted(moves)


def apply_relocations(moves: list[tuple[Path, Path]], *, check: bool = False) -> list[str]:
    """Move each planned artifact into its category directory; return descriptions."""
    actions = []
    for legacy, current in moves:
        actions.append(f"{legacy.relative_to(RESULTS_ROOT)} -> {current.relative_to(RESULTS_ROOT)}")
        if not check:
            current.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(current)  # category directories move as a whole, with their contents
    return actions


def rewrite_recorded_paths(root: Path = RESULTS_ROOT, *, check: bool = False) -> list[str]:
    """Normalise every ``results/`` path recorded inside the artifacts under ``root``."""
    changed: list[str] = []
    for record_path in sorted(root.rglob("*")):
        if not record_path.is_file() or record_path.suffix.lower() not in RECORD_SUFFIXES:
            continue
        if any(bulk in record_path.parents for bulk in BULK_DATA_DIRS):
            continue
        text = record_path.read_text(encoding="utf-8")
        if "results/" not in text:
            continue

        pieces: list[str] = []
        position = 0
        rewritten = 0
        for match in RECORDED_PATH_RE.finditer(text):
            canonical = _canonical_record(root, match.group(1))
            if canonical is None or canonical == match.group():
                continue
            pieces.append(text[position:match.start()])
            pieces.append(canonical)
            position = match.end()
            rewritten += 1
        if not rewritten:
            continue

        pieces.append(text[position:])
        changed.append(f"{record_path.relative_to(root)}: {rewritten} recorded path(s)")
        if not check:
            record_path.write_text("".join(pieces), encoding="utf-8")
    return changed


def _canonical_record(results_root: Path, relative: str) -> str | None:
    """Canonical text for a recorded ``results/``-relative path, if it should change.

    ``None`` means "leave the record alone": either the artifact is not on disk
    (prose that merely mentions ``results/``, or a run whose output was deleted)
    or the record already holds the canonical path.
    """
    if not resolve(results_root / relative).exists():
        return None
    return store_artifact(results_root / relative)


def migrate(results_root: Path = RESULTS_ROOT, *, check: bool = False) -> dict[str, list[str]]:
    """Run both steps and return what they did (or would do, with ``check``)."""
    return {
        "relocated": apply_relocations(plan_relocations(results_root), check=check),
        "rewritten": rewrite_recorded_paths(results_root, check=check),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report changes without applying them")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_ROOT)
    args = parser.parse_args()

    report = migrate(args.results_dir, check=args.check)
    for heading, key in (("move", "relocated"), ("rewrite", "rewritten")):
        print(f"{'would ' if args.check else ''}{heading} {len(report[key])} "
              f"{'artifact(s)' if key == 'relocated' else 'record file(s)'}:")
        for action in report[key]:
            print(f"  {action}")
    if not any(report.values()):
        print("results/ is already on the current layout")


if __name__ == "__main__":
    main()
