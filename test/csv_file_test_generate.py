"""Generate a compliant rooftop measurement CSV for the retrain upload endpoint.

The production model is trained on *district-aggregated* MW from the STEG
registry, so an upload has to match that contract:

  * ``district``  -> canonical STEG district names (keys of DISTRICT_CAPACITY_LOOKUP)
  * ``power_kw``  -> the district/direction sub-fleet output in kW (up to the
                     district's installed capacity), NOT a single micro-inverter
  * a continuous 15-minute time series long enough for temporal cross-validation
  * power derived from irradiance so there is no "night with production"

Run: ``python test.py``  -> writes ``measurement_data.csv``.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from data.steg_districts import STEG_DISTRICTS

np.random.seed(42)

# ── Configuration ────────────────────────────────────────────────────────────
START = datetime(2026, 1, 1)
DAYS = 60
INTERVAL_MIN = 15
SITES_PER_DISTRICT = 3          # split each district fleet across a few sub-plants
TEMP_COEFFICIENT = 0.004        # fractional power loss per °C above 25 °C
CLOUD_ATTENUATION = 0.6         # fraction of irradiance lost at 100% cloud

# Pick a handful of real STEG districts (name must exist in the capacity registry).
CHOSEN_DISTRICTS = ["TUNIS VILLE", "SFAX VILLE", "SFAX NORD", "KRAM", "TATAOUINE", "GAFSA"]

DISTRICT_META = {d.name: d for d in STEG_DISTRICTS}
missing = [name for name in CHOSEN_DISTRICTS if name not in DISTRICT_META]
if missing:
    raise SystemExit(f"Chosen districts not in STEG registry: {missing}")


def clear_sky_ghi(time_of_day: float, day_of_year: int) -> float:
    """Bell-shaped daytime irradiance (W/m²) with a mild seasonal amplitude."""
    if not 6.0 <= time_of_day <= 18.0:
        return 0.0
    diurnal = np.sin(np.pi * (time_of_day - 6.0) / 12.0)
    seasonal = 0.75 + 0.25 * np.sin(2 * np.pi * (day_of_year - 100) / 365.0)
    return float(max(0.0, 1000.0 * diurnal * seasonal))


def main() -> None:
    shares = np.linspace(0.5, 1.0, SITES_PER_DISTRICT)
    shares = shares / shares.sum()

    steps = DAYS * 24 * 60 // INTERVAL_MIN
    timestamps = [START + timedelta(minutes=INTERVAL_MIN * i) for i in range(steps)]

    rows = []
    for ts in timestamps:
        time_of_day = ts.hour + ts.minute / 60.0
        day_of_year = ts.timetuple().tm_yday
        cloud = float(np.clip(np.random.normal(25, 20), 0, 100))
        temp = float(15 + 12 * np.sin(2 * np.pi * (day_of_year - 105) / 365.0)
                     + 6 * np.sin(np.pi * (time_of_day - 6) / 12.0)
                     + np.random.normal(0, 1))
        for name in CHOSEN_DISTRICTS:
            district = DISTRICT_META[name]
            capacity_kwp = district.installed_capacity_mwc * 1000.0
            ghi = clear_sky_ghi(time_of_day, day_of_year) * (1 - CLOUD_ATTENUATION * cloud / 100.0)
            ghi = max(0.0, ghi + np.random.normal(0, 15))
            if ghi <= 1.0:
                district_power_kw = 0.0
            else:
                temp_derate = max(0.7, 1 - TEMP_COEFFICIENT * max(0.0, temp - 25.0))
                performance_ratio = (1 - district.dust_loss_pct) * temp_derate
                district_power_kw = capacity_kwp * (ghi / 1000.0) * performance_ratio
                district_power_kw = float(min(district_power_kw, capacity_kwp))
            for site_index in range(SITES_PER_DISTRICT):
                rows.append({
                    "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "location_id": f"{name.replace(' ', '_')}_{site_index + 1:02d}",
                    "power_kw": round(district_power_kw * shares[site_index], 2),
                    "district": name,
                    "direction": district.direction,
                    "ghi_wm2": round(ghi, 1),
                    "temp_c": round(temp, 1),
                    "cloud_cover_pct": round(cloud, 1),
                    "quality_status": "valid",
                })

    frame = pd.DataFrame(rows)
    frame.to_csv("measurement_data.csv", index=False)
    print(f"Generated {len(frame):,} rows -> measurement_data.csv")
    print("Districts:", ", ".join(CHOSEN_DISTRICTS))
    print("Peak district-aggregated production (MW):")
    agg = frame.groupby(["district", "timestamp_utc"], as_index=False)["power_kw"].sum()
    agg["mw"] = agg["power_kw"] / 1000.0
    print(agg.groupby("district")["mw"].max().round(2).to_string())


if __name__ == "__main__":
    main()
