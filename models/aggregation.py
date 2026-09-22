"""
Aggregates per-district (50 STEG commercial districts) forecasts up to
Direction, and national level.

Aggregation levels:
  'steg_district' — the 50 STEG commercial districts (finest grain)
  'direction'     — the 7 STEG Directions de Distribution
  'national'      — Tunisia total

Uncertainty bands are combined assuming partial independence of district-level
forecast errors (sqrt-sum-of-squares on the half-width). For adjacent districts
sharing the same cloud system, this slightly under-states uncertainty — a full
spatial covariance model would be more accurate (Bremnes 2004).
"""

import numpy as np
import pandas as pd


def _combine_band(p50_sum: float, half_widths: np.ndarray):
    """Combine per-district uncertainty half-widths into an aggregate band."""
    combined_half_width = np.sqrt((half_widths ** 2).sum())
    return p50_sum - combined_half_width, p50_sum + combined_half_width


def aggregate(df_forecast: pd.DataFrame, level: str) -> pd.DataFrame:
    """
    df_forecast: output of ml_forecast.predict(), must include
    'timestamp', 'steg_district' (or 'governorate'), 'direction',
    'forecast_p10_mw', 'forecast_p50_mw', 'forecast_p90_mw'.

    level:
      'national'     — sum across all districts
      'direction'    — sum by STEG Direction de Distribution (7 groups)
      'steg_district'— keep per-STEG-district rows (50 groups)
      'district'     — legacy alias for 'direction' (backward compat)
    """
    df = df_forecast.copy()
    df["half_width"] = (df["forecast_p90_mw"] - df["forecast_p10_mw"]) / 2

    # Resolve grouping column
    if level == "national":
        group_cols = ["timestamp"]
    elif level == "direction":
        col = "direction" if "direction" in df.columns else ("district" if "district" in df.columns else None)
        if not col:
            raise KeyError("Neither 'direction' nor 'district' found in DataFrame")
        group_cols = ["timestamp", col]
    elif level == "governorate":
        col = "governorate" if "governorate" in df.columns else "steg_district"
        group_cols = ["timestamp", col]
    elif level == "steg_district":
        col = "steg_district" if "steg_district" in df.columns else ("governorate" if "governorate" in df.columns else None)
        if not col:
            raise KeyError("Neither 'steg_district' nor 'governorate' found in DataFrame")
        group_cols = ["timestamp", col]
    elif level == "district":
        # Legacy: group by 'district' column (or direction)
        col = "district" if "district" in df.columns else ("direction" if "direction" in df.columns else None)
        if not col:
            raise KeyError("Neither 'district' nor 'direction' found in DataFrame")
        group_cols = ["timestamp", col]
    else:
        raise ValueError(f"Unknown aggregation level '{level}'. "
                         f"Use 'national', 'direction', 'governorate', 'steg_district', or 'district'.")

    rows = []
    for keys, g in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)

        p50_sum = g["forecast_p50_mw"].sum()
        lo, hi = _combine_band(p50_sum, g["half_width"].values)
        row = {
            "forecast_p50_mw": round(p50_sum, 3),
            "forecast_p10_mw": round(max(lo, 0), 3),
            "forecast_p90_mw": round(hi, 3),
        }
        for k, v in zip(group_cols, keys):
            row[k] = v
        rows.append(row)

    result = pd.DataFrame(rows)

    # Rename direction → district for legacy callers expecting 'district' column
    if level == "district" and "direction" in result.columns and "district" not in result.columns:
        result = result.rename(columns={"direction": "district"})

    return result


def aggregate_with_weather(df_forecast: pd.DataFrame, level: str) -> pd.DataFrame:
    """
    Like aggregate(), but also carries through mean weather conditions per group.
    Used by the /forecast/map endpoint to show weather alongside the forecast.
    """
    df = df_forecast.copy()

    weather_cols = [c for c in ["ghi_wm2", "temp_c", "cloud_cover_pct", "wind_speed_ms"] if c in df.columns]

    if level == "national":
        group_cols = ["timestamp"]
    elif level in ("direction", "district"):
        group_cols = ["timestamp", "direction"]
    elif level == "governorate":
        col = "governorate" if "governorate" in df.columns else "steg_district"
        group_cols = ["timestamp", col]
    elif level == "steg_district":
        group_cols = ["timestamp", "steg_district"]
    else:
        group_cols = ["timestamp"]

    df["half_width"] = (df["forecast_p90_mw"] - df["forecast_p10_mw"]) / 2
    rows = []
    for keys, g in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)

        p50_sum = g["forecast_p50_mw"].sum()
        lo, hi = _combine_band(p50_sum, g["half_width"].values)
        row = {
            "forecast_p50_mw": round(p50_sum, 3),
            "forecast_p10_mw": round(max(lo, 0), 3),
            "forecast_p90_mw": round(hi, 3),
        }
        for k, v in zip(group_cols, keys):
            row[k] = v
        # Mean weather for the group
        for wc in weather_cols:
            row[wc] = round(float(g[wc].mean()), 2)
        rows.append(row)

    return pd.DataFrame(rows)


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.steg_districts import STEG_DISTRICTS
    from ingestion.synthetic_data import generate_all
    from models.ml_forecast import load_models, predict

    capacity_lookup = {d.name: d.installed_capacity_mwc for d in STEG_DISTRICTS}
    dust_lookup     = {d.name: d.dust_loss_pct           for d in STEG_DISTRICTS}

    # synthetic_data.generate_all expects Governorate-like objects; StegDistrict is compatible
    df = generate_all(STEG_DISTRICTS, start="2024-06-01", end="2024-06-02")
    models = load_models(os.path.join(os.path.dirname(__file__), "artifacts", "quantile_models.joblib"))
    fc = predict(models, df, capacity_lookup, dust_lookup)

    print("=== Direction level (noon snapshot) ===")
    dir_agg = aggregate(fc, "direction")
    ts = dir_agg["timestamp"].iloc[12]
    print(dir_agg[dir_agg["timestamp"] == ts])

    print("\n=== National level (noon snapshot) ===")
    nat_agg = aggregate(fc, "national")
    print(nat_agg.iloc[[12]])

    print("\n=== STEG District level (Sfax districts at noon) ===")
    sd_agg = aggregate(fc, "steg_district")
    sfax = sd_agg[sd_agg["steg_district"].str.startswith("SFAX") & (sd_agg["timestamp"] == ts)]
    print(sfax)
