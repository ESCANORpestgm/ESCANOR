"""Tunisian PV climatology and geometry constants shared by data and model layers.

These are physical/site assumptions of the rooftop-PV programme, not per-rooftop
measurements: the platform models aggregate STEG district fleets, so every
district in a climate zone is assumed to share the same mounting geometry.
"""

from __future__ import annotations

# Representative latitude of the Tunisian load centre (used by the solar-position
# feature engineering and the synthetic clear-sky model).
REFERENCE_LATITUDE_DEG = 35.0

# Standard rooftop PV geometric assumptions in Tunisia (STEG Prosol programme).
DEFAULT_PV_ORIENTATION = {
    "tilt_degrees": 20.0,
    "tilt_range": (15.0, 30.0),
    "azimuth_degrees": 180.0,          # south-facing
    "azimuth_dispersion_std": 22.5,
    "temp_coefficient_pct_per_c": -0.38,
    "inverter_dc_ac_ratio": 1.15,
}

# Balance-of-system losses applied to every aggregate district fleet.
SYSTEM_LOSS_PCT = 14.0                 # inverter, cabling, availability
TEMP_COEFFICIENT_PER_C = -0.0038       # power derating above 25 °C cell temp
NOCT_CELL_TEMP_RISE = 0.03             # °C cell-temp rise per W/m² of GHI

# Theoretical clear-sky GHI at the reference latitude (W/m²), used for the
# clear-sky-index feature: ratio of measured to ideal irradiance.
CLEAR_SKY_GHI_WM2 = 1050.0

# ── Solar geometry (simplified Cooper declination model) ─────────────────────
# Amplitude of the solar declination over the year, in degrees.
SOLAR_DECLINATION_AMPLITUDE_DEG = 23.44
# Day of year of the March equinox, i.e. the zero crossing of the declination.
EQUINOX_ANCHOR_DAY_OF_YEAR = 81
# Earth rotation expressed as hour angle per clock hour.
SOLAR_HOUR_ANGLE_DEG_PER_HOUR = 15.0
# Local apparent solar noon on the deployment clock.
SOLAR_NOON_CLOCK_HOUR = 12.0
# Standard-test-condition cell temperature the derating is measured against.
STC_REFERENCE_CELL_TEMP_C = 25.0

# Sunrise/sunset guard-rails for the "physically impossible" data-quality gate:
# no district should report meaningful production in these hours (local time).
NIGHT_START_HOUR = 20
NIGHT_END_HOUR = 5
NIGHT_PRODUCTION_TOLERANCE_MW = 0.5

# 4-class Tunisian climate classification of STEG commercial districts.
# Drives the ``climate_zone_id`` feature so the model generalises spatially
# instead of memorising district names.
CLIMATE_ZONES: dict[str, frozenset[str]] = {
    "coastal_north": frozenset({
        "TUNIS VILLE", "ARIANA", "EZZAHRA", "MOUROUJ", "KRAM", "BARDO",
        "MANNOUBA", "EL MENZAH", "BIZERTE", "MENZEL BOURGUIBA", "NABEUL",
        "MENZEL B-ZELFA", "MENZEL TEMIME", "HAMMAMET", "TABARKA",
        "ZAGHOUAN", "BEJA", "JENDOUBA",
    }),
    "central_coastal": frozenset({
        "SOUSSE", "SOUSSE NORD", "MONASTIR", "MOKNINE", "MAHDIA",
        "ENFIDHA", "SFAX VILLE", "SFAX NORD", "SFAX SUD",
    }),
    "inland_central": frozenset({
        "KAIROUAN", "KAIROUAN NORD", "SIDI-BOUZID", "KASSERINE",
        "SBEITLA", "SILIANA", "KEF", "EL JEM", "MSAKEN",
    }),
    "south": frozenset({
        "GABES", "GABES NORD", "GAFSA", "TOZEUR", "KEBILI",
        "TATAOUINE", "MEDNINE", "BEN GUERDENE", "ZARZIS", "JERBA",
        "MAHRES", "MAKNASSY", "METLAOUI", "JBE NIANA",
    }),
}

# Stable integer encoding of the zones (0 is the default for unknown names,
# matching the largest production cluster around Tunis).
ZONE_IDS: dict[str, int] = {
    "coastal_north": 0,
    "central_coastal": 1,
    "inland_central": 2,
    "south": 3,
}
DEFAULT_ZONE_ID = ZONE_IDS["coastal_north"]

_DISTRICT_TO_ZONE: dict[str, str] = {
    district.upper(): zone for zone, districts in CLIMATE_ZONES.items() for district in districts
}


def district_to_zone(governorate: str) -> str | None:
    """Climate zone name for a district/governorate, or ``None`` when unmapped."""
    return _DISTRICT_TO_ZONE.get(str(governorate).strip().upper())


def climate_zone_id(governorate: str) -> int:
    """Integer climate zone for a district/governorate (unmapped → default)."""
    return ZONE_IDS.get(district_to_zone(governorate) or "", DEFAULT_ZONE_ID)


__all__ = [
    "CLIMATE_ZONES",
    "CLEAR_SKY_GHI_WM2",
    "DEFAULT_PV_ORIENTATION",
    "DEFAULT_ZONE_ID",
    "EQUINOX_ANCHOR_DAY_OF_YEAR",
    "NIGHT_END_HOUR",
    "NIGHT_PRODUCTION_TOLERANCE_MW",
    "NIGHT_START_HOUR",
    "NOCT_CELL_TEMP_RISE",
    "REFERENCE_LATITUDE_DEG",
    "SOLAR_DECLINATION_AMPLITUDE_DEG",
    "SOLAR_HOUR_ANGLE_DEG_PER_HOUR",
    "SOLAR_NOON_CLOCK_HOUR",
    "STC_REFERENCE_CELL_TEMP_C",
    "SYSTEM_LOSS_PCT",
    "TEMP_COEFFICIENT_PER_C",
    "ZONE_IDS",
    "climate_zone_id",
    "district_to_zone",
]
