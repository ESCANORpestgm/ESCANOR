"""Hardcoded March-2026 Prosol figures used only until a snapshot is imported.

``reports.prosol_report_importer`` turns an official PDF into a JSON snapshot and
``prosol_report_generator`` prefers that snapshot. This module is the safety net
that keeps the dashboard and the print report working on a fresh checkout where
no snapshot has been imported yet; the values are transcribed from the
"Tableau de Bord Programme Prosol" of March 2026 and must never be edited to
express anything other than that report.
"""

from __future__ import annotations

import copy
from typing import Any

# The fallback *is* the March 2026 report, whatever month label the caller asks
# for; only ``report_period`` follows the caller's request. The same constant is
# the default label every report caller falls back on.
DEFAULT_MONTH_LABEL = "Mars 2026"
FALLBACK_EMISSION_DATE = "11/05/2026"
DIRECTION_TUTELLE = "Direction Centrale de la Distribution — Direction Commerciale et Marketing"

FALLBACK_SUMMARY: dict[str, Any] = {
    "report_period": DEFAULT_MONTH_LABEL,
    "emission_date": FALLBACK_EMISSION_DATE,
    "direction_tutelle": DIRECTION_TUTELLE,
    "recap_executions": {
        "period": DEFAULT_MONTH_LABEL,
        "executes_current": 9340,
        "executes_prev": 6225,
        "executes_var_pct": 50.0,
        "pending_current": 3171,
        "pending_prev": 1466,
        "pending_var_pct": 116.3,
        "completion_rate_pct": 74.7,
    },
    "indicators": [
        {
            "id": 1,
            "label": "Nombre d’installations PV",
            "unit": "sites",
            "month_current": 3211,
            "month_prev": 3642,
            "month_var": -12.0,
            "ytd_current": 9340,
            "ytd_prev": 6225,
            "ytd_var": 50.0,
            "since_2011": 144979,
        },
        {
            "id": 2,
            "label": "Puissance installée (MW)",
            "unit": "MW",
            "month_current": 11.8,
            "month_prev": 12.5,
            "month_var": -6.0,
            "ytd_current": 33.8,
            "ytd_prev": 22.4,
            "ytd_var": 51.0,
            "since_2011": 456.0,
        },
        {
            "id": 3,
            "label": "Production des IPV (GWh)",
            "unit": "GWh",
            "month_current": 62.0,
            "month_prev": 43.4,
            "month_var": 43.0,
            "ytd_current": 175.2,
            "ytd_prev": 122.1,
            "ytd_var": 43.0,
            "since_2011": 2358.3,
        },
        {
            "id": 4,
            "label": "Production STEG Évitée (GWh)",
            "unit": "GWh",
            "month_current": 74.4,
            "month_prev": 52.1,
            "month_var": 43.0,
            "ytd_current": 210.2,
            "ytd_prev": 146.6,
            "ytd_var": 43.0,
            "since_2011": 2830.0,
        },
        {
            "id": 5,
            "label": "Énergie Injectée dans le réseau (GWh)",
            "unit": "GWh",
            "month_current": 35.8,
            "month_prev": 22.4,
            "month_var": 60.0,
            "ytd_current": 113.9,
            "ytd_prev": 77.5,
            "ytd_var": 47.0,
            "since_2011": 1511.1,
        },
        {
            "id": 6,
            "label": "Combustible évité (ktep)",
            "unit": "ktep",
            "month_current": 14.5,
            "month_prev": 9.9,
            "month_var": 46.0,
            "ytd_current": 40.9,
            "ytd_prev": 27.8,
            "ytd_var": 47.0,
            "since_2011": 574.8,
        },
        {
            "id": 7,
            "label": "Coût du combustible évité (MDT)",
            "unit": "MDT",
            "month_current": 16.8,
            "month_prev": 13.2,
            "month_var": 28.0,
            "ytd_current": 47.6,
            "ytd_prev": 37.9,
            "ytd_var": 26.0,
            "since_2011": 635.2,
        },
        {
            "id": 8,
            "label": "Émissions de CO2 évitées (ktonne)",
            "unit": "ktonne",
            "month_current": 34.0,
            "month_prev": 23.3,
            "month_var": 46.0,
            "ytd_current": 96.2,
            "ytd_prev": 65.3,
            "ytd_var": 47.0,
            "since_2011": 1350.1,
        },
    ],
    "top_five_districts": [
        {"name": "BEN GUERDENE", "rate_2026": 98.2, "rate_2025": 97.5},
        {"name": "JENDOUBA", "rate_2026": 96.1, "rate_2025": 97.6},
        {"name": "MEDNINE", "rate_2026": 93.9, "rate_2025": 97.5},
        {"name": "BEJA", "rate_2026": 90.8, "rate_2025": 96.6},
        {"name": "MAHRES", "rate_2026": 90.8, "rate_2025": 96.4},
    ],
    "last_five_districts": [
        {"name": "TABARKA", "rate_2026": 0.0, "rate_2025": 55.6},
        {"name": "GABES NORD", "rate_2026": 47.8, "rate_2025": 55.6},
        {"name": "KEBILI", "rate_2026": 49.7, "rate_2025": 56.4},
        {"name": "TOZEUR", "rate_2026": 53.1, "rate_2025": 56.7},
        {"name": "HAMMAMET", "rate_2026": 54.6, "rate_2025": 59.5},
    ],
}


def build_fallback_summary(report_period: str) -> dict[str, Any]:
    """A private copy of the March-2026 figures labelled ``report_period``.

    The caller mutates the result (live installation updates are overlaid on it),
    so the shared constant is deep-copied rather than handed out directly.
    """
    summary = copy.deepcopy(FALLBACK_SUMMARY)
    summary["report_period"] = report_period
    return summary
