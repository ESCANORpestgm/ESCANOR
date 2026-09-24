"""Feature derivations shared by the dataset generators.

Only the *dataset-side* encodings live here: the deployed LightGBM model keeps
its own historically-fitted encodings in ``models.features``, and changing them
would invalidate every persisted model artifact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAYS_IN_YEAR = 365.25
HOURS_IN_DAY = 24.0


def decimal_hour(timestamps: pd.Series) -> pd.Series:
    """Decimal hour of day (``13:30`` → ``13.5``)."""
    ts = pd.to_datetime(timestamps)
    return ts.dt.hour + ts.dt.minute / 60.0


def add_cyclic_time_features(frame: pd.DataFrame, timestamp_column: str = "timestamp") -> pd.DataFrame:
    """Add ``hour_sin/hour_cos`` and ``day_of_year_sin/day_of_year_cos``.

    Cyclical encodings let the model see that 23:00 and 00:00 are adjacent, which
    an integer ``hour`` cannot express. Timestamps are interpreted as UTC when no
    zone is present, matching the datasets written by ``data.generate_*``.
    Mutates and returns ``frame``; callers pass a fresh copy.
    """
    ts = pd.to_datetime(frame[timestamp_column], utc=True)
    hour = ts.dt.hour + ts.dt.minute / 60.0
    day_of_year = ts.dt.dayofyear
    frame["hour_sin"] = np.sin(2 * np.pi * hour / HOURS_IN_DAY)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / HOURS_IN_DAY)
    frame["day_of_year_sin"] = np.sin(2 * np.pi * day_of_year / DAYS_IN_YEAR)
    frame["day_of_year_cos"] = np.cos(2 * np.pi * day_of_year / DAYS_IN_YEAR)
    return frame


__all__ = ["DAYS_IN_YEAR", "HOURS_IN_DAY", "add_cyclic_time_features", "decimal_hour"]
