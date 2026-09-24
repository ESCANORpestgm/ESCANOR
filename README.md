# PréSol — National Rooftop PV Forecast Platform

**ESCANOR × STEG** — An end-to-end platform for forecasting Tunisia's aggregated rooftop solar (auto-production) output from intra-day to D+3, at STEG commercial district, Direction, governorate, and national levels.

Built for **STEG National Dispatching** as part of the **PESTGM 7.0 Technical Challenge — Track 1: National Intelligent Platform for Forecasting Rooftop Solar Production**.

---

## Overview

PréSol transforms weather forecasts, STEG capacity data, and production data into operational solar-production forecasts.

- **Multi-horizon forecasting** — nowcast through D+3, from 50 STEG commercial districts → 7 Directions de Distribution → governorate/national aggregation.
- **Probabilistic forecasting** — P10 / P50 / P90 quantile forecasts provide a model-derived uncertainty interval.
- **9-model ensemble** — three independently seeded LightGBM models are trained for each quantile, then averaged to reduce model variance.
- **Physics-aware features** — solar geometry, clear-sky index, temperature, cloud cover, dust/soiling, temporal features, and historical signals.
- **Automatic learning pipeline** — temporal validation, Optuna hyperparameter tuning, data-quality filtering, drift detection, and automatic retraining.
- **Multi-baseline evaluation** — model performance is compared against persistence-24h, persistence-168h, and clear-sky baselines.
- **Tunisia-specific modelling** — regional climate zones and district-level capacity are incorporated into the feature and aggregation pipeline.
- **REST API** — FastAPI provides the integration point for dispatching and operational applications.
- **Interactive dashboards** — national overview, regional analysis, spatial timelapse, model diagnostics, alerts, registry, Prosol history, and what-if scenarios.

---

# Architecture

```text
                         ┌──────────────────────────────┐
                         │        External Sources      │
                         │                              │
                         │  Open-Meteo weather forecast │
                         │  PVGIS-JRC historical data   │
                         │  STEG Prosol capacity data   │
                         │  STEG production / metering  │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │          INGESTION            │
                         │                              │
                         │ weather_client.py             │
                         │ pvgis_client.py               │
                         │ synthetic_data.py              │
                         │                              │
                         │ Live weather + offline       │
                         │ physics-based fallback       │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │       DATA / FEATURES        │
                         │                              │
                         │ 19 model features            │
                         │                              │
                         │ GHI / DNI / DHI              │
                         │ Temperature / cloud / wind   │
                         │ Hour sin / cos                │
                         │ Day-of-year sin / cos       │
                         │ Capacity / dust              │
                         │ Forecast horizon             │
                         │ Solar zenith                 │
                         │ Clear-sky index              │
                         │ Rolling GHI                   │
                         │ GHI × temperature             │
                         │ Climate zone                  │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │       DATA QUALITY GATE       │
                         │                              │
                         │ Remove impossible / invalid  │
                         │ training observations        │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │             ML TRAINING PIPELINE         │
                    │                                          │
                    │ Temporal CV + Optuna hyperparameter      │
                    │ optimization                             │
                    │                                          │
                    │              9 LightGBM models            │
                    │                                          │
                    │   ┌─────────┬─────────┬─────────┐        │
                    │   │ P10 ×3  │ P50 ×3  │ P90 ×3  │        │
                    │   │ α = .1  │ α = .5  │ α = .9  │        │
                    │   └────┬────┴────┬────┴────┬────┘        │
                    │        │         │         │              │
                    │       mean      mean      mean            │
                    │        │         │         │              │
                    │        └─────────┼─────────┘              │
                    │                  ▼                        │
                    │          P10 / P50 / P90                 │
                    └──────────────────┬───────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────────┐
                    │             UNCERTAINTY ENGINE            │
                    │                                          │
                    │ Raw quantile spread:                     │
                    │                                          │
                    │ half_width = (P90 - P10) / 2             │
                    │                                          │
                    │ Symmetric band around P50                 │
                    │                                          │
                    │ Safety cap: half_width ≤ P50             │
                    │                                          │
                    │ P10 = max(0, P50 - half_width)           │
                    │ P90 = P50 + half_width                   │
                    └──────────────────┬───────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────────┐
                    │             SPATIAL AGGREGATION           │
                    │                                          │
                    │ 50 STEG commercial districts             │
                    │              ↓                           │
                    │ 7 Directions de Distribution             │
                    │              ↓                           │
                    │ Governorate / regional views              │
                    │              ↓                           │
                    │ National forecast                         │
                    │                                          │
                    │ Optional spatial-correlation handling     │
                    │ for uncertainty propagation                │
                    └──────────────────┬───────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────────┐
                    │              FASTAPI SERVICE              │
                    │                                          │
                    │ Forecast │ Spatial │ Alerts │ Metrics    │
                    │ Learning │ Reports │ Registry │ Meta      │
                    └───────────────┬──────────────────────────┘
                                    │
                  ┌─────────────────┼─────────────────┐
                  ▼                 ▼                 ▼
           National Dashboard   Spatial Map     Diagnostics
           Regional Analysis    Timelapse        Model Health
           Alerts               Scenarios        Training History
```

