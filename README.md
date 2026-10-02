# ESCANOR — National Rooftop PV Forecast Platform

**ESCANOR × STEG** — A platform for forecasting Tunisia's aggregated rooftop solar production from intra-day to D+3, across STEG districts, Directions, governorates, and national level.

Built for **STEG National Dispatching** as part of the **PESTGM 7.0 Technical Challenge — Track 1**.

> Detailed module map, storage rules, API surface and the continuous operating loops:
> [ARCHITECTURE.md](ARCHITECTURE.md). Roadmap, risk containment and the closing assessment:
> [FUTURE_PERSPECTIVE_AND_CONCLUSION.md](FUTURE_PERSPECTIVE_AND_CONCLUSION.md).

## Overview

ESCANOR combines weather, STEG capacity, and production data to generate operational PV forecasts.

- **Multi-horizon:** intra-day → D+3
- **Spatial:** 50 districts → 7 Directions → governorates → national
- **Probabilistic:** P10 / P50 / P90 forecasts
- **ML:** 9-model LightGBM quantile ensemble
- **Features:** weather, solar geometry, capacity, dust, temporal and historical signals
- **Learning:** temporal validation, Optuna tuning, drift detection and retraining
- **API:** FastAPI
- **Dashboard:** national, regional, spatial, diagnostics, alerts and scenarios

## Architecture

```text
Weather / PVGIS / STEG Data
            │
            ▼
       Data Ingestion
            │
            ▼
    Feature Engineering
            │
            ▼
      Quality Filtering
            │
            ▼
 Temporal CV + Optuna
            │
            ▼
  9 LightGBM Quantile Models
       P10 / P50 / P90
            │
            ▼
    Uncertainty Engine
            │
            ▼
   Spatial Aggregation
            │
            ▼
        FastAPI API
            │
       ┌────┴────┐
       ▼         ▼
   Dashboard  Diagnostics
```

## The Five Operational Stages

The intro animation (`dashboard/assets/static/steg_intro.mp4`) shows the platform as five
numbered stages. This is what each stage actually does, with the file that implements it.

### 01 — Collect

| Input | Source | Where |
|---|---|---|
| Live weather | Open-Meteo forecast API, GHI/DNI/DHI + temperature, cloud cover, wind for all 50 districts, 3 days ahead | [ingestion/weather_client.py](ingestion/weather_client.py) |
| Historical irradiance & PV reference | PVGIS-JRC v5_2, cached per district under `results/datasets/pvgis_cache/` | [ingestion/pvgis_client.py](ingestion/pvgis_client.py) |
| Installed capacity & connection backlog | STEG "Tableau de Bord du Programme Prosol" text exports in `data/source/`, parsed into content-addressed snapshots | [reports/prosol_report_importer.py](reports/prosol_report_importer.py) |
| Live connections added after a snapshot | The installation ledger on the Prosol History page (add / amend / reverse) | `prosol_installation_updates` table |
| Measured output | Metering CSV upload buffered for bias correction and drift scoring | `api/services.py`, [db/repository.py](db/repository.py) |
| Offline development data | Physics-based synthetic generator (temperature derating + regional soiling) when no API access | [ingestion/synthetic_data.py](ingestion/synthetic_data.py) |

### 02 — Validate

Nothing reaches the model ungated:

- **Quality gate** — `validate_training_data()` in [models/features.py](models/features.py) drops negative production, production above `capacity × 1.15` (inverter headroom), nighttime rows above 0.5 MW, and rows missing GHI/temperature/production.
- **Unit sanity check** — series that look like single-site kW rather than district-aggregated MW are rejected outright instead of being scored, because they would poison every drift metric.
- **Drift check** — `check_drift_and_retrain()` in [models/retrain.py](models/retrain.py) compares daylight P50 error against the best of three naive baselines (persistence 24 h, persistence 168 h, climatology). Retraining starts when our error exceeds 85 % of the best baseline (`DRIFT_THRESHOLD_PCT = 15.0`), i.e. when the model has stopped earning its keep.
- **Promotion guard** — a candidate is trained across 3 expanding-window temporal folds, fitted on 80 % of history, and promoted only when its validation MAE is finite and better than the incumbent. Non-finite metrics block promotion. Every decision lands in `results/history/retrain_log.csv` under one frozen flat schema.

### 03 — Forecast

- **9 LightGBM models** = 3 quantiles (P10 / P50 / P90) × 3 ensemble seeds (42, 123, 456), averaged per quantile — [models/training_config.py](models/training_config.py).
- **19 input features** = 9 base (GHI, temperature, cloud cover, hour, day-of-year sin/cos, capacity, dust loss, `horizon_hours`) + 5 extended (DNI, DHI, wind, GHI×temperature, 3 h rolling GHI) + 5 physics (cos zenith, clear-sky index, hour sin/cos, climate zone) — [models/features.py](models/features.py).
- **Horizon-aware by design**: `horizon_hours` is a training feature, so uncertainty widens with lead time instead of a fixed band being bolted on afterwards.
- **Optuna tuning** — 30 trials by default over an expanding-window temporal CV (folds ending at 0.50/0.65, 0.65/0.80, 0.80/0.95), minimising mean absolute P50 error on future windows only, so no future row leaks into the fit. Baseline parameters: 400 trees, depth 6, learning rate 0.04.
- **Output** — hourly, J → J+3 (73 points) for each of 58 locations (50 districts + 7 Directions + national).
- **Every issued run is persisted** to `forecast_predictions` (4 234 rows per run) and pruned after 30 days (`ESCANOR_FORECAST_RETENTION_DAYS`), so the dashboard can show what was forecast, not only what is forecast now — it reads back the last 4 days, the horizon the model actually issues.

