# Machine Learning Pipeline Architecture

<cite>
**Referenced Files in This Document**
- [ml_forecast.py](file://models/ml_forecast.py)
- [aggregation.py](file://models/aggregation.py)
- [retrain.py](file://models/retrain.py)
- [model_registry.py](file://models/model_registry.py)
- [rooftop_training_adapter.py](file://models/rooftop_training_adapter.py)
- [synthetic_data.py](file://ingestion/synthetic_data.py)
- [steg_districts.py](file://data/steg_districts.py)
- [main.py](file://api/main.py)
- [forecast.py](file://api/routers/forecast.py)
- [learning.py](file://api/routers/learning.py)
- [core.py](file://api/core.py)
- [model_versions.json](file://results/model_registry/model_versions.json)
- [training_runs.json](file://results/model_registry/training_runs.json)
- [production_model.json](file://results/model_registry/production_model.json)
</cite>

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion

## Introduction
This document describes the machine learning pipeline that delivers multi-horizon rooftop PV production forecasts across 50 STEG commercial districts and aggregates them to Direction and national levels. The system uses LightGBM quantile regression models to produce P10/P50/P90 predictions, supports continuous learning with drift detection against a persistence baseline, and provides an API for real-time forecasting and model registry operations. It also documents feature engineering, training workflows, aggregation with uncertainty propagation, model versioning, retraining triggers, performance optimization, and scalability considerations.

## Project Structure
The platform is organized into clear layers:
- Ingestion: synthetic or live weather generation and district metadata
- Models: ML forecasting, aggregation, retraining, and model registry
- API: FastAPI endpoints exposing forecasts, grid integration tools, and continuous learning controls
- Data and results: district definitions, model artifacts, and registry files

```mermaid
graph TB
subgraph "Ingestion"
SD["Synthetic Weather<br/>ingestion/synthetic_data.py"]
DIST["District Metadata<br/>data/steg_districts.py"]
end
subgraph "Models"
ML["ML Forecast (LightGBM Quantile)<br/>models/ml_forecast.py"]
AGG["Aggregation & Uncertainty<br/>models/aggregation.py"]
RETRAIN["Drift Detection & Retraining<br/>models/retrain.py"]
REG["Model Registry<br/>models/model_registry.py"]
ADAPTER["Training Frame Builder<br/>models/rooftop_training_adapter.py"]
end
subgraph "API"
APP["FastAPI App<br/>api/main.py"]
CORE["Core State & Scheduler<br/>api/core.py"]
FRC["Forecast Endpoints<br/>api/routers/forecast.py"]
LRN["Learning Endpoints<br/>api/routers/learning.py"]
end
subgraph "Results"
REGJSON["Registry JSONs<br/>results/model_registry/*.json"]
end
SD --> ML
DIST --> ML
ML --> AGG
ML --> CORE
CORE --> FRC
CORE --> LRN
LRN --> RETRAIN
RETRAIN --> REG
REG --> REGJSON
AGG --> FRC
```

**Diagram sources**
- [ml_forecast.py:1-267](file://models/ml_forecast.py#L1-L267)
- [aggregation.py:1-164](file://models/aggregation.py#L1-L164)
- [retrain.py:1-115](file://models/retrain.py#L1-L115)
- [model_registry.py:1-161](file://models/model_registry.py#L1-L161)
- [rooftop_training_adapter.py:1-89](file://models/rooftop_training_adapter.py#L1-L89)
- [synthetic_data.py:1-170](file://ingestion/synthetic_data.py#L1-L170)
- [steg_districts.py:1-200](file://data/steg_districts.py#L1-L200)
- [main.py:1-42](file://api/main.py#L1-L42)
- [forecast.py:1-203](file://api/routers/forecast.py#L1-L203)
- [learning.py:1-163](file://api/routers/learning.py#L1-L163)
- [core.py:1-166](file://api/core.py#L1-L166)

**Section sources**
- [main.py:1-42](file://api/main.py#L1-L42)
- [core.py:1-166](file://api/core.py#L1-L166)
- [steg_districts.py:1-200](file://data/steg_districts.py#L1-L200)

## Core Components
- Multi-horizon quantile forecasting: Three LightGBM quantile regressors per horizon produce P10/P50/P90 predictions using engineered features including time-of-day, seasonal cycles, capacity, dust loss, DNI/DHI splits, wind speed, temperature interaction, and rolling GHI.
- Aggregation engine: Sums P50 across districts and combines uncertainty bands using sqrt-sum-of-squares of half-widths to propagate uncertainty from district to direction and national levels.
- Continuous learning: Compares recent forecast error to a persistence baseline; if drift exceeds threshold, trains candidate models on recent data, registers versions, and promotes only when validation improves.
- Model registry: Immutable file-based registry tracking training runs, model versions, metrics, and promotion status; ensures candidates outperform current production before promotion.
- API layer: Exposes endpoints for national/direction/district forecasts, map/timelapse views, export, bias correction, and continuous learning controls.

**Section sources**
- [ml_forecast.py:30-152](file://models/ml_forecast.py#L30-L152)
- [aggregation.py:20-89](file://models/aggregation.py#L20-L89)
- [retrain.py:40-104](file://models/retrain.py#L40-L104)
- [model_registry.py:35-131](file://models/model_registry.py#L35-L131)
- [forecast.py:25-158](file://api/routers/forecast.py#L25-L158)
- [learning.py:52-163](file://api/routers/learning.py#L52-L163)

## Architecture Overview
The pipeline ingests weather and district metadata, engineers features, predicts quantiles, aggregates to higher levels, and exposes results via API. A continuous learning loop monitors drift and retrains models when needed, with strict promotion policies enforced by the registry.

```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "FastAPI /forecast"
participant Core as "api/core.build_forecast"
participant ML as "models.ml_forecast.predict"
participant AGG as "models.aggregation.aggregate"
participant Reg as "models.model_registry"
participant Retrain as "models.retrain.check_drift_and_retrain"
Client->>API : GET /forecast/national?horizon_days=3
API->>Core : get_forecast_frame(horizon_days)
Core->>Core : build_live_weather_dataframe() or generate_all()
Core->>ML : predict(models, weather_df, capacity_lookup, dust_lookup)
ML-->>Core : df with p10/p50/p90 per district
Core-->>API : forecast frame
API->>AGG : aggregate(df, level="national")
AGG-->>API : aggregated national p10/p50/p90
API-->>Client : JSON records
Note over Retrain,Reg : Background daily job triggers drift check and optional retraining
Retrain->>Reg : create_training_run(), register_model(), promote_model()
```

**Diagram sources**
- [forecast.py:25-32](file://api/routers/forecast.py#L25-L32)
- [core.py:72-99](file://api/core.py#L72-L99)
- [ml_forecast.py:118-131](file://models/ml_forecast.py#L118-L131)
- [aggregation.py:26-89](file://models/aggregation.py#L26-L89)
- [retrain.py:40-104](file://models/retrain.py#L40-L104)
- [model_registry.py:35-131](file://models/model_registry.py#L35-L131)

## Detailed Component Analysis

### Feature Engineering and Multi-Horizon Forecasting
- Features include base time and capacity features plus extended weather interactions and rolling averages. Optional columns are filled with sensible defaults so pipelines remain robust with incomplete inputs.
- Three LightGBM quantile regressors are trained per horizon to output P10/P50/P90. Predictions are clipped to non-negative values and sorted to enforce monotonicity (P10 ≤ P50 ≤ P90).
- Evaluation computes MAE and nRMSE on daylight hours and coverage of the P10–P90 band.

```mermaid
flowchart TD
Start(["Feature Engineering Entry"]) --> TimeFeat["Add hour, day_of_year_sin/cos,<br/>capacity_mwc, dust_loss_pct,<br/>horizon_hours"]
TimeFeat --> ExtFeat["Fill dni_wm2/dhi_wm2,<br/>wind_speed_ms,<br/>ghi_x_temp,<br/>rolling_ghi_3h"]
ExtFeat --> Train{"Train?"}
Train --> |Yes| Fit["Fit LGBMRegressor per quantile<br/>alpha ∈ {0.1, 0.5, 0.9}"]
Train --> |No| Predict["Predict with loaded models"]
Fit --> Save["Save models"]
Predict --> ClipSort["Clip ≥ 0 and sort p10≤p50≤p90"]
ClipSort --> Output(["Return forecast frame"])
Save --> Output
```

**Diagram sources**
- [ml_forecast.py:49-94](file://models/ml_forecast.py#L49-L94)
- [ml_forecast.py:97-131](file://models/ml_forecast.py#L97-L131)

**Section sources**
- [ml_forecast.py:30-152](file://models/ml_forecast.py#L30-L152)

### Aggregation Engine and Uncertainty Propagation
- Aggregates per-district forecasts to direction and national levels by summing P50 and combining uncertainty bands using sqrt-sum-of-squares of half-widths. This assumes partial independence of district-level errors; adjacent districts sharing cloud systems may have correlated errors, slightly underestimating true uncertainty.
- Supports multiple grouping keys and legacy aliases for compatibility.

```mermaid
flowchart TD
A["Per-district p10/p50/p90"] --> B["Compute half_width = (p90 - p10)/2"]
B --> C{"Group by level"}
C --> |National| SumNat["Sum p50 across all districts"]
C --> |Direction| SumDir["Sum p50 by direction"]
C --> |District| Keep["Keep per-district rows"]
SumNat --> CombineNat["Combine half_widths via sqrt(sum(h^2))"]
SumDir --> CombineDir["Combine half_widths via sqrt(sum(h^2))"]
CombineNat --> OutNat["Output national p10/p50/p90"]
CombineDir --> OutDir["Output direction p10/p50/p90"]
Keep --> OutDist["Output district p10/p50/p90"]
```

**Diagram sources**
- [aggregation.py:20-89](file://models/aggregation.py#L20-L89)

**Section sources**
- [aggregation.py:1-164](file://models/aggregation.py#L1-L164)

### Continuous Learning and Drift Detection
- Drift detection compares recent model MAE to a persistence baseline (24-hour lag). If the ratio indicates degradation beyond a threshold, a candidate model is trained on a recent training split and validated on a holdout split.
- Candidate models are registered with metrics and promoted only if they improve upon current production MAE. Training runs are tracked with start/end timestamps, feature/schema versions, and status transitions.

```mermaid
sequenceDiagram
participant LRN as "learning.py"
participant RET as "retrain.py"
participant REG as "model_registry.py"
participant MLF as "ml_forecast.py"
LRN->>RET : check_drift_and_retrain(recent_df, capacity_lookup, dust_lookup)
RET->>MLF : evaluate(current_models, validation_df)
RET->>RET : compute persistence baseline MAE
RET->>RET : drift_ratio = our_MAE / persist_MAE
alt drift above threshold
RET->>REG : create_training_run(data_start, data_end, feature_version, schema_version, source)
RET->>MLF : train_quantile_models(train_df)
RET->>MLF : evaluate(candidate_models, validation_df)
RET->>REG : register_model(run_id, artifact_path, metrics, ...)
RET->>REG : promote_model(model_version, production_artifact)
else no retrain
RET-->>LRN : status without retraining
end
```

**Diagram sources**
- [learning.py:31-49](file://api/routers/learning.py#L31-L49)
- [retrain.py:40-104](file://models/retrain.py#L40-L104)
- [model_registry.py:35-131](file://models/model_registry.py#L35-L131)
- [ml_forecast.py:97-152](file://models/ml_forecast.py#L97-L152)

**Section sources**
- [retrain.py:1-115](file://models/retrain.py#L1-L115)
- [model_registry.py:1-161](file://models/model_registry.py#L1-L161)
- [learning.py:1-163](file://api/routers/learning.py#L1-L163)

### Model Versioning and Registry Management
- File-based immutable registry tracks training runs and model versions with timestamps, metrics, feature/schema versions, and statuses (candidate, production, archived).
- Promotion enforces improvement over current production MAE and copies artifacts safely. Ensure_initial_production initializes the registry for existing artifacts.

```mermaid
classDiagram
class ModelRegistry {
+create_training_run(data_start, data_end, feature_version, schema_version, source) string
+finish_training_run(training_run_id, status, model_version, metrics, error) void
+register_model(training_run_id, artifact_path, metrics, data_start, data_end, feature_version, schema_version, status) string
+promote_model(model_version, production_artifact) dict
+ensure_initial_production(artifact_path, metrics) dict
+list_model_versions() list
+list_training_runs() list
}
```

**Diagram sources**
- [model_registry.py:35-161](file://models/model_registry.py#L35-L161)

**Section sources**
- [model_registry.py:1-161](file://models/model_registry.py#L1-L161)
- [production_model.json:1-18](file://results/model_registry/production_model.json#L1-L18)
- [model_versions.json:1-35](file://results/model_registry/model_versions.json#L1-L35)
- [training_runs.json:1-32](file://results/model_registry/training_runs.json#L1-L32)

### API Workflows and Real-Time Forecasting
- Endpoints provide national, direction, and district forecasts; map snapshots; timelapse frames; and export to CSV/XML. Bias correction scales forecasts using recent metered data when available.
- Cache avoids recomputation within a short window; background scheduler refreshes periodically and triggers daily retraining checks.

```mermaid
sequenceDiagram
participant Client as "Client"
participant FRC as "/forecast/*"
participant CORE as "build_forecast()"
participant W as "weather_client or synthetic"
participant M as "ml_forecast.predict"
participant A as "aggregation.aggregate"
Client->>FRC : GET /forecast/intraday
FRC->>CORE : get_forecast_frame(1)
CORE->>W : build_live_weather_dataframe() or generate_all()
W-->>CORE : weather DataFrame
CORE->>M : predict(models, weather, capacity, dust)
M-->>CORE : forecast per district
CORE-->>FRC : cached forecast frame
FRC->>A : aggregate(level="national")
A-->>FRC : aggregated national series
FRC-->>Client : 15min interpolated series with optional bias correction
```

**Diagram sources**
- [forecast.py:35-54](file://api/routers/forecast.py#L35-L54)
- [core.py:72-99](file://api/core.py#L72-L99)
- [ml_forecast.py:118-131](file://models/ml_forecast.py#L118-L131)
- [aggregation.py:26-89](file://models/aggregation.py#L26-L89)

**Section sources**
- [forecast.py:1-203](file://api/routers/forecast.py#L1-L203)
- [core.py:1-166](file://api/core.py#L1-L166)

### Data Preparation for Retraining
- Validated rooftop measurement snapshots are converted to the canonical training schema, aggregating power by timestamp and district, merging weather if necessary, and enforcing quality filters.

```mermaid
flowchart TD
In["Validated measurements CSV"] --> Q["Filter valid rows<br/>timestamp_utc, power_kw, district, direction"]
Q --> Agg["Aggregate power_kw by timestamp,district → production_mw"]
Agg --> Merge{"Weather present?"}
Merge --> |Yes| UseW["Use embedded weather columns"]
Merge --> |No| LoadW["Load external weather CSV and merge"]
UseW --> Out["Sorted training frame (governorate, timestamp, weather, production)"]
LoadW --> Out
```

**Diagram sources**
- [rooftop_training_adapter.py:26-89](file://models/rooftop_training_adapter.py#L26-L89)

**Section sources**
- [rooftop_training_adapter.py:1-89](file://models/rooftop_training_adapter.py#L1-L89)

## Dependency Analysis
Key dependencies and coupling:
- API depends on core state and model prediction; core orchestrates weather ingestion and caching.
- ML forecasting depends on district metadata for capacity and dust loss; aggregation depends on forecast outputs and grouping keys.
- Retraining depends on model registry for versioning and promotion; learning endpoints orchestrate background jobs and logging.

```mermaid
graph LR
API["api/routers/forecast.py"] --> CORE["api/core.py"]
CORE --> ML["models/ml_forecast.py"]
CORE --> W["ingestion/synthetic_data.py"]
ML --> DIST["data/steg_districts.py"]
API --> AGG["models/aggregation.py"]
LEARN["api/routers/learning.py"] --> RETRAIN["models/retrain.py"]
RETRAIN --> REG["models/model_registry.py"]
```

**Diagram sources**
- [forecast.py:1-203](file://api/routers/forecast.py#L1-L203)
- [core.py:1-166](file://api/core.py#L1-L166)
- [ml_forecast.py:1-267](file://models/ml_forecast.py#L1-L267)
- [synthetic_data.py:1-170](file://ingestion/synthetic_data.py#L1-L170)
- [steg_districts.py:1-200](file://data/steg_districts.py#L1-L200)
- [aggregation.py:1-164](file://models/aggregation.py#L1-L164)
- [learning.py:1-163](file://api/routers/learning.py#L1-L163)
- [retrain.py:1-115](file://models/retrain.py#L1-L115)
- [model_registry.py:1-161](file://models/model_registry.py#L1-L161)

**Section sources**
- [core.py:1-166](file://api/core.py#L1-L166)
- [ml_forecast.py:1-267](file://models/ml_forecast.py#L1-L267)
- [aggregation.py:1-164](file://models/aggregation.py#L1-L164)
- [retrain.py:1-115](file://models/retrain.py#L1-L115)
- [model_registry.py:1-161](file://models/model_registry.py#L1-L161)

## Performance Considerations
- Caching: Forecasts are cached for up to 14 minutes to reduce repeated computation; background scheduler refreshes every 15 minutes during operational hours.
- Efficient feature engineering: Rolling GHI computed per governorate; optional columns filled with defaults to avoid branching overhead.
- Quantile crossing guard: Sorting predictions ensures consistent uncertainty bands without post-processing complexity.
- Aggregation efficiency: Groupby operations on pandas DataFrames scale well to 50 districts; uncertainty combination uses vectorized numpy operations.
- Bias correction: Applied only when sufficient recent metering exists; prevents unnecessary scaling.

Scalability considerations:
- District count (50) and horizon length (up to 3 days) fit comfortably in memory; groupby and vectorized ops remain efficient.
- For larger scale, consider:
  - Parallelizing per-district feature computations where applicable
  - Using batched model inference with optimized LightGBM settings
  - Partitioning aggregation by direction to reduce cross-group operations
  - Streaming updates for metering buffer and incremental retraining windows

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- No forecast data available: Ensure weather ingestion returns rows within the requested horizon; fallback to synthetic data if live calls fail.
- Unknown district or direction: Validate names against district metadata; endpoints return 404 with options when not found.
- Retraining failures: Check validated measurement snapshots and required columns; ensure weather data matches timestamps and districts; review retrain logs and status endpoints.
- Promotion blocked: Candidate must improve MAE over current production; verify metrics and artifact paths exist.

**Section sources**
- [forecast.py:64-89](file://api/routers/forecast.py#L64-L89)
- [learning.py:77-108](file://api/routers/learning.py#L77-L108)
- [model_registry.py:104-131](file://models/model_registry.py#L104-L131)
- [core.py:106-122](file://api/core.py#L106-L122)

## Conclusion
The pipeline delivers robust multi-horizon PV forecasts with calibrated uncertainty bands across 50 districts, aggregates to higher administrative levels, and continuously learns from observed production while maintaining strict model governance. The architecture balances accuracy, interpretability, and operational reliability through careful feature design, quantile modeling, uncertainty propagation, and automated drift-aware retraining with immutable versioning.

[No sources needed since this section summarizes without analyzing specific files]