---

# Project Structure

```text
PréSol/
│
├── data/                         # Domain data & configuration
│   ├── governorates.py           # 24 governorates + coordinates
│   ├── steg_districts.py         # 50 districts → 7 Directions
│   ├── prosol_report_schema.py   # Prosol report structure
│   ├── features.py               # Feature definitions
│   ├── schema.py                 # Training-data contract
│   └── paths.py                  # Central artifact registry
│
├── ingestion/                    # External data acquisition
│   ├── weather_client.py         # Open-Meteo forecast client
│   ├── pvgis_client.py           # PVGIS-JRC reference data
│   └── synthetic_data.py         # Offline physics-based generator
│
├── models/                       # Forecasting & learning engine
│   ├── ml_forecast.py            # Quantile LightGBM + ensemble
│   ├── inference.py              # Shared prediction pipeline
│   ├── aggregation.py            # Spatial aggregation
│   ├── calibration.py            # Calibration analysis
│   ├── retrain.py                # Drift detection + retraining
│   ├── model_registry.py         # Versioned model registry
│   ├── evaluation.py             # Baseline comparison
│   ├── validation_report.py      # Validation diagnostics
│   └── history.py                # Forecast/training history
│
├── api/                          # FastAPI backend
│   ├── main.py                   # Application entrypoint
│   ├── core.py                   # Shared API configuration
│   ├── services.py               # Forecast/cache services
│   └── routers/
│       ├── forecast.py
│       ├── spatial.py
│       ├── alerts.py
│       ├── metrics.py
│       ├── learning.py
│       ├── diagnostics.py
│       ├── reports.py
│       └── meta.py
│
├── dashboard/                    # Static API-connected frontend
│   ├── index.html                # National overview
│   ├── districts.html            # Regional analysis
│   ├── map.html                  # Spatial timelapse
│   ├── performance.html          # Model diagnostics
│   ├── alerts.html               # Operational alerts
│   ├── registry.html             # Park/model registry
│   ├── scenarios.html            # What-if scenarios
│   └── prosol-history.html       # Prosol history
│
├── results/                      # Generated artifacts
│   ├── models/
│   ├── evaluations/
│   ├── history/
│   ├── calibration.json
│   └── ...
│
└── requirements.txt
```

Generated datasets, model artifacts, evaluations, figures, reports, and
databases under `results/` are **not tracked in Git**. They can be regenerated
from the source data and training pipeline.

---

# Machine Learning Pipeline

## 1. Feature Engineering

The forecasting model uses **19 features** combining meteorological,
temporal, physical, and regional information:

| Category          | Features                          |
| ----------------- | --------------------------------- |
| Solar irradiance  | GHI, DNI, DHI                     |
| Weather           | Temperature, cloud cover, wind    |
| Time              | Hour sin/cos, day-of-year sin/cos |
| PV system         | Installed capacity                |
| Environment       | Dust / soiling                    |
| Forecast          | Horizon                           |
| Solar physics     | Solar zenith, clear-sky index     |
| Historical signal | Rolling GHI                       |
| Interactions      | GHI × temperature                 |
| Geography         | Climate zone                      |

These features allow the model to capture both short-term weather variation
and Tunisia-specific solar-production behaviour.

---

## 2. Data Quality Gate

Before training, observations are passed through a quality-control stage that
filters impossible or invalid records.

This prevents corrupted measurements from being learned as legitimate
production behaviour.

---

## 3. Temporal Cross-Validation

Solar forecasting is a time-series problem, so training and validation respect
chronological order.

Instead of randomly mixing past and future observations, temporal validation
uses earlier observations for training and later observations for validation.

This reduces temporal leakage and gives a more realistic estimate of future
forecast performance.

---

## 4. Optuna Hyperparameter Optimization

Optuna is used to search for suitable LightGBM hyperparameters.

The optimization can tune parameters such as:

- learning rate
- number of estimators
- tree depth
- number of leaves
- subsampling
- feature sampling

The objective is evaluated using the temporal validation pipeline rather than a
random train/test split.

---

# 9-Model Quantile Ensemble

The production model contains **nine independent LightGBM regressors**.

