# ESCANOR PV Forecast Platform — Project Task List

This checklist follows the official STEG Prosol monthly report structure and keeps the forecasting scope limited to aggregated rooftop PV installations.

## Completed

### Frontend

- [x] Reorganize dashboard assets under `dashboard/assets/`.
- [x] Split the frontend JavaScript into core and page-specific modules.
- [x] Fix the mobile Regional Analysis layout.
- [x] Add i18next language switching for English, French, and Arabic.
- [x] Add Arabic RTL layout support.
- [x] Fix the Prosol HTML report link to use the FastAPI URL.

### Backend structure

- [x] Split the monolithic `api/main.py` into domain routers and shared core services.
- [x] Preserve existing forecast, registry, metering, diagnostics, report, evaluation, and model-registry paths.

### Prosol report structure

- [x] Extract the March 2026 Prosol reports.
- [x] Document the official report hierarchy.
- [x] Separate PV data from CES solar-water-heater data.
- [x] Define the canonical report schema.
- [x] Import national PV metrics.
- [x] Import the 7 Directions de Distribution.
- [x] Import the 50 commercial districts.
- [x] Import the 1–12 kWc installation-size classes.
- [x] Import pending PV dossiers by district.
- [x] Preserve monthly, previous-year, YTD, previous-YTD, and since-2011 values.
- [x] Add district-to-national reconciliation checks.
- [x] Generate `reports/generated/prosol_mars_2026.json`.
- [x] Expose the normalized snapshot through `/reports/prosol/snapshot`.

## Priority 1 — Make report data authoritative

- [x] Update `reports/prosol_report_generator.py` to load the normalized JSON snapshot instead of hardcoded March 2026 values.
- [x] Add snapshot-path/report-period support to the HTML and JSON report generator flow.
- [x] Add a generated report registry containing source filename, report period, emission date, and import status.
- [x] Import both attached March 2026 report versions and compare them.
- [x] Validate the expected 50 district and 50 pending-dossier rows during import.
- [—] Detect renamed districts and preserve source names — deferred by scope.
- [x] Export normalized CSV files for national, Direction, district, size, and pending-dossier tables.
- [—] Add automated tests for report counts and reconciliation totals — deferred by scope.


## Priority 4 — Add actual rooftop production data

- [x] Define the actual measurement format.
- [x] Support CSV measurement imports.
- [x] Store raw measurements without overwriting them through immutable validated snapshots.
- [x] Add data-quality flags.
- [x] Detect duplicate timestamps.
- [x] Detect missing intervals.
- [x] Detect negative or impossible production values.
- [ ] Mark estimated or imputed values.
- [x] Aggregate measurements by district and Direction when source columns are supplied.

Expected measurement fields:

```text
timestamp_utc
location_id
power_kw
energy_kwh
installed_capacity_kwp
source
quality_status
```

## Priority 5 — Save and evaluate forecasts

- [x] Create file-based immutable forecast runs and values until the database phase.
- [x] Store forecast creation time separately from target time.
- [x] Store the Prosol capacity snapshot, model version, and weather source metadata.
- [x] Match forecast values with later actual measurements.
- [x] Calculate MAE.
- [x] Calculate RMSE and nRMSE.
- [x] Calculate forecast bias.
- [x] Calculate P10/P90 coverage.
- [x] Calculate interval width.
- [x] Add forecast-versus-actual charts.
- [x] Add nowcast, short-term, day-ahead, and extended horizon metrics.
- [x] Add optional Direction/district evaluation summaries.
- [x] Add saved evaluation history API endpoints.
- [x] Enforce kW-only forecast evaluation schema.

## Priority 6 — Model versioning and retraining

- [x] Create file-based `model_versions` registry.
- [x] Create file-based `training_runs` registry.
- [x] Record training data start and end dates.
- [x] Record feature and schema versions.
- [x] Store validation metrics for every candidate model.
- [x] Keep the current production model immutable until promotion.
- [x] Add a canonical validated-rooftop-to-model training adapter.
- [x] Train candidate models using validated rooftop measurements.
- [x] Promote a candidate only when it beats the production model.
- [x] Add drift-triggered candidate retraining.
- [x] Add manual retraining trigger UI/API (authorization deferred with security scope).

## Database and Prosol history UI

Implemented after the file-based report and forecast workflow. Alembic migrations remain deferred for now.

### Database-backed report history

- [x] Add a SQLite database for local development.
- [—] Add database migrations with Alembic — deferred while using the file-based local workflow.
- [x] Create `prosol_reports` and normalized report metric tables.
- [x] Preserve immutable monthly snapshots in the database.
- [x] Add report history API endpoints.

### Prosol history frontend

- [x] Add a Prosol History page.
- [x] Add a report-period selector.
- [x] Add national, Direction, district, pending-dossier, and size charts/tables.
- [x] Show source, emission date, and reconciliation status.

## Deferred — Security, operations, and quality-of-life work

These items are intentionally out of the current scope. Revisit them after the
core report-history and forecast-learning workflow is complete:

- Authentication and authorization
- Role-based access
- Audit history
- Backups and deployment hardening
- Structured logging and monitoring
- Scheduled imports
- Additional UI polish and convenience features

## Active scope rules

- [ ] Keep the forecasting scope limited to rooftop PV.
- [ ] Do not include CES metrics in PV training data.
- [ ] Do not model individual rooftops unless source data requires it.
- [ ] Treat Prosol reports as monthly capacity and installation snapshots.
- [x] Add a reproducible SolNet-style synthetic rooftop dataset generator.
- [x] Use the SolNet-style aggregate dataset in the historical dashboard pipeline.
- [ ] Use actual hourly or 15-minute production data for production model training.
- [ ] Never overwrite historical forecasts, report snapshots, or raw measurements.
