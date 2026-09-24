"""
STEG Commercial Districts Reference Data.
Derived directly from STEG's official "Tableau de Bord du Programme Prosol" (Mars 2026).

Contains all 50 commercial districts across the 7 Directions de Distribution with:
- Exact geographical coordinates (lat, lon) for spatial map positioning
- Official cumulative installed capacity (MWc) as of Mars 2026
- Pending connection requests ("dossiers en instance") since 2018
- Direction de Distribution affiliation
- District execution rate (taux de réalisation 2026) from STEG Prosol Page 2
- Fuel and energy displacement conversion factors
"""

if __package__ in (None, ""):  # launched as `python <dir>/<file>.py`: add the project root
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from dataclasses import dataclass
from typing import List, Dict

from data.climate import DEFAULT_PV_ORIENTATION  # re-exported for legacy importers

# Official National Aggregates (Mars 2026)
NATIONAL_ROOFTOP_PV_MWC = 456.0
NATIONAL_TOTAL_INSTALLATIONS = 144979
NATIONAL_PENDING_DOSSIERS = 5475

# Average kWc per new residential installation (STEG Prosol Mars 2026 Section 5.1)
# 9,340 units executed in Q1 2026 with 33.8 MWc total => 3.62 kWc/unit
AVG_UNIT_KWC = 3.62

# National Displacement Ratios (Source: STEG Prosol Mars 2026, Section 1.1)
DISPLACEMENT_FACTORS = {
    "grid_loss_avoidance_ratio": 1.2000,    # 1 MWh PV generated avoids 1.200 MWh thermal generation
    "fuel_saved_tep_per_mwh": 0.2437,       # Tonnes oil equivalent saved per MWh PV
    "cost_saved_dt_per_mwh": 269.34,        # Avoided fuel cost in Dinars per MWh PV
    "co2_avoided_tonnes_per_mwh": 0.5725,   # Tonnes of CO2 emissions avoided per MWh PV
    "grid_injection_share": 0.6407,         # Share of generation exported into STEG MV/LV grid
    "self_consumption_share": 0.3593,       # Share self-consumed behind the meter
}

# Saturation thresholds per high-penetration district (MW)
# Above these levels, midday PV output may exceed minimum load -> reverse flow risk
SATURATION_THRESHOLDS_MW = {
    "SFAX NORD":  28.0,
    "SFAX SUD":   26.0,
    "JERBA":      20.0,
    "MOKNINE":    19.0,
    "KRAM":       15.0,
    "ARIANA":     16.5,
    "SFAX VILLE": 17.0,
    "MONASTIR":   14.0,
    "SOUSSE NORD":13.0,
}


@dataclass
class StegDistrict:
    name: str
    direction: str
    governorate: str
    lat: float
    lon: float
    installed_capacity_mwc: float
    pending_dossiers: int
    dust_loss_pct: float
    tilt_deg: float = 20.0
    azimuth_deg: float = 180.0
    execution_rate_pct: float = 75.0   # Taux de réalisation Q1 2026 (STEG Prosol Page 2)

    @property
    def district(self) -> str:
        """Compatibility: expose Direction as .district for aggregation pipeline."""
        return self.direction

    @property
    def pending_connections(self) -> int:
        """Compatibility: alias for pending_dossiers."""
        return self.pending_dossiers