```text
                  Seed 42    Seed 123    Seed 456
                 ─────────   ─────────   ─────────

P10 α=0.10          M1          M2          M3
                    │           │           │
                    └────── mean ──────────┘
                              │
                             P10

P50 α=0.50          M4          M5          M6
                    │           │           │
                    └────── mean ──────────┘
                              │
                             P50

P90 α=0.90          M7          M8          M9
                    │           │           │
                    └────── mean ──────────┘
                              │
                             P90
```

Each model uses:

```python
LGBMRegressor(
    objective="quantile",
    alpha=0.1,  # or 0.5 / 0.9
    random_state=seed
)
```

### Why three seeds?

The three models for each quantile are averaged:

```python
p10 = mean(p10_model_42, p10_model_123, p10_model_456)
p50 = mean(p50_model_42, p50_model_123, p50_model_456)
p90 = mean(p90_model_42, p90_model_123, p90_model_456)
```

The ensemble reduces sensitivity to the randomness of individual LightGBM
training runs.

There is **no voting or winner-takes-all selection**. Every model contributes
to its corresponding quantile.

---

# Uncertainty Construction

The production uncertainty interval is currently derived directly from the
ensemble's quantile predictions.

First:

```python
half_width = (p90 - p10) / 2
```

The interval is then constructed symmetrically around P50:

```python
p10_final = p50 - half_width
p90_final = p50 + half_width
```

A safety constraint prevents the uncertainty width from exceeding the
forecast itself:

```python
half_width = min(half_width, p50)
p10_final = max(p10_final, 0)
```

This guarantees the final output satisfies:

```text
P10 ≤ P50 ≤ P90
P10 ≥ 0
```

### Important calibration distinction

The platform contains conformal and horizon-dependent calibration infrastructure
for calibration analysis and experimentation. However, the current production
`predict()` path **does not add conformal `q̂` or multiply the interval by**
**horizon-dependent scale factors**.

The production interval therefore represents **model-derived quantile**
**uncertainty**, rather than a separately calibrated conformal prediction
interval.

This avoids excessive widening of the interval at low production values while
preserving the uncertainty learned by the quantile models.

---

# Continuous Learning

The retraining pipeline evaluates the current model against statistical
baselines:

```text
Current ML model
       │
       ├── Persistence 24h
       ├── Persistence 168h
       └── Clear-sky baseline
```

Performance degradation can trigger retraining.

The retraining pipeline includes:

1. Data-quality validation
2. Temporal validation
3. Baseline comparison
4. Candidate model training
5. Validation
6. Model promotion/rejection
7. Versioned registry update

This allows the forecasting system to adapt as weather conditions, production
patterns, or the underlying PV fleet change.

---

# Baseline Evaluation

The ML forecast is evaluated against three statistical/physics-based
references:

| Baseline         | Purpose                            |
| ---------------- | ---------------------------------- |
| Persistence 24h  | Short-term historical reference    |
| Persistence 168h | Weekly seasonal reference          |
| Clear-sky        | Physics-based production reference |

Metrics include:

- MAE
- RMSE
- nRMSE
- P10–P90 coverage
- Bias
- Horizon-specific performance

The baselines provide a reference for determining whether the ML model is
actually adding predictive value.

---

# Spatial Aggregation

Forecasts are generated and aggregated through the STEG operational
hierarchy:

```text
50 STEG commercial districts
             │
             ▼
7 Directions de Distribution
             │
             ▼
Governorates / regional views
             │
             ▼
National rooftop PV forecast
```

The aggregation layer combines district-level production and uncertainty while
preserving the geographical structure of the STEG network.

Spatial-correlation handling is available for uncertainty propagation where
appropriate.

---

# Tunisia-Specific Modelling

The platform incorporates local characteristics rather than treating Tunisia
as a generic solar-production region.

### Regional climate zones

The model distinguishes four Tunisian climate zones.

### Dust / soiling

Regional dust and soiling losses are incorporated into the production features,
with stronger effects represented in arid and interior regions.

### Solar geometry

Solar position and clear-sky information help distinguish changes caused by
solar geometry from changes caused by cloud/weather conditions.

### Installed capacity

District-level installed capacity is used to scale production and aggregate
forecasts through the STEG geography.

---

# API

The forecasting engine is exposed through a FastAPI service.

| Area          | Endpoints                                                                      |
| ------------- | ------------------------------------------------------------------------------ |
| Health / Meta | `/status`, `/cache/status`, `/steg-districts`, `/districts/positions`          |
| Forecast      | `/forecast/national`, `/forecast/intraday`, `/forecast/directions`             |
| District      | `/forecast/steg-district/{name}`                                               |
| Governorate   | `/forecast/governorate/{g}`                                                    |
| Spatial       | `/forecast/map`, `/forecast/timelapse`, `/export/forecast`                     |
| Alerts        | `/alerts`                                                                      |
| Metrics       | `/metrics`, `/history/national`, `/history/daily`                              |
| Learning      | `/models/retrain`, `/retrain/status`, `/models/versions`, `/models/production` |
| Diagnostics   | `/model/training-info`, `/model/training-progression`                          |
| Reports       | `/reports/prosol/summary`, `/reports/prosol/html`, `/reports/prosol/history`   |

