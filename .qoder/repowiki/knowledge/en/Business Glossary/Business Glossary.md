---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### STEG Districts
- Definition：The canonical set of 50 commercial sub-districts defined in `data/steg_districts.py` that form the finest forecasting granularity. Each district carries installed capacity, dust/soiling loss, latitude/longitude, and displacement factors; they aggregate up to the 7 distribution directions and 24 governorates.
- Aliases：steg_district、commercial district、direction de distribution

### Prosol Report
- Definition：The monthly rooftop-PV report published by STEG's Programme Prosol (Tableau de Bord du Programme Prosol). It contains national indicators, financing, installation and installed-power history, breakdown by Direction de Distribution and commercial district, system-size buckets, and pending dossiers. CES (Chauffe-Eau-Solaire) values are explicitly excluded from PV metrics. New reports are imported via `reports/prosol_report_importer` into normalized JSON snapshots under `reports/generated/`.
- Aliases：prosol、tableau de bord prosol、prosol snapshot、monthly prosol report

### P10/P50/P90
- Definition：Calibrated uncertainty bands produced by the horizon-aware quantile gradient-boosting model in `models/ml_forecast.py`. P10 is the lower bound (10 % chance actual output falls below), P50 is the median forecast, and P90 is the upper bound; coverage widens realistically with forecast lead time rather than using a fixed band.
- Aliases：quantile bands、uncertainty bands、quantile regression

### Drift Detection
- Definition：The continuous-learning mechanism in `models/retrain.py` that compares recent forecast error against a persistence baseline and triggers automatic retraining when performance degrades. Runs as a daily APScheduler job and also exposed via the `/models/retrain` endpoint.
- Aliases：continuous learning、automatic retrain、drift check

### Nowcast / Intra-day / D+1–D+3
- Definition：Forecast horizons used throughout the platform: nowcast (same day, near-term), intra-day (remaining hours of today), and multi-day horizons D+1 through D+3. Model accuracy and uncertainty bands vary by horizon, with nRMSE increasing and P10–P90 coverage narrowing as lead time grows.
- Aliases：forecast horizon、lead time、horizon

### Metering Buffer
- Definition：A rolling CSV file at `results/metering_buffer.csv` that stores recent actual vs. forecasted MW readings. `compute_bias_correction()` reads the last 3 hours to compute a bias ratio applied to forecasts; it requires at least two non-zero entries and rejects ratios outside (0, 3].
- Aliases：meter buffer、bias correction buffer、actual_mw
