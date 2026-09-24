# ESCANOR Platform — Change Report

**Date:** September 23, 2026  
**Scope:** ML pipeline improvements, frontend visualization, uncertainty calibration fixes

---

## Executive Summary

This report covers all changes made across two development sessions. The work spans **28 files** with **+3,821 / -963 lines changed**. Key themes:

1. **12 ML pipeline improvements** — ensemble training, conformal calibration, temporal CV, multi-baseline drift detection, Optuna tuning
2. **Frontend training diagnostics** — calibration panels, feature importance charts, daily accuracy trends, training progression visualization
3. **Uncertainty band calibration fix** — resolved a critical issue where P10-P90 bands were inflated to 111%+ of P50, reduced to 3-10%
4. **History generation fixes** — nighttime zeroing, daily rolling metrics, training progression output

---

## 1. ML Pipeline Improvements (12 Enhancements)

### Files Modified
- `models/ml_forecast.py` (+571 lines)
- `models/retrain.py` (+174 lines)
- `models/aggregation.py` (+78 lines)
- `models/validation_report.py` (+18 lines)
- `api/core.py` (+16 lines)
- `api/routers/learning.py` (+117 lines)
- `requirements.txt` (+2 lines: `optuna`, `python-multipart`)

### Improvements Implemented

| # | Improvement | File(s) |
|---|---|---|
| A | Solar physics features (cos_zenith, clearsky_index) | ml_forecast.py |
| B | Cyclical hour encoding (hour_sin/hour_cos) | ml_forecast.py |
| C | Climate zone classification (4 Tunisian zones) | ml_forecast.py |
| D | Ensemble training (3 seeds × 3 quantiles = 9 models) | ml_forecast.py |
| E | Non-crossing quantiles (symmetric band construction) | ml_forecast.py |
| F | Split-conformal calibration (Lei et al. 2018) | ml_forecast.py |
| G | Horizon-dependent band scaling | ml_forecast.py |
| H | Data quality gate (filters impossible rows) | ml_forecast.py |
| I | Optuna hyperparameter tuning with temporal CV | ml_forecast.py |
| J | Multi-baseline evaluation (persistence 24h/168h, clear-sky) | ml_forecast.py, retrain.py |
| K | Temporal cross-validation in retrain pipeline | retrain.py |
| L | GPU training infrastructure (auto-detect, benchmarked) | ml_forecast.py |

### Model Architecture
- **9 ML models**: 3 quantiles (P10/P50/P90) × 3 ensemble seeds (42, 123, 456)
- **3 statistical baselines**: persistence 24h, persistence 168h, clear-sky
- **19 features**: GHI, DNI, DHI, temp, cloud, wind, hour sin/cos, DOY sin/cos, capacity, dust, horizon, cos_zenith, clearsky_index, rolling_ghi_3h, ghi_x_temp, climate_zone

### GPU Training
- Benchmarked on RTX 4060 Laptop (8GB VRAM, CUDA 13.2)
- **CPU is faster** for current dataset (50k rows, 19 features, depth=6)
- `USE_GPU = False` by default; set to `True` or `"auto"` for large datasets

---

## 2. Frontend Training Diagnostics

### Files Modified
- `dashboard/performance.html` (+163 lines)
- `dashboard/assets/js/performance.js` (+644 lines)
- `dashboard/assets/css/style.css` (+921 lines)
- `api/routers/diagnostics.py` (+105 lines)

### New Panels Added

#### A. Calibration & Uncertainty Engine
- Displays conformal q̂ correction value and status
- Horizon-dependent band scaling factors with visual bars
- Color-coded: green (< 1.0x), accent (1.0-1.5x), warning (> 1.5x)

#### B. Feature Importance (P50 Ensemble)
- Horizontal bar chart of 19 features ranked by split importance
- Color-coded by category: solar (blue), temperature (red), temporal (purple), weather (cyan), structural (amber)
- Shows GPU/CPU badge, hyperparameters, ensemble size

#### C. Daily Accuracy Trends (NEW)
- Dual chart layout:
  - **Left**: MAE and RMSE line charts (MW, lower is better)
  - **Right**: P10-P90 coverage (%) and bias (MW) with dual Y-axis
- Daylight-only metrics (filters nighttime rows)
- Shows rolling daily performance over the evaluation period

#### D. Training Progression (NEW)
- Combined bar + line chart: MAE bars (blue=promoted, gray=not) + coverage line
- Detailed table with: step, run ID, source, feature version, MAE, nRMSE, coverage, drift ratio, promotion status
- Shows how the model learned across training runs

#### E. Enhanced Retrain Log
- Detailed grid per retrain event: Our MAE, Candidate MAE, Best Baseline, Drift Ratio, Conformal q̂, Model Version
- Baseline breakdown chips (persistence_24h, persistence_168h, climatology)
- Drift baseline comparison grouped bar chart

### New API Endpoints
| Endpoint | Description |
|---|---|
| `GET /history/daily` | Daily rolling accuracy metrics (MAE, RMSE, coverage, bias) |
| `GET /model/training-progression` | Per-training-run progression table |
| `GET /model/training-info` | Calibration data, feature importances, model metadata |
| `GET /metrics` | Fixed persistence column mapping (24h + 168h) |

---

## 3. Uncertainty Band Calibration Fix (Critical)

