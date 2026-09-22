"""Build district-level new rooftop-PV installation exports from Prosol snapshots."""

from __future__ import annotations

import csv
import io
from typing import Any

from data.steg_districts import DISTRICT_BY_NAME


def new_installations_by_district(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return monthly and YTD new installations for every district in a snapshot.

    The values come from the official Prosol district installation rows. This is
    a derived export; it does not create individual rooftop records.
    """
    rows = []
    for district in report.get("districts", []):
        district_name = str(district.get("name", "")).upper()
        steg_district = DISTRICT_BY_NAME.get(district_name)
        installed_power = district.get("installed_power", {})
        rows.append({
            "report_period": report.get("report_period"),
            "emission_date": report.get("emission_date"),
            "district": district.get("name"),
            "direction": steg_district.direction if steg_district else None,
            "new_installations_month": district.get("current_month", 0),
            "new_installations_ytd": district.get("current_year_to_date", 0),
            "installations_since_program_start": district.get("since_program_start", 0),
            "new_capacity_mw_month": installed_power.get("current_month"),
            "new_capacity_mw_ytd": installed_power.get("current_year_to_date"),
            "source_file": report.get("source_file"),
            "source": "official_prosol_snapshot",
        })
    return rows


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize installation rows with a stable CSV column order."""
    fields = [
        "report_period", "emission_date", "district", "direction",
        "new_installations_month", "new_installations_ytd",
        "live_new_installations", "current_new_installations_ytd",
        "installations_since_program_start", "new_capacity_mw_month",
        "new_capacity_mw_ytd", "source_file", "source",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
