# Master Build Prompt — STEG National Rooftop PV Forecast Platform
### From local prototype to a deployed production website

Copy everything below into Claude Code (or hand to a developer) as the project brief. It assumes the existing codebase (Python/FastAPI backend + single-file HTML/JS dashboard) is the starting point and describes everything needed to turn it into a real, hosted, production-grade website.

---

## 0. Context and goal

I have a working prototype: a Python/FastAPI backend that forecasts Tunisia's rooftop solar (PV) production, and a single-file HTML/JS dashboard that displays it. It currently only runs locally (`uvicorn` on localhost + opening an HTML file in a browser). I want to turn this into a real, deployed website that STEG (Tunisia's national electricity utility) could actually use, reachable at a real URL, with a live backend, without breaking anything that already works.

Do not rewrite the forecasting logic, the ML model, or the data pipeline — they are already built and tested. Your job is architecture, deployment, hardening, and polish: take what exists and make it production-ready.

---

## 1. What already exists (do not rebuild these)

**Backend** (`api/main.py`, FastAPI):
- `GET /` — health/info
- `GET /governorates` — 24 Tunisia governorates: name, district, lat/lon, real installed_capacity_mwc, real pending_connections, dust_loss_pct
- `GET /districts` — 7 STEG operational district groupings
- `GET /status` — whether the backend is running on live weather or synthetic fallback
- `GET /metrics` — real backtest results (nRMSE vs persistence/clear-sky baselines by horizon)
- `GET /history/national` — real actual-vs-forecast track record, last 7 days
- `GET /forecast/national?horizon_days=3`
- `GET /forecast/district/{district}?horizon_days=3`
- `GET /forecast/districts?horizon_days=3` (all districts at once)
- `GET /forecast/governorate/{governorate}?horizon_days=3`
- `GET /forecast/map?horizon_hours=0` — full governorate snapshot with weather
- `GET /forecast/timelapse?hours=48` — 48 hourly frames for map animation

**Data layer** (`data/governorates.py`): REAL installed capacity and pending-connection-backlog data per governorate, sourced from STEG's own "Tableau de Bord du Programme Prosol, Mars 2026," aggregated from their 49 commercial sub-districts. National totals reconcile to within 0.3 MWc of STEG's reported figures.

**ML layer** (`models/ml_forecast.py`, `models/aggregation.py`, `models/retrain.py`, `models/history.py`): horizon-aware quantile gradient boosting (LightGBM, P10/P50/P90), trained so uncertainty widens realistically with forecast lead time; district/national aggregation with uncertainty propagation; drift-detection continuous-learning loop comparing against a persistence baseline.

**Weather ingestion** (`ingestion/weather_client.py`, `ingestion/synthetic_data.py`): real Open-Meteo (forecast) and PVGIS-JRC (historical) integration, with automatic fallback to a physics-based synthetic generator if network access fails.

**Frontend** (`dashboard/index.html`): single-file HTML/CSS/JS, light "clean SaaS" theme (Manrope + Inter + JetBrains Mono fonts; amber/indigo/violet/teal/rose/emerald color-coded sections), sidebar navigation across 6 views — Overview, Production Map (with 48h animated time-lapse), Forecast & Simulator (what-if cloud-cover stress test), Model Validation (backtest + track record), Impact & Recommendations (reserve recommendations, CO2/cost impact, real connection-backlog ranking), Data & Methodology (real Prosol program KPIs + transparency notes). It currently embeds demo data directly in the HTML and, when opened in a browser with the API running locally, upgrades itself to live data via `fetch()` calls to `http://localhost:8000` with automatic fallback if unreachable.

---

## 2. High-level architecture for the deployed version

```
┌─────────────────┐      HTTPS       ┌──────────────────────┐
│  Frontend        │ ───────────────▶ │  Backend API          │
│  (static site,   │  fetch() calls   │  (FastAPI, containerized)│
│  React or plain  │ ◀─────────────── │  hosted on a real URL │
│  HTML/JS)         │      JSON        │  e.g. api.yourdomain  │
└─────────────────┘                  └───────────┬──────────┘
                                                   │
                                    ┌──────────────┴───────────────┐
                                    │  Data layer                   │
                                    │  - governorates.py (static)   │
                                    │  - trained model (.joblib)    │
                                    │  - Open-Meteo / PVGIS (live)  │
                                    │  - (future) STEG metering DB  │
                                    └───────────────────────────────┘
```

Two independently deployable pieces: **backend API** (Python) and **static frontend** (HTML/CSS/JS — can stay a single file or be restructured into a small React/Vite app, your call, but keep the visual design and all 6 dashboard views intact).

