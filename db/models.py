"""ORM models for ESCANOR's relational data.

``metering_observations`` and ``retraining_events`` reproduce the schema already
declared in the legacy ``results/prosol/presol.db`` — created but never wired to
any code. Keeping the column names, the ``CHECK`` constraints and the ``UNIQUE``
contract means this is the completion of an existing design rather than a
competing one.

The ``prosol_*`` tables absorb the Prosol snapshot history that used to live in
its own second SQLite file, so one store holds all relational data.

Timestamps are stored as ISO-8601 strings, as everywhere else in the platform
(``datetime.now(timezone.utc).isoformat()``). SQLite has no native datetime
type, so a ``DateTime`` column would behave differently per engine while buying
nothing for the query patterns here, which filter by string range or by day.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata root for every ESCANOR table."""


class MeteringObservation(Base):
    """One governorate-level production reading, optionally paired with the P50
    forecast that was in force for it — the actual/forecast pairing that drift
    detection and bias correction consume."""

    __tablename__ = "metering_observations"
    __table_args__ = (
        CheckConstraint("actual_mw >= 0", name="ck_metering_actual_non_negative"),
        CheckConstraint(
            "forecast_p50_mw IS NULL OR forecast_p50_mw >= 0",
            name="ck_metering_forecast_non_negative",
        ),
        # Makes a repeated push idempotent: the same (timestamp, governorate)
        # can be replayed by a recovering metering feed without duplicating rows.
        UniqueConstraint("timestamp", "governorate", name="uq_metering_timestamp_governorate"),
        Index("idx_metering_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(32))
    governorate: Mapped[str] = mapped_column(String(64))
    actual_mw: Mapped[float] = mapped_column(Float)
    forecast_p50_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    received_at: Mapped[str] = mapped_column(String(32))

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"<MeteringObservation {self.timestamp} {self.governorate} "
            f"actual={self.actual_mw}>"
        )


class RetrainingEvent(Base):
    """One retrain decision.

    ``payload`` holds the whole result dict as JSON because the entry points that
    produce it (API upload, synthetic retrain, ``python -m models.retrain``)
    carry different key sets and nested values — the same reason the CSV log
    JSON-encodes nested fields. The flat columns stay for querying, the payload
    keeps the audit trail lossless.
    """

    __tablename__ = "retraining_events"
    __table_args__ = (Index("idx_retraining_timestamp", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64), default="")
    retrained: Mapped[bool] = mapped_column(default=False)
    candidate_promoted: Mapped[bool] = mapped_column(default=False)
    payload: Mapped[str] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<RetrainingEvent {self.timestamp} source={self.source!r}>"


# ── Prosol official-snapshot history ─────────────────────────────────────────

class ProsolReport(Base):
    """One immutable official Prosol report, keyed by a content address.

    ``snapshot_json`` is the whole payload, which is what the API actually serves:
    ``get_report`` re-reads it and grafts on an import stamp. The child tables
    mirror the arrays inside it for SQL-side analytics and currently have no
    readers, so the parent row is the authoritative copy.
    """

    __tablename__ = "prosol_reports"
    __table_args__ = (
        Index("idx_prosol_reports_period", "report_period", "emission_date"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_period: Mapped[str] = mapped_column(String(64))
    emission_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_file: Mapped[str] = mapped_column(String(256))
    imported_at: Mapped[str] = mapped_column(String(32))
    # Matches the legacy DDL default; import_snapshot always supplies it explicitly.
    scope: Mapped[str] = mapped_column(String(32), default="rooftop_pv")
    # Boolean rather than the legacy INTEGER: the store may be Postgres. The
    # importer re-reads it as 0/1 so the JSON wire format does not change.
    reconciliation_passed: Mapped[bool] = mapped_column()
    snapshot_json: Mapped[str] = mapped_column(Text)


class _ProsolSnapshotRow:
    """Composite key shared by every Prosol child table.

    ``row_order`` preserves the position in the source JSON array, which keeps a
    re-import of the same file byte-identical and therefore idempotent against
    the content-addressed parent key.
    """

    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("prosol_reports.snapshot_id"), primary_key=True
    )
    row_order: Mapped[int] = mapped_column(Integer, primary_key=True)


class ProsolNationalMetric(_ProsolSnapshotRow, Base):
    """One row of the national metrics table of a snapshot."""

    __tablename__ = "prosol_national_metrics"

    name: Mapped[str] = mapped_column(String(128), default="")
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_year_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance_month_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_year_to_date: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_year_to_date: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance_ytd_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    since_program_start: Mapped[float | None] = mapped_column(Float, nullable=True)


class _ProsolPayloadRow(_ProsolSnapshotRow):
    """Child tables that store their row verbatim, as the legacy DDL did."""

    payload_json: Mapped[str] = mapped_column(Text)


class ProsolDirection(_ProsolPayloadRow, Base):
    """One direction row of a snapshot."""

    __tablename__ = "prosol_directions"


class ProsolDistrict(_ProsolPayloadRow, Base):
    """One district row of a snapshot."""

    __tablename__ = "prosol_districts"


class ProsolInstallationSize(_ProsolPayloadRow, Base):
    """One installation-size-band row of a snapshot."""

    __tablename__ = "prosol_installation_sizes"


class ProsolPendingDossier(_ProsolPayloadRow, Base):
    """One pending-dossier row of a snapshot."""

    __tablename__ = "prosol_pending_dossiers"