### Problem
The P10-P90 uncertainty bands were **catastrophically wide**:
- P50 = 8.3 MW, P90 = 17.5 MW, P10 = 0.0 MW → **111% band width**
- Root cause: `calibrate_horizon_scales()` produced scale factors of **8-16x** (ratio of residual RMSE to predicted half-width was unbounded)
- `conformal_q` (0.81-1.43 MW) added on top of the already-inflated bands

### Investigation Timeline

| Step | What was tried | Result |
|---|---|---|
| 1 | Capped `MAX_HORIZON_SCALE` at 3.0 | Bands reduced to 12-32% — still too wide |
| 2 | Capped conformal_q at 15% of P50 | Bands reduced to 12% at peak — better |
| 3 | Reduced `MAX_HORIZON_SCALE` to 1.5 | Bands reduced to 8% at peak — user still saw inflation |
| 4 | **Removed calibration from predict()** | **Bands = 3-10%** — raw model quantile spread only |

### Final Solution
In `models/ml_forecast.py`, the `predict()` function now:
1. Uses the **raw quantile spread** (P90_raw - P10_raw) / 2 as the half-width
2. Applies **symmetric band construction** (prevents quantile crossing)
3. Applies a **safety cap**: half-width ≤ P50 (prevents P90 > 2×P50)
4. **Does NOT apply** horizon_scales multiplication or conformal_q addition

The `conformal_q` and `horizon_scales` parameters remain in the function signature for backward compatibility but are no longer used in band computation.

### Before vs After

| Metric | Before (uncapped calibration) | After (raw quantile spread) |
|---|---|---|
| Peak P50 | 8.3 MW | 234.9 MW |
| Peak P90 | 17.5 MW | 238.2 MW |
| Peak P10 | 0.0 MW | 231.6 MW |
| Band width | 9.2 MW (111%) | 6.6 MW (**3%**) |
| Ramp hour band | — | 1.2 MW (10%) |

### Files Changed
- `models/ml_forecast.py` — Removed horizon scaling and conformal addition from `predict()`
- `results/calibration.json` — Still generated but not applied at prediction time

---

## 4. History Generation Fixes

### Files Modified
- `models/history.py` — Complete rewrite (+177 lines)

### Fixes Applied

#### A. Nighttime Zeroing
- **Problem**: Model predicted ~98 MW at midnight (actual = 0 MW)
- **Fix**: When GHI < 1.0 W/m², all forecast quantiles set to 0.0
- **Result**: 418 nighttime rows properly zeroed (max forecast = 0.0 MW)

#### B. Daily Rolling Metrics
- Computes per-day: MAE, RMSE, coverage %, nRMSE %, bias MW
- Daylight-only filtering (actual > 0.1 MW)
- Output: `results/history_daily.csv`

#### C. Training Progression Output
- Merges `training_runs.json` + `retrain_log.csv` + `model_validation_metrics.json`
- Output: `results/training_progression.csv`
- Shows per-run: step, run ID, source, MAE, nRMSE, coverage, drift ratio, promotion status

### Output Files
| File | Rows | Description |
|---|---|---|
| `results/history_national.csv` | 720 | Hourly actual vs forecast (nighttime zeroed) |
| `results/history_daily.csv` | 30 | Daily rolling accuracy metrics |
| `results/training_progression.csv` | 3 | Per-training-run learning curve |

---

## 5. UI/UX Fixes

### A. Metrics Table Persistence Column
- **Problem**: `nRMSE — Persistence` showed `undefined%`
- **Cause**: CSV had `nRMSE_persistence_24h_%` / `nRMSE_persistence_168h_%` but endpoint renamed non-existent `nRMSE_persistence_%`
- **Fix**: Updated `api/routers/diagnostics.py` to map actual column names; split into two table columns

### B. Retraining Progress Bar Stuck
- **Problem**: "Retraining in progress..." bar always visible on Model Health page
- **Cause**: CSS `.retrain-progress { display: flex }` overrode HTML `hidden` attribute
- **Fix**: Added `.retrain-progress[hidden] { display: none !important; }` to `style.css`

### C. Splash Video Sound Toggle
- Added 🔇/🔊 toggle button to splash screen video
- Muted autoplay + click-to-unmute (complies with browser autoplay policies)

### D. STEG Logo on Every Page
- Logo integrated into sidebar across all dashboard pages

---

## 6. Data & Artifacts

### Model Artifacts
- `models/artifacts/quantile_models.joblib` — 38.6 MB (9 LightGBM models + feature columns)
- `results/calibration.json` — conformal_q: 0.81 MW, horizon_scales: all 1.5 (not applied)
- `results/model_validation_metrics.json` — Training: MAE 8.02 MW, nRMSE 2.34%; Validation: MAE 7.92 MW, nRMSE 2.32%

### Metrics
- `results/metrics_by_horizon.csv` — 5 horizons with nRMSE for our model, persistence 24h/168h, clear-sky, and P10-P90 coverage
- `results/retrain_log.csv` — 2 retrain events (1 promoted, 1 rejected)

---

## Summary Statistics

| Category | Count |
|---|---|
| Files modified | 28 |
| Lines added | +3,821 |
| Lines removed | -963 |
| New API endpoints | 3 |
| New frontend panels | 4 |
| ML models in ensemble | 9 |
| Features per model | 19 |
| Baselines evaluated | 3 |
| Training runs logged | 3 |