The prediction interval itself is built in [models/inference.py](models/inference.py); see [Quantile Ensemble](#quantile-ensemble) for the formula and for the calibration infrastructure that is present but not yet applied in production.

### 04 — Aggregate

```text
50 STEG commercial districts
        ↓
7 Directions de Distribution
        ↓
24 governorates
        ↓
National forecast
```

Medians are summed; uncertainty half-widths are combined as a root-sum-of-squares under an
independence assumption, or through the full covariance `√(hwᵀ R hw)` when a spatial
correlation matrix (Bremnes 2004) is supplied — [models/aggregation.py](models/aggregation.py).
Weather columns are averaged per group so the map can show conditions alongside power.

### 05 — Operate

- **Serving** — FastAPI on Uvicorn; APScheduler refreshes the forecast every 15 minutes but only during Tunisian daylight hours, and runs the drift/retrain check daily. A 14-minute in-memory cache absorbs dashboard polling.
- **Intraday correction** — the ratio of measured to forecast P50 over the last 3 hours rescales the live forecast when it is plausible (0 < ratio ≤ 3), and the dashboard banner says so.
- **Alerts** — `HIGH_UNCERTAINTY` (national P90−P10 above 50 MW), `RAMP_DOWN` (more than 30 % drop within 2 h), `SATURATION_RISK` (per-district MW thresholds), `MODEL_DRIFT`, `MODEL_RETRAINING_STARTED/FAILED` — [api/routers/alerts.py](api/routers/alerts.py).
- **Dashboard** — 8 pages: national overview, regional analysis, spatial timelapse, model health, alerts, park registry, Prosol history (snapshots, PV ledger, saved prediction runs, CSV export), what-if scenarios.
- **Scenarios** — cloud-cover, irradiance, temperature-offset and soiling stress tests: `P × (1 − 0.004 × max(0, T_offset))` for crystalline-silicon derating against the 25 °C STC reference (offset slider −10…+25 °C), cloud cover scaled against diffuse-only overcast, combined factor capped at 1.3, and the result sized in MW of extra reserve.

## ML Pipeline

### Features

19 features covering:

- GHI / DNI / DHI
- Temperature, cloud cover, wind
- Temporal encoding
- Installed capacity
- Dust / soiling
- Forecast horizon
- Solar zenith and clear-sky index
- Rolling GHI
- GHI × temperature
- Climate zone

### Quantile Ensemble

Three LightGBM models are trained for each quantile using different seeds:

```text
P10 → 3 models → mean
P50 → 3 models → mean
P90 → 3 models → mean
```

The resulting P10/P50/P90 predictions provide model-derived uncertainty.

The production interval is constructed as:

```python
half_width = min((p90 - p10) / 2, p50)

p10_final = max(0, p50 - half_width)
p90_final = p50 + half_width
```

> Split-conformal and horizon-dependent calibration were implemented and then deliberately
> reverted (commit `5f9be72`). The deployed interval is the raw quantile ensemble spread only;
> empirical P10–P90 coverage is reported next to accuracy on the Model Health page.

## Spatial Aggregation

```text
50 STEG Commercial Districts
            ↓
7 Directions de Distribution
            ↓
Governorates / Regions (24)
            ↓
National Forecast
```

## API

FastAPI provides endpoints for:

- National, intraday and regional forecasts
- District and governorate forecasts
- Spatial maps and timelapse
- Alerts and metrics
- Model retraining and versions
- Diagnostics and reports

API documentation:

```text
http://localhost:8000/docs
```

## Dashboard

The frontend provides:

- National forecast overview
- Regional/district analysis
- Spatial production timelapse
- Model diagnostics
- Operational alerts
- What-if scenarios
- Training and model history

## Data Sources

| Source | Usage |
|---|---|
| STEG ESCANOR | Capacity and connection data |
| Open-Meteo | Weather forecasts |
| PVGIS-JRC | Historical/reference PV data |
| STEG metering | Production data when available |
| Synthetic generator | Offline development |

## Data & Limitations

STEG capacity and connection data are based on the **March 2026 ESCANOR dashboard**.

Current hourly production training data is **physics-based synthetic data**, since per-installation historical metering was not provided. The architecture allows real production data to replace the synthetic generator without changing the downstream pipeline.

Live weather data is retrieved from Open-Meteo.

## Quickstart

```bash
pip install -r requirements.txt

# Train the model
python -m models.ml_forecast

# Optional: drift detection / retraining
python -m models.retrain

# Start API
uvicorn api.main:app --reload --port 8000
```

Open:

```text
API:       http://localhost:8000/docs
Dashboard: dashboard/index.html
```

## Technology Stack

- **Python**
- **FastAPI + Uvicorn**
- **LightGBM + scikit-learn**
- **Optuna**
- **pandas + NumPy**
- **Open-Meteo / PVGIS-JRC**
- **SQLite / CSV**
- **HTML / CSS / JavaScript**
- **Chart.js**

## Project Structure

```text
PréSol/
├── data/          # Domain data & configuration
├── ingestion/     # Weather, PVGIS and synthetic data
├── models/        # Forecasting, aggregation and learning
├── api/           # FastAPI backend
├── dashboard/     # Frontend
├── results/       # Generated artifacts
└── requirements.txt
```

Generated artifacts under `results/` are not tracked in Git.

## Team

- Rostom Mastory
- Abdannasser Mbarki
- Aya Jalouli
- Siwar Mhamdi

**ESCANOR × STEG**  
**PESTGM 7.0**