# 50 Commercial Districts — columns: name, direction, governorate, lat, lon, MWc, pending, dust, exec_rate
DISTRICTS_RAW = [
    # Direction TUNIS
    ("TUNIS VILLE",      "TUNIS",      "Tunis",       36.8008, 10.1800,  8.1,  38, 0.020, 81.7),
    ("ARIANA",           "TUNIS",      "Ariana",      36.8625, 10.1956, 19.9, 139, 0.020, 75.8),
    ("EZZAHRA",          "TUNIS",      "Ben Arous",   36.7444, 10.3075, 13.3, 201, 0.020, 72.1),
    ("MOUROUJ",          "TUNIS",      "Ben Arous",   36.7322, 10.2208,  6.8,  91, 0.020, 71.6),
    ("KRAM",             "TUNIS",      "Tunis",       36.8333, 10.3167, 17.8, 276, 0.020, 80.3),
    ("BARDO",            "TUNIS",      "Tunis",       36.8092, 10.1411,  8.1, 245, 0.020, 70.9),
    ("MANNOUBA",         "TUNIS",      "Manouba",     36.8081, 10.0972,  8.0,  49, 0.020, 72.8),
    ("EL MENZAH",        "TUNIS",      "Ariana",      36.8400, 10.1800, 13.7, 103, 0.020, 73.5),

    # Direction NORD
    ("ZAGHOUAN",         "NORD",       "Zaghouan",    36.4028, 10.1425,  3.0, 111, 0.025, 70.3),
    ("BIZERTE",          "NORD",       "Bizerte",     37.2744,  9.8739, 10.3,  49, 0.020, 87.5),
    ("MENZEL BOURGUIBA", "NORD",       "Bizerte",     37.1536,  9.7858,  2.2,  12, 0.020, 63.9),
    ("NABEUL",           "NORD",       "Nabeul",      36.4561, 10.7376, 13.5, 395, 0.020, 83.2),
    ("MENZEL B-ZELFA",   "NORD",       "Nabeul",      36.6833, 10.5833,  7.9, 118, 0.020, 69.7),
    ("MENZEL TEMIME",    "NORD",       "Nabeul",      36.7833, 11.0000,  9.2, 110, 0.020, 68.9),
    ("HAMMAMET",         "NORD",       "Nabeul",      36.4000, 10.6167,  7.5, 271, 0.020, 54.6),

    # Direction NORD OUEST
    ("BEJA",             "NORD OUEST", "Beja",        36.7256,  9.1817, 10.8,  21, 0.025, 90.8),
    ("JENDOUBA",         "NORD OUEST", "Jendouba",    36.5011,  8.7803,  3.1,   6, 0.025, 96.1),
    ("KEF",              "NORD OUEST", "Le Kef",      36.1826,  8.7148,  3.8,  31, 0.030, 75.0),
    ("SILIANA",          "NORD OUEST", "Siliana",     36.0844,  9.3708,  1.7,  55, 0.030, 88.3),
    ("TABARKA",          "NORD OUEST", "Jendouba",    36.9544,  8.7581,  1.0,   3, 0.020,  0.0),

    # Direction CENTRE
    ("SOUSSE",           "CENTRE",     "Sousse",      35.8256, 10.6369, 12.5,  47, 0.020, 79.8),
    ("SOUSSE NORD",      "CENTRE",     "Sousse",      35.8900, 10.5800, 15.8, 129, 0.020, 74.9),
    ("MONASTIR",         "CENTRE",     "Monastir",    35.7643, 10.8113, 16.5, 168, 0.020, 86.4),
    ("MOKNINE",          "CENTRE",     "Monastir",    35.6267, 10.9039, 22.4, 245, 0.020, 78.6),
    ("MAHDIA",           "CENTRE",     "Mahdia",      35.5047, 11.0622, 12.4,  79, 0.020, 78.1),
    ("KAIROUAN",         "CENTRE",     "Kairouan",    35.6781, 10.0963,  5.3,  98, 0.035, 84.9),
    ("KAIROUAN NORD",    "CENTRE",     "Kairouan",    35.7200, 10.0700,  2.9,  16, 0.035, 66.8),
    ("EL JEM",           "CENTRE",     "Mahdia",      35.3000, 10.7167,  4.7, 109, 0.025, 68.2),
    ("MSAKEN",           "CENTRE",     "Sousse",      35.7333, 10.5833,  7.0,  64, 0.020, 67.5),
    ("ENFIDHA",          "CENTRE",     "Sousse",      36.1333, 10.3833,  1.9,  33, 0.020, 64.7),

    # Direction SFAX
    ("SFAX VILLE",       "SFAX",       "Sfax",        34.7406, 10.7603, 20.1, 197, 0.025, 85.6),
    ("JBENIANA",         "SFAX",       "Sfax",        35.0333, 10.9167,  6.5,  72, 0.025, 65.2),
    ("SFAX NORD",        "SFAX",       "Sfax",        34.8000, 10.7500, 32.4, 253, 0.025, 82.5),
    ("MAHRES",           "SFAX",       "Sfax",        34.5333, 10.5000,  9.8,  43, 0.025, 90.8),
    ("SFAX SUD",         "SFAX",       "Sfax",        34.6800, 10.7200, 30.2, 271, 0.025, 74.2),

    # Direction SUD OUEST
    ("GAFSA",            "SUD OUEST",  "Gafsa",       34.4250,  8.7842,  3.7, 107, 0.045, 77.5),
    ("METLAOUI",         "SUD OUEST",  "Gafsa",       34.3208,  8.4017,  0.7,  11, 0.045, 58.8),
    ("TOZEUR",           "SUD OUEST",  "Tozeur",      33.9197,  8.1335,  4.6,  50, 0.055, 53.1),
    ("MAKNASSY",         "SUD OUEST",  "Sidi Bouzid", 34.9083,  9.6139,  0.6,  11, 0.040, 61.4),
    ("SIDI-BOUZID",      "SUD OUEST",  "Sidi Bouzid", 35.0382,  9.4849,  3.2,  35, 0.040, 62.8),
    ("KASSERINE",        "SUD OUEST",  "Kasserine",   35.1676,  8.8365,  1.2,   6, 0.035, 60.7),
    ("SBEITLA",          "SUD OUEST",  "Kasserine",   35.2333,  9.1167,  0.4,  14, 0.035, 59.3),
    ("KEBILI",           "SUD OUEST",  "Kebili",      33.7044,  8.9690,  9.3, 210, 0.055, 49.7),

    # Direction SUD
    ("GABES",            "SUD",        "Gabes",       33.8815, 10.0982,  7.4, 167, 0.035, 76.4),
    ("GABES NORD",       "SUD",        "Gabes",       33.9300, 10.0600,  5.0, 193, 0.035, 47.8),
    ("MEDNINE",          "SUD",        "Medenine",    33.3399, 10.4956,  8.3,  16, 0.045, 93.9),
    ("ZARZIS",           "SUD",        "Medenine",    33.5044, 11.1122,  7.7, 105, 0.035, 57.9),
    ("JERBA",            "SUD",        "Medenine",    33.8750, 10.8575, 23.4, 319, 0.030, 57.2),
    ("TATAOUINE",        "SUD",        "Tataouine",   32.9297, 10.4518,  6.9,  65, 0.055, 56.4),
    ("BEN GUERDENE",     "SUD",        "Medenine",    33.1389, 11.2167,  3.2,  18, 0.050, 98.2),
]

