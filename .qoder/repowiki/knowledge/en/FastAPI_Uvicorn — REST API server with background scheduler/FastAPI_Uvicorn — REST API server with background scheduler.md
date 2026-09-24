---
kind: external_dependency
name: FastAPI/Uvicorn — REST API server with background scheduler
slug: fastapi-uvicorn
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---


- Framework behavior: lifespan hook imports Prosol report snapshots into SQLite and starts an APScheduler `BackgroundScheduler` that runs a 15-minute forecast refresh job and a daily retraining job; the scheduler is stored on `app.state.scheduler` and shut down on app exit.
- Integration point: routers under `api/routers/` (forecast, learning, diagnostics, meta, reports) register routes against this single app; the same JSON contract is what STEG grid-operation tools consume.
- Concurrency note: shared state (`_state["models"]`, cache, data_source) is guarded by a `threading.Lock` (`refresh_lock`) but read paths outside the lock can race with mutations — any new route should acquire the lock around cache writes.