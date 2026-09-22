"""
Compatibility shim redirecting legacy imports to data.steg_districts.
STEG commercial districts (50 districts across 7 Directions) completely replaces
the administrative governorates dataset.
"""

from data.steg_districts import (
    STEG_DISTRICTS,
    DISTRICT_BY_NAME,
    DIRECTIONS,
    DISTRICT_CAPACITY_LOOKUP,
    DISTRICT_DUST_LOOKUP,
    SATURATION_THRESHOLDS_MW,
    AVG_UNIT_KWC,
    GOVERNORATES,
    GOVERNORATE_BY_NAME,
    DISTRICTS,
    CAPACITY_LOOKUP,
    DUST_LOOKUP,
    Governorate,
    StegDistrict,
    calculate_displacement,
    direction_summary,
    project_capacity,
)

__all__ = [
    "STEG_DISTRICTS",
    "DISTRICT_BY_NAME",
    "DIRECTIONS",
    "DISTRICT_CAPACITY_LOOKUP",
    "DISTRICT_DUST_LOOKUP",
    "SATURATION_THRESHOLDS_MW",
    "AVG_UNIT_KWC",
    "GOVERNORATES",
    "GOVERNORATE_BY_NAME",
    "DISTRICTS",
    "CAPACITY_LOOKUP",
    "DUST_LOOKUP",
    "Governorate",
    "StegDistrict",
    "calculate_displacement",
    "direction_summary",
    "project_capacity",
]