STEG_DISTRICTS: List[StegDistrict] = [
    StegDistrict(
        name=r[0], direction=r[1], governorate=r[2],
        lat=r[3], lon=r[4],
        installed_capacity_mwc=r[5], pending_dossiers=r[6],
        dust_loss_pct=r[7], execution_rate_pct=r[8],
    )
    for r in DISTRICTS_RAW
]

DISTRICT_BY_NAME: Dict[str, StegDistrict] = {d.name: d for d in STEG_DISTRICTS}

DIRECTIONS: List[str] = sorted(set(d.direction for d in STEG_DISTRICTS))

# Lookup dicts used by the forecast/aggregation pipeline
DISTRICT_CAPACITY_LOOKUP: Dict[str, float] = {d.name: d.installed_capacity_mwc for d in STEG_DISTRICTS}
DISTRICT_DUST_LOOKUP: Dict[str, float] = {d.name: d.dust_loss_pct for d in STEG_DISTRICTS}

# Backward-compatibility aliases (replaces legacy governorates.py)
GOVERNORATES = STEG_DISTRICTS
GOVERNORATE_BY_NAME = DISTRICT_BY_NAME
DISTRICTS = DIRECTIONS
CAPACITY_LOOKUP = DISTRICT_CAPACITY_LOOKUP
DUST_LOOKUP = DISTRICT_DUST_LOOKUP
Governorate = StegDistrict


