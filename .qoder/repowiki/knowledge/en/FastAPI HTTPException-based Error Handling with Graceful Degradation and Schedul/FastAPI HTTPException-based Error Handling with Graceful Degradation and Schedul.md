---
kind: error_handling
name: FastAPI HTTPException-based Error Handling with Graceful Degradation and Scheduled Task Logging
category: error_handling
scope:
    - '**'
source_files:
    - api/main.py
    - api/core.py
    - api/routers/forecast.py
    - api/routers/diagnostics.py
    - api/routers/reports.py
---

## Overview

The PréSol PV Forecast Platform uses FastAPI's built-in `HTTPException` as its primary error signaling mechanism for the REST API layer. There is no custom exception hierarchy, no centralized exception handler registered via `@app.exception_handler`, and no dedicated `errors/` package. Errors are raised inline in route handlers and background tasks, converted to appropriate HTTP status codes, and logged via `print()` statements in scheduled/background contexts.

## API Layer: HTTPException Usage

- **Authentication errors**: `api/core.py::require_api_key` raises `HTTPException(status_code=403, detail="Invalid or missing X-API-Key header.")` when the `X-API-Key` header does not match the `PRESOL_API_KEY` environment variable.
- **Client/validation errors**: Routers raise `HTTPException(400, ...)` for malformed input — e.g. `reports.py` wraps a downstream `ValueError` from `add_installation_update` into a 400 response; `reports.py::import_prosol_history_snapshot` rejects snapshot paths that escape the project root.
- **Not-found errors**: The most common pattern is checking existence of files/datasets and raising `HTTPException(404, "...")` with a human-readable message, used across `diagnostics.py`, `reports.py`, and `forecast.py` (e.g. unknown district/direction/governorate, missing Prosol snapshot, missing forecast evaluation).
- **Service-unavailable errors**: `forecast.py::forecast_intraday` returns 503 when no forecast data is available for the next 6 hours.
- **Internal server errors**: `diagnostics.py::model_validation` catches `OSError` / `json.JSONDecodeError` while reading model validation metrics and re-raises as `HTTPException(500, "Model validation metrics could not be read.")`.

There is no global exception-to-HTTP mapping middleware; each route handler decides the appropriate status code at the point of failure.

## Background and Lifecycle Error Handling

Background work (APScheduler jobs, lifespan startup) swallows exceptions rather than propagating them:

- `api/core.py::lifespan`: imports generated snapshots inside a `try/except Exception` block and prints `[Prosol history] snapshot import failed: {error}` on failure, allowing the app to start even if snapshot import fails.
- `api/core.py::scheduled_refresh` and `scheduled_retrain`: wrap their work in `try/except Exception as error` and print `[scheduler] forecast refresh/retraining failed: {error}`. This prevents a failing background job from crashing the process.
- `api/core.py::build_forecast`: attempts live weather ingestion first; any exception falls through to synthetic data generation (`generate_all`) and marks `_state["data_source"] = "synthetic"`. This is a deliberate graceful-degradation strategy so the API keeps responding even when external weather APIs fail.

## No Centralized Error Types or Middleware

- No custom exception classes exist anywhere in the codebase.
- No `app.add_exception_handler(...)` is present in `api/main.py`; only `CORSMiddleware` is added.
- No structured logging framework is configured — failures in background tasks use plain `print()`, and there is no file-based log sink visible in the API code.
- The dashboard frontend has no explicit error-handling module beyond generic JavaScript alerting utilities under `dashboard/assets/js/alerts.js`.

## Conventions Observed

1. **Route handlers raise `HTTPException` directly** with an integer status code and a string `detail` message — never return raw Python exceptions.
2. **Domain-layer functions raise domain-specific exceptions** (e.g. `ValueError` in `reports.prosol_updates.add_installation_update`) and the router catches them to convert to a 400 `HTTPException`.
3. **Missing resources are treated as 404**, not 500 — whether it is a missing CSV, JSON, database snapshot, or forecast evaluation.
4. **External dependencies fail open**: `build_forecast` treats weather client failure as a signal to fall back to synthetic data rather than surfacing an error to the caller.
5. **Scheduled tasks never propagate exceptions**: all background jobs catch `Exception` broadly and log via `print`, ensuring scheduler crashes do not take down the service.
6. **Auth failures are 403**, not 401, using a shared `Security` dependency (`require_api_key`).
7. **Input validation errors are 400**, resource-not-found errors are 404, and I/O-read failures during diagnostics are elevated to 500.