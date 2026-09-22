"""Convert validated rooftop measurements to the model's canonical training schema."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

REQUIRED_MEASUREMENT_COLUMNS = {
    "timestamp_utc", "location_id", "power_kw", "district", "direction",
}
WEATHER_COLUMNS = {"ghi_wm2", "temp_c", "cloud_cover_pct"}


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
