---
kind: build_system
name: Build & Artifact Management — Python/uvicorn FastAPI with Flat requirements.txt
category: build_system
scope:
    - '**'
source_files:
    - requirements.txt
    - api/main.py
    - models/ml_forecast.py
    - models/retrain.py
    - BUILD_PROMPT.md
    - README.md
---

## What system/approach is used

The repository has **no formal build system** (no Makefile, Dockerfile, CI pipeline, packaging script, or task runner). The project is a flat Python package served by `uvicorn` and a static HTML/JS dashboard. Development and deployment are driven by:
- `pip install -r requirements.txt` for dependency resolution.
- Direct invocation of entry-point scripts (`python models/ml_forecast.py`, `python models/retrain.py`, `uvicorn api.main:app --reload --port 8000`).
- A plain `dashboard/index.html` plus sibling `.html` pages that the browser loads directly — no frontend build step.

The only build-related artifact at the root is `requirements.txt`; everything else is source code and data.

## Key files and packages

- `requirements.txt` — single flat dependency list with **no version pins** (e.g. `numpy`, `pandas`, `lightgbm`, `fastapi`, `uvicorn`, `pydantic<3`, `apscheduler`, `python-dotenv`). This is the sole manifest controlling installed versions.
- `api/main.py` + `api/core.py` — FastAPI application entry point; launched via `uvicorn api.main:app`.
- `models/ml_forecast.py` — trains LightGBM quantile models and writes artifacts to `models/artifacts/quantile_models.joblib`.
- `models/retrain.py` — drift-detection / retraining script invoked manually.
- `dashboard/*.html` and `dashboard/assets/{css,js,data}` — static frontend assets loaded directly by browsers; no bundler.
- `results/model_registry/` — file-based model registry (`model_versions.json`, `production_model.json`, `training_runs.json`) plus `.joblib` artifacts under `artifacts/`.
- `BUILD_PROMPT.md` — a human-oriented build/deployment brief describing how to turn the prototype into a hosted site; it explicitly recommends adding `Dockerfile`, CI, pinned `requirements.txt`, etc., but these do not exist in the repo yet.

## Architecture and conventions

- **Single-process runtime**: the API runs as one `uvicorn` process per instance; there is no multi-service orchestration, reverse proxy, or container definition in the repo.
- **Model artifacts are filesystem-bound**: trained models are persisted as `.joblib` files under `models/artifacts/` and referenced by path from the API. There is no model server or remote registry.
- **Static frontend**: the dashboard is a collection of HTML/CSS/JS files with no compilation step; it connects to the backend via `fetch()` against a configurable base URL (currently defaults to `http://localhost:8000`).
- **Configuration via environment**: `python-dotenv` is listed as a dependency, and `BUILD_PROMPT.md` prescribes loading settings from `.env` (e.g. `OPEN_METEO_BASE_URL`, `PVGIS_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `MODEL_PATH`, `LOG_LEVEL`), though the current codebase still uses hard-coded values in several places.
- **No virtual environment committed**: `venv/` appears in the tree but is ignored by `.gitignore`; developers create their own local envs.

## Conventions and constraints

Observed conventions (descriptive):
- Dependencies are declared centrally in `requirements.txt` and installed with `pip install -r requirements.txt`.
- Scripts are executed directly with `python <script>.py`; there is no wrapper command or task runner.
- Model training outputs go to `results/` and `models/artifacts/`; evaluation summaries land in `results/forecast_evaluations/<run_id>/`.
- The dashboard falls back to embedded demo JSON when the live API is unreachable.

Enforced or documented rules (from authoritative sources in the repo):
- `BUILD_PROMPT.md` states that production deployment should use a `Dockerfile` based on `python:3.11-slim`, install `requirements.txt`, copy code, expose the port, and run via `uvicorn --host 0.0.0.0`. This is a prescribed convention for future builds, not currently implemented.
- `BUILD_PROMPT.md` requires `requirements.txt` pinning ("verify versions are pinned, not just named") — the current file does not yet comply.
- `BUILD_PROMPT.md` mandates environment-driven configuration (`OPEN_METEO_BASE_URL`, `PVGIS_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `MODEL_PATH`, `LOG_LEVEL`) loaded via `python-dotenv` or `pydantic-settings`, replacing hardcoded URLs.
- `BUILD_PROMPT.md` specifies that the trained model artifact (`models/artifacts/quantile_models.joblib`) must be included in any deployed build/container and that the API must return a clear 503 if the model is missing rather than crash.
- `README.md` documents the canonical development workflow: `pip install -r requirements.txt`, then `python models/ml_forecast.py`, optionally `python models/retrain.py`, then `uvicorn api.main:app --reload --port 8000`, followed by opening `dashboard/index.html`.

There is no CI/CD, no Makefile, no Dockerfile, no packaging (`setup.py`/`pyproject.toml`), and no cross-compilation strategy present in this repository.