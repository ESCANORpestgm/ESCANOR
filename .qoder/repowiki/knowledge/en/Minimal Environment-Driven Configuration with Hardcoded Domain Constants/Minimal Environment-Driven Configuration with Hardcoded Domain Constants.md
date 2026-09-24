---
kind: configuration_system
name: Minimal Environment-Driven Configuration with Hardcoded Domain Constants
category: configuration_system
scope:
    - '**'
source_files:
    - api/core.py
    - api/main.py
    - data/steg_districts.py
    - ingestion/weather_client.py
    - ingestion/pvgis_client.py
    - ingestion/synthetic_data.py
    - models/model_registry.py
---

## What system/approach is used

The repository uses a **minimal, environment-variable-only configuration approach** — there is no dedicated config file format (no `.env`, `config.yaml`, `settings.py`, or TOML/INI files). The only runtime configuration point is the `PRESOL_API_KEY` environment variable read via `os.environ.get()` in `api/core.py`. All other operational parameters are either hard-coded Python constants or derived from data modules.

There is no configuration loading framework, no settings class, no validation layer, and no configuration hierarchy (e.g. defaults → env → file). This is a deliberately lightweight setup for a single-process FastAPI service.

## Key files and packages

- `api/core.py` — sole configuration consumer: reads `PRESOL_API_KEY` from `os.environ` (line 45) with a fallback default of `"dev-key"`; defines absolute filesystem paths (`ROOT`, `MODEL_PATH`, `RESULTS_DIR`, `METER_BUFFER`, `RETRAIN_LOG`) computed relative to the module location; holds the API key header name `X-API-Key` as a string constant.
- `api/main.py` — FastAPI app assembly; no configuration passed in beyond title/description/version strings.
- `data/steg_districts.py` — domain configuration: contains all STEG district metadata (coordinates, capacities, dust loss, directions), national aggregates (`NATIONAL_ROOFTOP_PV_MWC`, `NATIONAL_TOTAL_INSTALLATIONS`, `NATIONAL_PENDING_DOSSIERS`), displacement factors, geometric defaults (`DEFAULT_PV_ORIENTATION`), saturation thresholds, and the full list of 50 commercial districts. This is the project's primary "configuration" of business/domain state.
- `ingestion/weather_client.py` — external service endpoints configured as module-level constants: `OPEN_METEO_URL`, `PVGIS_HOURLY_URL`, `HOURLY_VARS` list, and timezone `Africa/Tunis`.
- `ingestion/pvgis_client.py` — PVGIS endpoint and `DEFAULT_LOSS_PCT = 14.0` constant.
- `models/model_registry.py` — filesystem layout configuration: `REGISTRY_DIR = ROOT / "results" / "model_registry"`, plus fixed filenames `model_versions.json`, `training_runs.json`, `production_model.json`.
- `ingestion/synthetic_data.py` — synthetic weather generator used as a fallback when live weather APIs are unavailable; includes horizon noise buckets and physical constants (temperature coefficient `-0.0038`, system loss 14%, etc.).

## Architecture and conventions

1. **Environment variables are the only external configuration.** The only configurable secret is `PRESOL_API_KEY`, consumed at import time in `api/core.py`. There is no `.env` loader (no `python-dotenv` usage found anywhere).
2. **Paths are resolved relative to the source tree**, not via an application root setting. `ROOT = Path(__file__).resolve().parents[1]` is used in both `api/core.py` and `models/model_registry.py` to derive `results/`, `models/artifacts/`, etc. This ties deployment to a directory structure where these packages sit under the repo root.
3. **Domain configuration lives in Python modules, not config files.** `data/steg_districts.py` is effectively the authoritative configuration for all geographic, capacity, and policy parameters. It is imported directly by `api/core.py`, `reports/`, and `data/` scripts.
4. **External service URLs and timeouts are module-level constants.** Open-Meteo and PVGIS endpoints, variable lists, and HTTP timeouts are defined inline in `ingestion/weather_client.py` and `ingestion/pvgis_client.py`. There is no way to override them without editing source.
5. **Fallback behavior replaces configuration switches.** Instead of a `USE_SYNTHETIC_WEATHER=true` flag, `api/core.py` tries live weather first and silently falls back to `synthetic_data.generate_all()` on any exception, marking `_state["data_source"]` as `"live"` or `"synthetic"`. This is the project's feature-flag equivalent.
6. **Model registry uses immutable JSON files** under `results/model_registry/` with atomic writes (write to `.tmp` then `replace`). Production promotion enforces that candidate models must outperform current production MAE before being copied.
7. **No configuration validation exists.** Missing or malformed `PRESOL_API_KEY` simply results in the default `"dev-key"` being used; invalid model artifacts raise exceptions at runtime rather than at startup.

## Conventions and constraints

- **Only one environment variable is supported:** `PRESOL_API_KEY`. No other env vars are read anywhere in the codebase.
- **All paths assume a fixed repo layout:** `api/`, `models/`, `results/`, `data/` must exist relative to each other. Changing this layout requires editing multiple modules.
- **Domain constants are frozen in code:** District names, coordinates, capacities, and STEG policy ratios in `data/steg_districts.py` are the source of truth. They are described as "derived directly from STEG's official Tableau de Bord du Programme Prosol (Mars 2026)" — treated as authoritative reference data, not user-editable config.
- **External services have no retry or circuit-breaker configuration:** Open-Meteo/PVGIS calls use fixed timeouts (30s for async, 120s for PVGIS historical) and raise exceptions on failure; callers handle failures by falling back to synthetic data.
- **APScheduler jobs are hardcoded:** forecast refresh runs every 15 minutes (`minutes=15`) and retraining runs daily (`days=1`) during hours 5–20 local time. These intervals cannot be tuned without modifying source.
- **CORS is open:** `allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]` — no per-environment CORS configuration.