---

## 3. Step-by-step build plan

### Phase 1 — Repository and environment hygiene
1. Initialize a proper git repository if not already one; add a `.gitignore` (Python venv, `__pycache__`, `.env`, `node_modules` if applicable, `models/artifacts/*.joblib` optionally kept via Git LFS since it's a binary model file).
2. Split configuration from code: create a `.env.example` with `OPEN_METEO_BASE_URL`, `PVGIS_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `MODEL_PATH`, `LOG_LEVEL`. Load via `python-dotenv` or `pydantic-settings`. Never hardcode the frontend's `API_BASE = 'http://localhost:8000'` — make it configurable per environment (local/staging/production).
3. Add `requirements.txt` pinning (already exists — verify versions are pinned, not just named) and consider a `Dockerfile` for the backend (Python 3.11-slim base, install requirements, copy code, expose port, run via `uvicorn` with `--host 0.0.0.0`).

### Phase 2 — Backend hardening for production
4. **CORS**: replace the current `allow_origins=["*"]` with an explicit allow-list read from environment config (your deployed frontend's real domain), since wildcard CORS is unsafe once this is public.
5. **Error handling**: audit every endpoint for proper HTTP status codes and JSON error bodies (not raw stack traces) on failure — especially the weather-fetch fallback path and missing-model-file cases.
6. **Rate limiting**: add basic rate limiting (e.g. `slowapi`) on public endpoints to prevent abuse, especially the weather-proxying ones.
7. **Health check endpoint**: add `GET /health` returning `{"status": "ok", "model_loaded": true/false, "data_source": "live"/"synthetic"}` for uptime monitoring and container orchestration health checks.
8. **Logging**: replace print statements with structured logging (Python `logging` module), including request logging and forecast-generation timing.
9. **Caching**: the live weather fetch + model inference on every request is expensive at scale — add a short-TTL cache (5–15 minutes) per governorate/horizon combination (in-memory `cachetools` is fine for a single-instance deployment; Redis if you expect multiple backend instances).
10. **Model artifact handling**: ensure `models/artifacts/quantile_models.joblib` is included in the deployed container/build (via Git LFS, a build step that runs `python models/ml_forecast.py`, or bundled directly) — the API must not crash if this file is briefly missing; return a clear 503 instead.
11. **Scheduled retraining**: wire `models/retrain.py`'s drift-check into an actual schedule (cron job, GitHub Action, or a background task/Celery beat) instead of manual invocation — daily or weekly, logging whether a retrain was triggered.
12. **API documentation**: FastAPI's automatic `/docs` (Swagger) is already free — just confirm it's reachable at the deployed URL and is not blocked by the reverse proxy/CORS config.

### Phase 3 — Frontend: decide single-file vs. restructured app
13. **Recommended default**: keep it as a single self-contained HTML file if the team is not comfortable with a JS build toolchain — it deploys trivially to any static host and has zero build step. Only restructure into a React/Vite app if you specifically want component reuse, TypeScript, or a design system library; if you do, preserve every existing page, color system, and font choice exactly, and re-implement the Leaflet map, Chart.js charts, and the 48-hour time-lapse animation faithfully.
14. **Environment-aware API base URL**: replace the hardcoded `const API_BASE = 'http://localhost:8000'` with a value injected at build/deploy time (e.g. a `<meta>` tag, a small `config.js` loaded before the main script, or a Vite `.env` variable) so the same code works in local dev and production without manual edits.
15. **Loading and error states**: add a visible "connecting to live backend…" indicator during `connectToLiveBackend()`, and make the existing "demo data (embedded)" vs "live" sidebar pill more prominent so users always know which data they're looking at.
16. **Responsive/mobile check**: verify the sidebar layout, map, and charts degrade gracefully on tablet/mobile widths (STEG staff may check this on a phone) — add a collapsible sidebar or bottom-tab-bar fallback below ~768px if not already handled.
17. **Accessibility pass**: keyboard navigation for the sidebar tabs, sufficient color contrast (the light theme should already be reasonable — verify with a contrast checker), `alt`/`aria-label` attributes on icon-only buttons (play/pause on the time-lapse, nav icons).
18. **Language**: the dashboard is currently English-only (per final-pitch judging requirements). For a real STEG-facing production tool, add a French toggle at minimum (STEG's internal reports and the Prosol dashboard itself are in French) — either a simple object-based i18n dictionary swapped by a toggle button, or a proper i18n library if restructured into a JS framework.

### Phase 4 — Deployment
19. **Backend hosting**: deploy the FastAPI app to a platform that supports long-running Python processes and can hold the trained model in memory — Render, Railway, Fly.io, or a small VPS with Docker + a reverse proxy (Caddy or Nginx) for automatic HTTPS. Avoid pure serverless functions (cold starts + model loading time is a bad fit) unless you specifically optimize for it.
20. **Frontend hosting**: deploy the static HTML (or built React app) to Vercel, Netlify, GitHub Pages, or Cloudflare Pages — all support custom domains and free HTTPS with zero server management.
21. **Domain and HTTPS**: register or use an existing domain; point a subdomain (e.g. `pv-forecast.yourdomain.tn` or similar) at the frontend, and `api.yourdomain.tn` at the backend. Ensure both serve over HTTPS (all the platforms above provide this automatically).
22. **CORS final wiring**: once both are deployed with real URLs, update the backend's CORS allow-list to the frontend's real production domain (and keep `localhost` allowed for local development).
23. **CI/CD**: add a GitHub Actions workflow (or equivalent) that runs on push to `main`: install dependencies, run any existing tests, retrain/validate the model if data changed, then deploy backend and frontend automatically. At minimum, auto-deploy on merge to main.
24. **Secrets management**: if any API keys are added later (e.g. a paid weather provider, an email/alerting service), store them in the hosting platform's secret manager — never commit them to the repository.

### Phase 5 — Data path to real production data
25. **Real metering data**: when STEG provides actual hourly production metering (not just the capacity/backlog snapshot already integrated), replace `ingestion/synthetic_data.py`'s training-data generation with a real data-loading module reading from wherever STEG exports it (CSV drop, database, or API) — the model, aggregation, and API code do not need to change, only the data-loading layer, exactly as already documented in `README.md`.
26. **Persistent storage**: move `results/metrics_by_horizon.csv` and `results/history_national.csv` from flat files to a small database (SQLite is enough at this scale; PostgreSQL if you expect concurrent writes) so the retraining job can update them safely without file-locking issues in a deployed environment.
27. **STEG systems integration**: if/when STEG wants to consume this from their own internal tools (the "automatic exchange with grid/load-forecasting tools" requirement), document the REST/JSON contract clearly (OpenAPI spec is auto-generated by FastAPI at `/openapi.json`) and discuss authentication (API key or OAuth) before opening the API beyond the dashboard itself.

### Phase 6 — Monitoring and reliability
28. **Uptime monitoring**: add an external uptime check (UptimeRobot, Better Uptime, or similar free tier) pinging the `/health` endpoint every few minutes, alerting if the backend goes down.
29. **Error tracking**: integrate a lightweight error-tracking tool (Sentry free tier) on the backend to catch and alert on unhandled exceptions in production, especially around the live-weather fallback logic.
30. **Analytics** (optional, only if appropriate for an internal STEG tool): basic, privacy-respecting page-view analytics (Plausible or a self-hosted alternative) to understand which dashboard views are actually used.

### Phase 7 — Final QA before calling it done
31. Test the full flow end-to-end on the real deployed URLs: open the frontend, confirm the sidebar shows "live," click through all 6 pages, run the time-lapse animation, drag the what-if simulator slider, and confirm numbers update.
32. Test the fallback path deliberately: stop the backend and reload the frontend — confirm it falls back to embedded demo data without crashing or showing a blank page.
33. Load-test the backend lightly (even a simple script hitting `/forecast/national` 50 times) to catch any obvious performance cliff before a live demo.
34. Confirm HTTPS, custom domain, and CORS all work together with no browser console errors.
35. Write a short `DEPLOYMENT.md` documenting exactly how to redeploy (in case someone else on the team needs to update it later) — hosting provider, environment variables required, and the retraining/update cadence.

---

## 4. Constraints and things to preserve exactly

- Do not change the visual design system: light background, Manrope/Inter/JetBrains Mono fonts, the amber/indigo/violet/teal/rose/emerald color coding per section.
- Do not remove the "demo data (embedded)" fallback — it is a deliberate reliability feature for live demos with unreliable venue wifi, not a bug to clean up.
- Do not alter the real STEG data already integrated in `data/governorates.py` (installed capacity, pending connections) without a documented reason.
- Keep the honest-baseline framing throughout (nRMSE vs. persistence and clear-sky, explicitly labeled real vs. synthetic data) — this transparency is a deliberate design choice for STEG's trust and for hackathon judging, not something to simplify away.

## 5. Deliverable

At the end of this work: a live, HTTPS, custom-domain website where anyone (or authorized STEG staff, depending on final access decisions) can open the URL and see the exact same dashboard that currently only runs locally — fully connected to a live, monitored, auto-deploying backend, with a documented path for STEG to eventually plug in their real metering data.
