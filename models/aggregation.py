"""Spatial aggregation of district forecasts to Direction and national level.

Aggregation levels:
  'steg_district' — the 50 STEG commercial districts (finest grain)
  'direction'     — the 7 STEG Directions de Distribution
  'national'      — Tunisia total
  'governorate'   — group by the governorate/steg_district column present
  'district'      — legacy alias grouping by the raw district column

Uncertainty bands can be combined with optional spatial correlation
(Bremnes 2004). When a correlation matrix is supplied, the aggregate
half-width uses the full covariance sum: hw_agg = sqrt(hw^T @ R @ hw).
Otherwise falls back to the independent sqrt-sum-of-squares approximation.
"""

from __future__ import annotations

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collections.abc import Sequence

import numpy as np
import pandas as pd

from models.inference import FORECAST_P10_COLUMN, FORECAST_P50_COLUMN, FORECAST_P90_COLUMN

# ── Aggregation contract ─────────────────────────────────────────────────────
LEVEL_NATIONAL = "national"
LEVEL_DIRECTION = "direction"
LEVEL_GOVERNORATE = "governorate"
LEVEL_STEG_DISTRICT = "steg_district"
LEVEL_DISTRICT = "district"
TIMESTAMP_COLUMN = "timestamp"
SPATIAL_KEY_COLUMNS = ("governorate", "steg_district")
# Columns summarised by mean alongside the aggregated power, for the map view
WEATHER_SUMMARY_COLUMNS = ("ghi_wm2", "temp_c", "cloud_cover_pct", "wind_speed_ms")
# The interval half-width is the band spread over two, and the reported
# probabilities are sums of the district medians rounded for the API payload.
BAND_WIDTH_DIVISOR = 2.0
METRIC_DECIMALS = 3
WEATHER_DECIMALS = 2

# Candidate grouping columns per level, tried in order after the timestamp.
_LEVEL_COLUMNS: dict[str, tuple[str, ...]] = {
    LEVEL_NATIONAL: (),
    LEVEL_DIRECTION: ("direction", "district"),
    LEVEL_GOVERNORATE: ("governorate", "steg_district"),
    LEVEL_STEG_DISTRICT: ("steg_district", "governorate"),
    LEVEL_DISTRICT: ("district", "direction"),
}


def _combine_band(p50_sum: float, half_widths: np.ndarray,
                  corr_matrix: np.ndarray | None = None) -> tuple[float, float]:
    """Combine per-district uncertainty half-widths into an aggregate band.

    When corr_matrix is None, assumes independence (sqrt-sum-of-squares).
    When supplied, uses full covariance: hw_agg = sqrt(hw^T @ R @ hw).
    This correctly accounts for spatially correlated forecast errors
    between adjacent districts sharing the same cloud systems.
    """
    hw = np.asarray(half_widths, dtype=float)
    if corr_matrix is not None and corr_matrix.shape == (len(hw), len(hw)):
        cov = np.outer(hw, hw) * corr_matrix
        combined_half_width = float(np.sqrt(np.clip(np.sum(cov), 0, None)))
    else:
        combined_half_width = float(np.sqrt((hw ** 2).sum()))
    return p50_sum - combined_half_width, p50_sum + combined_half_width


