"""Convert validated rooftop measurements to the model's canonical training schema."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from data.steg_districts import DISTRICT_CAPACITY_LOOKUP

REQUIRED_MEASUREMENT_COLUMNS = {
    "timestamp_utc", "location_id", "power_kw", "district", "direction",
}
WEATHER_COLUMNS = {"ghi_wm2", "temp_c", "cloud_cover_pct"}

# Compliance thresholds for an upload to be usable for training. The model is
# trained on district-aggregated MW; these mirror ``models.retrain`` gates.
MIN_DAYLIGHT_PRODUCTION_MW = 0.01     # a district must exceed this during daytime
MIN_TRAINING_TIMESTAMPS = 96          # ≥ one full day of 15-minute points
MIN_TRAINING_SPAN_HOURS = 24.0
DAYLIGHT_HOUR_RANGE = (6, 18)


def assess_measurement_compliance(frame: pd.DataFrame) -> list[str]:
    """Return human-readable reasons an uploaded CSV is not trainable (empty = OK).

    Catches the two silent-failure modes that otherwise produce NaN metrics and a
    promoted garbage model: (1) district names not in the STEG registry, and
    (2) power that is single-site kW instead of district-aggregated MW, plus too
    little temporal history to build train/validation folds.
    """
    problems: list[str] = []
    working = frame.copy()
    working["_ts"] = pd.to_datetime(working["timestamp_utc"], utc=True, errors="coerce")
    working["_kw"] = pd.to_numeric(working["power_kw"], errors="coerce")

    known = set(DISTRICT_CAPACITY_LOOKUP)
    districts = working["district"].dropna().astype(str)
    unknown = sorted(set(districts) - known)
    if unknown:
        shown = ", ".join(unknown[:10]) + (" …" if len(unknown) > 10 else "")
        problems.append(
            f"Unknown district(s) not in the STEG registry: {shown}. Use canonical "
            f"district names (e.g. 'SFAX VILLE', 'TATAOUINE', 'GAFSA', 'ARIANA')."
        )

    distinct_ts = int(working["_ts"].nunique())
    if distinct_ts < MIN_TRAINING_TIMESTAMPS:
        problems.append(
            f"Only {distinct_ts} distinct timestamps; a continuous 15-minute series "
            f"with at least {MIN_TRAINING_TIMESTAMPS} points is required for temporal CV."
        )
    if working["_ts"].notna().any():
        span_hours = float((working["_ts"].max() - working["_ts"].min()).total_seconds() / 3600)
        if span_hours < MIN_TRAINING_SPAN_HOURS:
            problems.append(
                f"Time span is only {span_hours:.1f}h; at least {MIN_TRAINING_SPAN_HOURS:.0f}h of "
                "continuous history is required to build train/validation folds."
            )

    district_level = (
        working.dropna(subset=["_ts", "_kw", "district", "direction"])
        .groupby(["_ts", "district", "direction"], as_index=False)["_kw"].sum()
    )
    district_level["_mw"] = district_level["_kw"] / 1000.0
    daytime = district_level[
        district_level["_ts"].dt.hour.between(*DAYLIGHT_HOUR_RANGE) & (district_level["_mw"] > 0)
    ]["_mw"]
    if daytime.empty or float(daytime.max()) < MIN_DAYLIGHT_PRODUCTION_MW:
        problems.append(
            "District-level daytime production never exceeds the "
            f"{MIN_DAYLIGHT_PRODUCTION_MW} MW gate — the data looks like single-site kW "
            "rather than district-aggregated MW. Scale power_kw so each "
            "district/direction sum is a realistic fleet output (up to its installed capacity)."
        )
    return problems


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED_MEASUREMENT_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Validated rooftop data is missing columns: {sorted(missing)}")
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="coerce")
    frame["power_kw"] = pd.to_numeric(frame["power_kw"], errors="coerce")
    return frame


def build_training_frame(measurement_path: Path, weather_path: Path | None = None) -> pd.DataFrame:
    """Build model-ready district rows from valid rooftop measurements.

    Weather must either be present in the validated measurement snapshot or be
    supplied separately with timestamp_utc, district, and the weather columns.
    No weather defaults are used for training data.
    """
    measurements = _read_csv(measurement_path)
    quality_status = (
        measurements["quality_status"]
        if "quality_status" in measurements.columns
        else pd.Series("valid", index=measurements.index)
    )
    valid = measurements[
        measurements["timestamp_utc"].notna()
        & measurements["power_kw"].notna()
        & measurements["district"].notna()
        & measurements["direction"].notna()
        & quality_status.eq("valid")
    ].copy()
    if valid.empty:
        raise ValueError("No valid rooftop measurements are available for training")

    grouped = cast(pd.DataFrame, (
        valid.groupby(["timestamp_utc", "district", "direction"], as_index=False)
        .agg(production_kw=("power_kw", "sum"))
    ))
    grouped["timestamp"] = pd.to_datetime(grouped.pop("timestamp_utc"), utc=True).dt.tz_localize(None)
    grouped["governorate"] = grouped.pop("district")
    grouped["production_mw"] = grouped.pop("production_kw") / 1000.0

    source = valid
    if not WEATHER_COLUMNS.issubset(source.columns):
        if weather_path is None:
            raise ValueError(
                "Weather columns are required for model training. Include ghi_wm2, "
                "temp_c, and cloud_cover_pct in the measurement import or provide --weather."
            )
        weather = pd.read_csv(weather_path)
        required_weather = {"timestamp_utc", "district", *WEATHER_COLUMNS}
        missing = required_weather - set(weather.columns)
        if missing:
            raise ValueError(f"Weather data is missing columns: {sorted(missing)}")
        weather["timestamp_utc"] = pd.to_datetime(weather["timestamp_utc"], utc=True, errors="coerce")
        weather["timestamp"] = pd.to_datetime(weather.pop("timestamp_utc"), utc=True).dt.tz_localize(None)
        weather["governorate"] = weather.pop("district")
        grouped = grouped.merge(
            weather[["timestamp", "governorate", *WEATHER_COLUMNS]],
            on=["timestamp", "governorate"], how="inner",
        )
    else:
        weather_rows = cast(pd.DataFrame, source.groupby(
            ["timestamp_utc", "district"], as_index=False
        )[list(WEATHER_COLUMNS)].first())
        weather_rows["timestamp"] = pd.to_datetime(weather_rows.pop("timestamp_utc"), utc=True).dt.tz_localize(None)
        weather_rows["governorate"] = weather_rows.pop("district")
        grouped = grouped.merge(weather_rows, on=["timestamp", "governorate"], how="inner")

    if grouped.empty:
        raise ValueError("No measurement rows matched the supplied weather data")
    if weather_path is not None:
        grouped["weather_source"] = str(weather_path)
    return grouped.sort_values(["governorate", "timestamp"]).reset_index(drop=True)
