"""Canonical structure for importing STEG Prosol dashboard reports.

The source report is a monthly aggregate rooftop-PV dashboard. It reports the
same measures at national, Direction de Distribution, and commercial-district
levels. It does not describe individual rooftop geometry or individual panels.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class ComparisonMetric:
    """A report value with its monthly, annual, and programme baselines."""

    current_month: float
    previous_year_month: float
    current_year_to_date: float
    previous_year_to_date: float
    since_program_start: float
    unit: str
    variance_month_pct: float | None = None
    variance_ytd_pct: float | None = None


@dataclass(frozen=True)
class RooftopInstallationStats:
    """Section 1.1: aggregate rooftop PV programme indicators."""

    installations: ComparisonMetric
    installed_power: ComparisonMetric
    pv_production: ComparisonMetric
    steg_generation_avoided: ComparisonMetric
    grid_energy_injected: ComparisonMetric
    fuel_avoided: ComparisonMetric
    fuel_cost_avoided: ComparisonMetric
    co2_avoided: ComparisonMetric


@dataclass(frozen=True)
class DistributionSnapshot:
    """Sections 3.3 and 4.3: one Direction de Distribution row."""

    direction: str
    installations: ComparisonMetric
    installed_power: ComparisonMetric


@dataclass(frozen=True)
class DistrictSnapshot:
    """Sections 3.4, 4.4, and 7: one commercial-district row."""

    district: str
    direction: str
    installations: ComparisonMetric
    installed_power: ComparisonMetric
    pending_dossiers_ytd: int
    pending_dossiers_since_2018: int
    pending_share_pct: float | None = None


@dataclass(frozen=True)
class InstallationSizeSnapshot:
    """Sections 5.1 and 5.2: rooftop installations grouped by kWc type."""

    system_size_kwc: int
    installation_count: ComparisonMetric
    installed_power: ComparisonMetric


@dataclass(frozen=True)
class CreditSnapshot:
    """Sections 2.1–2.4: financing breakdown for rooftop installations."""

    credit_amount_dt: int | None
    installation_count: ComparisonMetric
    credit_amount_mdt: ComparisonMetric | None = None


@dataclass(frozen=True)
class ProsolReportSnapshot:
    """One immutable monthly report snapshot.

    The report period and emission date are separate: the March 2026 report
    shown in the source files has an emission date of 11 May 2026.
    """

    report_period: date
    emission_date: date
    source_file: str
    national: RooftopInstallationStats
    directions: list[DistributionSnapshot] = field(default_factory=list)
    districts: list[DistrictSnapshot] = field(default_factory=list)
    installation_sizes: list[InstallationSizeSnapshot] = field(default_factory=list)
    credits: list[CreditSnapshot] = field(default_factory=list)

    @property
    def is_rooftop_only(self) -> bool:
        return True


# The report's official hierarchy. Keep this order when displaying/importing
# rows so dashboard tables match the Prosol document.
REPORT_SECTIONS = (
    "installation_statistics",
    "financing",
    "installation_count_history",
    "installed_power_history",
    "installation_size_distribution",
    "pending_dossiers",
)

REPORT_LEVELS = ("national", "direction", "commercial_district")
REPORT_PERIOD_COLUMNS = (
    "current_month",
    "previous_year_month",
    "current_year_to_date",
    "previous_year_to_date",
    "since_program_start",
)