def _add_half_width(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the per-row P10–P90 half-width used by the band combination."""
    frame = df.copy()
    frame["half_width"] = (frame[FORECAST_P90_COLUMN] - frame[FORECAST_P10_COLUMN]) / BAND_WIDTH_DIVISOR
    return frame


def _band_row(keys: Sequence, group_cols: list[str], group: pd.DataFrame,
              half_widths: np.ndarray | None = None,
              corr_matrix: np.ndarray | None = None) -> dict:
    """Aggregate one group: sum the medians, combine the half-widths, label it.

    ``half_widths`` may cover a subset of ``group`` (the districts present in a
    correlation matrix); the median sum always covers the whole group.
    """
    p50_sum = float(group[FORECAST_P50_COLUMN].sum())
    widths = group["half_width"].values if half_widths is None else half_widths
    lower, upper = _combine_band(p50_sum, widths, corr_matrix)
    row = {
        FORECAST_P50_COLUMN: round(p50_sum, METRIC_DECIMALS),
        FORECAST_P10_COLUMN: round(max(lower, 0), METRIC_DECIMALS),
        FORECAST_P90_COLUMN: round(upper, METRIC_DECIMALS),
    }
    row.update(dict(zip(group_cols, keys)))
    return row


def _resolve_group_columns(df: pd.DataFrame, level: str) -> list[str]:
    """Grouping columns for ``level``, preferring the column actually present."""
    if level not in _LEVEL_COLUMNS:
        raise ValueError(
            f"Unknown aggregation level '{level}'. "
            f"Use '{LEVEL_NATIONAL}', '{LEVEL_DIRECTION}', '{LEVEL_GOVERNORATE}', "
            f"'{LEVEL_STEG_DISTRICT}', or '{LEVEL_DISTRICT}'."
        )
    candidates = _LEVEL_COLUMNS[level]
    if not candidates:
        return [TIMESTAMP_COLUMN]
    column = next((candidate for candidate in candidates if candidate in df.columns), None)
    if column is None:
        raise KeyError(f"Neither '{candidates[0]}' nor '{candidates[1]}' found in DataFrame")
    return [TIMESTAMP_COLUMN, column]


def build_spatial_correlation(models, df_hist: pd.DataFrame,
                               capacity_lookup: dict, dust_lookup: dict = None,
                               level: str = LEVEL_NATIONAL) -> pd.DataFrame:
    """Estimate residual correlation matrix from historical forecast errors.

    Returns a DataFrame (district × district) of pairwise Pearson correlations
    of P50 residuals. Use this as the corr_matrix argument to aggregate().
    """
    from models.ml_forecast import predict as _predict

    del level  # Kept for call-site compatibility; residuals are district-paired.
    preds = _predict(models, df_hist, capacity_lookup, dust_lookup)
    preds["residual"] = preds["production_mw"] - preds[FORECAST_P50_COLUMN]
    pivot = preds.pivot_table(index=TIMESTAMP_COLUMN, columns="governorate",
                              values="residual", aggfunc="mean")
    return pivot.corr()


def aggregate(df_forecast: pd.DataFrame, level: str,
              corr_matrix: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sum district forecasts into ``level`` bands.

    ``df_forecast`` is the output of ``models.inference.predict`` and must carry
    ``timestamp``, a district column matching the level, and the three forecast
    columns. ``corr_matrix`` (index = district names) is applied at national
    level only, where neighbouring districts share cloud systems.
    """
    df = _add_half_width(df_forecast)
    group_cols = _resolve_group_columns(df, level)
    spatial_col = next((column for column in SPATIAL_KEY_COLUMNS if column in df.columns), None)
    use_correlation = corr_matrix is not None and spatial_col is not None and level == LEVEL_NATIONAL

    rows = []
    for keys, group in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        sub_corr = None
        sub_widths = None
        if use_correlation:
            common = [d for d in group[spatial_col].unique().tolist() if d in corr_matrix.index]
            if len(common) > 1:
                # The covariance sum only spans the districts the correlation
                # matrix knows about; the median sum still covers the group.
                sub_corr = corr_matrix.loc[common, common].values
                sub_widths = group.loc[group[spatial_col].isin(common), "half_width"].values
        rows.append(_band_row(keys, group_cols, group, sub_widths, sub_corr))

    result = pd.DataFrame(rows)
    # Rename direction → district for legacy callers expecting a 'district' column
    if level == LEVEL_DISTRICT and "direction" in result.columns and "district" not in result.columns:
        result = result.rename(columns={"direction": "district"})
    return result


def aggregate_with_weather(df_forecast: pd.DataFrame, level: str,
                            corr_matrix: pd.DataFrame | None = None) -> pd.DataFrame:
    """Like :func:`aggregate`, but also carries mean weather per group.

    Used by the ``/forecast/map`` endpoint to show weather conditions next to
    the aggregated forecast. Levels here are advisory: an unknown level falls
    back to a national (timestamp-only) grouping instead of raising.
    ``corr_matrix`` is accepted for call-site compatibility and deliberately
    unused — the map view sums independent bands across whichever districts
    share a group.
    """
    df = _add_half_width(df_forecast)
    if level in (LEVEL_DIRECTION, LEVEL_DISTRICT):
        group_cols = [TIMESTAMP_COLUMN, "direction"]
    elif level == LEVEL_GOVERNORATE:
        group_cols = [TIMESTAMP_COLUMN,
                      "governorate" if "governorate" in df.columns else "steg_district"]
    elif level == LEVEL_STEG_DISTRICT:
        group_cols = [TIMESTAMP_COLUMN, "steg_district"]
    else:
        group_cols = [TIMESTAMP_COLUMN]

    weather_cols = [column for column in WEATHER_SUMMARY_COLUMNS if column in df.columns]
    rows = []
    for keys, group in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = _band_row(keys, group_cols, group)
        for column in weather_cols:
            row[column] = round(float(group[column].mean()), WEATHER_DECIMALS)
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from data.paths import MODEL_PATH
    from data.steg_districts import STEG_DISTRICTS
    from ingestion.synthetic_data import generate_all
    from models.artifacts import load_models
    from models.inference import predict

    NOON_ROW = 12  # hourly index of the midday snapshot printed below
    capacity_lookup = {d.name: d.installed_capacity_mwc for d in STEG_DISTRICTS}
    dust_lookup = {d.name: d.dust_loss_pct for d in STEG_DISTRICTS}

    # synthetic_data.generate_all expects Governorate-like objects; StegDistrict is compatible
    df = generate_all(STEG_DISTRICTS, start="2024-06-01", end="2024-06-02")
    models = load_models(MODEL_PATH)
    fc = predict(models, df, capacity_lookup, dust_lookup)

    print("=== Direction level (noon snapshot) ===")
    dir_agg = aggregate(fc, LEVEL_DIRECTION)
    ts = dir_agg[TIMESTAMP_COLUMN].iloc[NOON_ROW]
    print(dir_agg[dir_agg[TIMESTAMP_COLUMN] == ts])

    print("\n=== National level (noon snapshot) ===")
    print(aggregate(fc, LEVEL_NATIONAL).iloc[[NOON_ROW]])

    print("\n=== With spatial correlation ===")
    hist_df = generate_all(STEG_DISTRICTS, start="2024-05-01", end="2024-05-15")
    corr = build_spatial_correlation(models, hist_df, capacity_lookup, dust_lookup)
    print(aggregate(fc, LEVEL_NATIONAL, corr_matrix=corr).iloc[[NOON_ROW]])

    print("\n=== STEG District level (Sfax districts at noon) ===")
    sd_agg = aggregate(fc, LEVEL_STEG_DISTRICT)
    sfax = sd_agg[sd_agg["steg_district"].str.startswith("SFAX") & (sd_agg[TIMESTAMP_COLUMN] == ts)]
    print(sfax)