The API provides the integration layer for operational applications and the
frontend dashboard.

---

# Dashboard

The frontend is a static HTML/CSS/JavaScript application connected to the
FastAPI backend.

### National Overview

Provides:

- National P50 production
- P10–P90 interval
- Forecast horizon
- Key operational indicators
- Forecast charts

### Regional Analysis

Allows drill-down from national production to Directions and districts.

### Spatial Timelapse

Displays the geographical evolution of rooftop PV production over time.

### Model Diagnostics

The performance dashboard exposes:

- Feature importance
- Calibration information
- Daily MAE/RMSE
- P10–P90 coverage
- Training progression
- Drift information
- Retraining history
- Model versions

### Alerts

Operational alerts include:

- High uncertainty
- Rapid production ramps
- Saturation conditions
- Retraining status

### What-If Scenarios

The scenario interface allows users to stress-test production under modified
cloud-cover assumptions.

---

# Data Grounding

Installed capacity and connection backlog are based on STEG's official:

**"Tableau de Bord du Programme Prosol — Mars 2026"**

The platform maps the reported commercial sub-district information to its
internal district, Direction, and governorate geography.

National capacity reconciliation is within approximately **0.3 MWc** of the
STEG reported figure, while pending-connection counts match the source data.

---

# Data Sources

| Source              | Usage                                     |
| ------------------- | ----------------------------------------- |
| STEG Prosol data    | Installed capacity and connection backlog |
| Open-Meteo          | Live weather forecasts                    |
| PVGIS-JRC           | Historical/reference PV production        |
| STEG metering       | Production training data when available   |
| Synthetic generator | Offline development/demo mode             |

---

# Honest Limitations

- **Installed capacity and connection backlog are real**, sourced from the
  STEG March 2026 Prosol dashboard.
- **Hourly production training data is currently physics-based synthetic data**
  because per-installation historical metering was not provided.
- The ML pipeline is designed so that real production measurements can replace
  the synthetic generator without changing the downstream model, aggregation,
  API, or dashboard architecture.
- **Live weather data is real and retrieved from Open-Meteo**, but online
  connectivity should be verified before operational demonstrations.
- The current P10/P90 production interval is **model-derived quantile**
  **uncertainty**. Conformal and horizon calibration components remain available
  for future validated calibration experiments but are not currently applied
  to the final prediction band.

---

# Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train the quantile ensemble
#    Synthetic data is used by default.
python -m models.ml_forecast

# 3. Optional: run drift detection / retraining
python -m models.retrain

# 4. Launch the API
uvicorn api.main:app --reload --port 8000
```

API documentation:

```text
http://localhost:8000/docs
```

The dashboard can then be opened from:

```text
dashboard/index.html
```

The frontend connects to the running FastAPI service for live forecasts and
diagnostics.

---

# Technology Stack

| Layer                 | Technology              |
| --------------------- | ----------------------- |
| Language              | Python                  |
| API                   | FastAPI + Uvicorn       |
| ML                    | LightGBM + scikit-learn |
| Hyperparameter tuning | Optuna                  |
| Model artifacts       | joblib                  |
| Data processing       | pandas + NumPy          |
| Weather               | Open-Meteo              |
| Solar reference data  | PVGIS-JRC               |
| Scheduling            | APScheduler             |
| Reports               | ReportLab + Matplotlib  |
| Frontend              | HTML + CSS + JavaScript |
| Charts                | Chart.js                |
| Database / history    | SQLite + CSV artifacts  |

---

# Reproducibility

The platform separates source data, model code, and generated artifacts.

```text
Source data
     │
     ▼
Feature engineering
     │
     ▼
Data quality
     │
     ▼
Temporal CV + Optuna
     │
     ▼
9-model quantile ensemble
     │
     ▼
Uncertainty construction
     │
     ▼
Spatial aggregation
     │
     ▼
API + Dashboard
```

Generated outputs under `results/` can be recreated from the training and
evaluation pipeline and are intentionally excluded from Git tracking.

---

# Team
Rostom Mastory
Abdannasser Mbarki
Aya jalouli
Siwar Mhamdi
---

## Project Context

**ESCANOR × STEG**

**PESTGM 7.0 Technical Challenge**

**Track 1 — National Intelligent Platform for Forecasting Rooftop Solar Production**
