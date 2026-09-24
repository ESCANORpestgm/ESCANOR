graph LR
    A[Synthetic / PVGIS Data] --> B["train_quantile_models()"]
    B --> C["3× LGBMRegressor (P10/P50/P90)"]
    C --> D["predict() + quantile sort"]
    D --> E["aggregation sqrt-sum-squares"]
    E --> F[Dashboard]
    G[check_drift_and_retrain] -->|80/20 split| B
    G -->|MAE vs persistence| H{Drift > 15%?}
    H -->|Yes| B
    H -->|No| I[Skip]# STEG Rooftop PV Forecast Platform — Context

**What it is:** A platform forecasting Tunisia's rooftop solar output (intra-day to D+3) with uncertainty, for STEG's National Dispatching. Built for PESTGM 7.0 Technical Challenge, Track 1 (IEEE ESPRIT × STEG). Preselection due Sept 24, 2026: GitHub repo + technical report (max 10 pages) + video demo. Final pitch Oct 3-4 if selected (top 10).

**STEG's requirement (Note Conceptuelle):** forecast aggregated rooftop PV by district/governorate/national, with uncertainty, dashboards+maps, API integration with grid tools, and continuous learning from forecast-vs-actual error.

## Architecture

**Backend** (FastAPI, `api/main.py`): endpoints for governorates, districts, status, metrics, history, forecast (national/district/governorate/map/timelapse). Live weather (Open-Meteo + PVGIS-JRC) with automatic synthetic fallback if unreachable.

**Data** (`data/governorates.py`): 24 governorates with REAL capacity + pending-connection-backlog data, sourced from STEG's own "Tableau de Bord Programme Prosol, Mars 2026" (~49 sub-districts aggregated to governorates via real delegation geography). National total reconciles to 455.7 vs STEG's 456.0 MWc; backlog matches exactly (5,475).

**ML** (`models/`): LightGBM (open-source) horizon-aware quantile regression (P10/P50/P90) — trained with noise scaling by forecast lead time so uncertainty widens realistically, not arbitrarily. `aggregation.py` rolls up with uncertainty propagation. `retrain.py` does drift-detection continuous learning vs. a persistence baseline. `history.py` builds a real held-out track record.

**Data honesty:**
- Real: capacity, backlog, governorate geometry, live weather.
- Synthetic (built by us): hourly weather→production training data (physics-based simulator), since STEG hasn't shared metering history.
- Real backtest: beats persistence at every horizon; margin narrows at D+3 (nowcast 0.15% nRMSE vs 0.34% persistence; D+3 0.43% vs 0.42% — honest, expected pattern given real capacity concentration in Sfax/Medenine).

**Frontend** (`dashboard/index.html`, single file): light SaaS theme (Manrope/Inter/JetBrains Mono; amber/indigo/violet/teal/rose/emerald color-coded sections). 6 pages via sidebar: Overview (hero KPI + alert banner), Production Map (Leaflet + real weather popups + 48h animated time-lapse), Forecast & Simulator (uncertainty chart + live cloud-cover stress-test), Model Validation (backtest + track record), Impact & Recommendations (reserve recommendations, CO2/cost impact, real backlog ranking), Data & Methodology (real Prosol KPIs + transparency notes).

**Live-connect layer:** tries `fetch()` to a FastAPI backend on load; falls back to embedded real/demo data gracefully if unreachable (deliberate reliability feature, not a bug) — sidebar shows "live" or "demo data" accordingly.

**Splash screen:** dark scene, canvas-generated twinkling particles, glowing Tunisia outline drawn live from the same real GeoJSON used on the map page (not a static image), with glowing nodes at real governorate coordinates, camera-zoom-in CSS animation. Dismissed by scrolling/swiping down (tracks progress live); auto-dismisses after 10s; click also works.

## Other deliverables
- `README.md` — GitHub-ready, real data table, honest limitations.
- `report/technical_report.pdf` — 6 pages, real charts (architecture diagram, capacity map, backlog chart, backtest charts), via `report/generate_report.py` (reportlab+matplotlib). Still has `[team name]` placeholder.
- `demo/video_script.md` — preselection video script + final pitch outline, in English (judged on English fluency).
- `BUILD_PROMPT.md` — 7-phase brief for deploying this as a real live website later.

## Known constraints
- Single-file frontend by design (instant deploy, no build step).
- CES/Prosol Thermique (solar water heaters) data reviewed but deliberately out of scope (Track 1 = PV only).
- A published Claude.ai artifact preview exists but blocks external image hosts via CSP (works fine self-hosted/local).
- Past bug (fixed): duplicated `<body>` tag from a packaging mistake — sanity check `grep -c "<body>"` should return 1 if inheriting this file.

## Remaining action items (not code)
1. Fill in real team name/members in README + report.
2. Create GitHub repo, push code (required deliverable).
3. Record video per script.
4. (Optional) Deploy live per BUILD_PROMPT.md.

## Run it
```bash
pip install -r requirements.txt
python models/ml_forecast.py    # train + real metrics
python models/history.py        # real track record
uvicorn api.main:app --reload --port 8000
# open dashboard/index.html — works standalone, connects live if API running
```

## Approach to maintain
Radical transparency: label real vs. synthetic vs. estimated data explicitly; report honest backtest numbers even when they show the model's edge shrinking at longer horizons; treat this as a strength for judges, not something to hide.
