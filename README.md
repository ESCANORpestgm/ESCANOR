# ESCANOR — National Rooftop PV Forecast Platform

**ESCANOR × STEG** — A platform for forecasting Tunisia's aggregated rooftop solar production from intra-day to D+3, across STEG districts, Directions, governorates, and national level.

Built for **STEG National Dispatching** as part of the **PESTGM 7.0 Technical Challenge — Track 1**.

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

> Conformal and horizon-dependent calibration infrastructure exists, but is **not currently applied to the production prediction interval**.

## Spatial Aggregation

```text
50 STEG Commercial Districts
            ↓
7 Directions de Distribution
            ↓
Governorates / Regions
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