def districts_by_direction(direction: str) -> List[StegDistrict]:
    return [d for d in STEG_DISTRICTS if d.direction == direction]


def direction_summary() -> Dict[str, Dict]:
    summary = {}
    for d in DIRECTIONS:
        items = districts_by_direction(d)
        cap = sum(x.installed_capacity_mwc for x in items)
        pending = sum(x.pending_dossiers for x in items)
        summary[d] = {
            "districts_count": len(items),
            "total_capacity_mwc": round(cap, 2),
            "pending_dossiers": pending,
            "share_pct": round((cap / NATIONAL_ROOFTOP_PV_MWC) * 100, 1),
        }
    return summary


def calculate_displacement(mwh_generated: float) -> Dict[str, float]:
    """
    Calculate multi-vector displacement for a given MWh of rooftop PV generation
    based on STEG Prosol empirical ratios (Mars 2026, Section 1.1).
    """
    f = DISPLACEMENT_FACTORS
    mwh_avoided = mwh_generated * f["grid_loss_avoidance_ratio"]
    return {
        "mwh_gross_generated":     round(mwh_generated, 2),
        "mwh_injected_to_grid":    round(mwh_generated * f["grid_injection_share"], 2),
        "mwh_self_consumed":       round(mwh_generated * f["self_consumption_share"], 2),
        "steg_thermal_mwh_avoided": round(mwh_avoided, 2),
        "fuel_saved_tep":          round(mwh_generated * f["fuel_saved_tep_per_mwh"], 2),
        "cost_saved_dt":           round(mwh_generated * f["cost_saved_dt_per_mwh"], 2),
        "co2_avoided_tonnes":      round(mwh_generated * f["co2_avoided_tonnes_per_mwh"], 2),
    }


def project_capacity(district: StegDistrict, days: int = 90) -> float:
    """
    Project installed capacity `days` in the future using the backlog pipeline:
    C(t+Δt) = C(t) + N_pending × avg_kWc/1000 × exec_rate × (Δt/90 days)
    """
    added_mwc = (
        district.pending_dossiers
        * AVG_UNIT_KWC / 1000.0
        * (district.execution_rate_pct / 100.0)
        * (days / 90.0)
    )
    return round(district.installed_capacity_mwc + added_mwc, 3)


if __name__ == "__main__":
    print(f"Loaded {len(STEG_DISTRICTS)} STEG Commercial Districts across {len(DIRECTIONS)} Directions.")
    print(f"Total Model Capacity: {sum(d.installed_capacity_mwc for d in STEG_DISTRICTS):.1f} MWc (Report: {NATIONAL_ROOFTOP_PV_MWC} MWc)")
    print(f"Total Pending Dossiers: {sum(d.pending_dossiers for d in STEG_DISTRICTS)} (Report: {NATIONAL_PENDING_DOSSIERS})")
    print("\nSummary by Direction de Distribution:")
    for dir_name, s in direction_summary().items():
        print(f" - {dir_name:12s}: {s['total_capacity_mwc']:5.1f} MWc ({s['share_pct']:4.1f}%) | {s['pending_dossiers']:4d} pending across {s['districts_count']} districts")
    print("\nSaturation Risk Districts:")
    for d in STEG_DISTRICTS:
        if d.name in SATURATION_THRESHOLDS_MW:
            print(f" - {d.name:18s}: {d.installed_capacity_mwc:5.1f} MWc, threshold={SATURATION_THRESHOLDS_MW[d.name]:.0f} MW")
    print("\nCapacity Pipeline (30d / 90d projections):")
    for d in sorted(STEG_DISTRICTS, key=lambda x: x.pending_dossiers, reverse=True)[:8]:
        p30 = project_capacity(d, 30)
        p90 = project_capacity(d, 90)
        print(f" - {d.name:18s}: {d.installed_capacity_mwc:5.1f} → {p30:5.1f} (30d) → {p90:5.1f} MWc (90d) | exec={d.execution_rate_pct:.0f}%")
