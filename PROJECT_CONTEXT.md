# Project Context: STEG National Rooftop PV Forecast Platform
### Paste this entire document into a new chat to give it full context on this project.

---

## 0. What this is, in one line

A national platform that forecasts Tunisia's rooftop solar power output days in advance, with real-time uncertainty and grid-decision support, so STEG (Tunisia's national electricity utility) can manage the electricity network more reliably.

## 1. The competition context

- **Event:** PESTGM 7.0 Technical Challenge — organized by the IEEE IAS/IES/PES ESPRIT Student Branch Joint Chapter, in partnership with STEG.
- **Track:** Track 1 — "National Intelligent Platform for Forecasting Rooftop Solar Production" (Track 2 was a separate load-shedding problem, not ours).
- **Timeline:** Preselection deliverables due **September 24, 2026** (GitHub repo + technical report max 10 pages + video demo, judged on creativity/relevance/feasibility). Top 10 teams advance to a final pitch day **October 3–4, 2026** (5-min live presentation + 2-min video + live prototype, judged partly on English fluency and delivery).
- **The official problem statement** (STEG's "Note Conceptuelle"): rooftop PV installations are growing fast in Tunisia and are now significant enough to affect the grid, but STEG's National Dispatching has no visibility into this decentralized production. STEG wants a platform forecasting aggregated rooftop PV production at district/governorate/national level, from intra-day to D+3, with uncertainty quantification, dashboards, interactive maps, automatic exchange with grid tools, and continuous learning from forecast-vs-actual error.

## 2. What was built — full architecture

**Backend** (Python/FastAPI, `api/main.py`):
- `GET /governorates` — 24 governorates with real capacity/backlog data
- `GET /districts`, `GET /status`, `GET /metrics`, `GET /history/national`
- `GET /forecast/national`, `/forecast/district/{d}`, `/forecast/districts`, `/forecast/governorate/{g}`
- `GET /forecast/map`, `/forecast/timelapse` (48-hour animation feed)
- CORS enabled; live weather with automatic fallback to synthetic data if unreachable

**Data layer** (`data/governorates.py`): 24 Tunisia governorates with coordinates, STEG district grouping, and — critically — **real data from STEG**, not a proxy: installed PV capacity and pending-connection backlog per governorate, aggregated from STEG's own "Tableau de Bord du Programme Prosol, Mars 2026" (their real internal program dashboard, shared directly with us), which reports figures across ~49 commercial sub-districts. We mapped those to our 24 governorates using real Tunisia delegation-to-governorate geography. National totals reconcile to within 0.3 MWc of STEG's own reported 456.0 MWc, and pending-connections match exactly (5,475).

**ML layer** (`models/`):
- `ml_forecast.py` — horizon-aware quantile gradient boosting (LightGBM, open-source), predicting P10/P50/P90 simultaneously. Key design choice: training data includes a `horizon_hours` feature with noise that scales with lead time, so the model learns that forecast uncertainty should widen the further out it predicts — not an arbitrary fixed band.
- `aggregation.py` — governorate → district → national roll-up with uncertainty propagation (sum-of-squares on half-widths).
- `retrain.py` — drift-detection continuous learning: compares recent error against a naive persistence baseline, retrains automatically if the model's edge shrinks.
- `history.py` — generates real held-out actual-vs-forecast track record.

**Data honesty (important to preserve when discussing this project):**
- Real: installed capacity, pending connections (from STEG), governorate geography.
- Real and live: weather forecasts (Open-Meteo) and historical irradiance (PVGIS-JRC), both free/keyless APIs, with automatic synthetic fallback if network access fails.
- Synthetic (built by us, not from an external dataset): hourly weather-to-production training history, since STEG hasn't shared real per-installation metering data. Generated via `ingestion/synthetic_data.py`, a physics-based simulator (temperature derating + regional dust/soiling loss, higher in the arid south).
- Real backtest results (not hand-picked): our model beats a persistence baseline at every forecast horizon, with the margin narrowing at longer horizons — the honest, expected pattern (current numbers: nowcast 0.15% nRMSE vs 0.34% persistence, down to D+3 at 0.43% vs 0.42%, roughly on par — real capacity concentration in a few governorates like Sfax and Medenine makes long-horizon forecasting genuinely harder, an honest side effect of using real data).

**Frontend** (`dashboard/index.html`, single self-contained file):
- Light "clean SaaS" visual theme: white background, Manrope (headings) + Inter (body) + JetBrains Mono (numbers) fonts, color-coded sections (amber=production/overview, indigo=map, violet=validation/analytics, teal=data, rose=alerts, emerald=impact).
- Sidebar navigation, 6 pages: **Overview** (hero KPI, district breakdown, smart alert banner), **Production Map** (Leaflet map + real weather popups + 48-hour animated time-lapse with play/scrub controls, built from real per-hour forecast data, not a canned animation), **Forecast & Simulator** (time-series chart with uncertainty bands + live what-if cloud-cover stress-test simulator sized in MW of extra reserve needed), **Model Validation** (real backtest table/chart + real 7-day actual-vs-forecast track record), **Impact & Recommendations** (auto-flagged reserve recommendations, estimated CO2/fuel-cost impact, and a real connection-backlog ranking by governorate), **Data & Methodology** (real Prosol program KPI table + full transparency notes on what's real vs. synthetic).
- **Live-connect layer**: on load, the dashboard tries fetching from a FastAPI backend at `http://localhost:8000` (configurable); if reachable, it replaces all embedded demo data with live data and shows "live" in the sidebar; if not, it falls back gracefully to embedded real data with no crash — this fallback is a deliberate reliability feature for demos with unreliable venue wifi, not a bug.
- **Opening splash screen**: dark scene with (a) a canvas-based procedurally-generated twinkling particle starfield, (b) a glowing cyan/teal wireframe outline of Tunisia rendered live from the same real GeoJSON geometry used on the map page (not a static image), with glowing dot markers at the real lat/lon of all 24 governorates, and a "camera descending" zoom-in CSS animation on load. Dismissed by scrolling the mouse wheel down (or swiping up on mobile) — the splash tracks scroll progress live and slides away; auto-dismisses after 10 seconds if untouched so a live demo never gets stuck; also dismissible by clicking.

**Supporting deliverables:**
- `README.md` — GitHub-ready, English, includes the real STEG data table, honest limitations section, architecture diagram description, quickstart commands.
- `report/technical_report.pdf` (generated via `report/generate_report.py` using reportlab + matplotlib) — 6 pages, includes a real architecture diagram, real capacity map, real connection-backlog chart, real backtest charts, and a "Platform at a glance" stats table — all generated from actual project data, not stock content. Still has `[team name]` / `[members]` placeholders to fill in.
- `demo/video_script.md` — both a ~2-3 minute preselection video script and a full final-pitch outline (title/problem/solution/demo/results/feasibility/close), in English since judging scores English fluency.
- `BUILD_PROMPT.md` — a full 7-phase deployment brief (repo hygiene → backend hardening → frontend decisions → actual hosting/domain/CI-CD → real-data integration path → monitoring → final QA) for turning the local prototype into a real deployed website later.

## 3. Known technical decisions and constraints worth knowing

- The dashboard is a **single self-contained HTML file** on purpose — deploys anywhere instantly, no build step, easy to open standalone for demos.
- A **published Claude.ai artifact link** exists for this project (a live, shareable preview), but Claude's published-page sandbox blocks external image hosts by CSP — so any hotlinked real photo won't load there (falls back gracefully); it works fine if self-hosted or opened locally.
- We evaluated and explicitly excluded **Prosol Thermique (CES / solar water heaters)** data from STEG's dashboard — out of scope, since Track 1 is specifically about PV forecasting, not thermal.
- CES/credit-financing details from STEG's Tableau de Bord were reviewed but intentionally not incorporated (not relevant to the forecasting problem).
- A previous packaging mistake once caused the dashboard HTML to contain a duplicated `<body>` (two copies of the whole page stacked) — this was found and fixed; if a future session inherits a copy of this file, it's worth a quick sanity check (`grep -c "<body>"` should return exactly 1).

## 4. What's left to do (action items, not code)

1. Fill in real team name/members/contact in `README.md` and `report/technical_report.pdf`.
2. Create a GitHub repository and push the full codebase (required deliverable).
3. Record the actual video demo following `demo/video_script.md`.
4. (Optional, not required) Deploy the backend + frontend as a real live website following `BUILD_PROMPT.md`, if pursuing a fully "live" public version beyond the local/demo setup.

## 5. How to run it (for a fresh environment)

```bash
pip install -r requirements.txt
python models/ml_forecast.py      # trains model, saves real backtest metrics
python models/history.py          # generates real track record
python models/retrain.py          # tests the drift-detection loop
uvicorn api.main:app --reload --port 8000   # starts the API
# open dashboard/index.html in a browser — works standalone, connects live if the API is running
```

## 6. Tone/approach to maintain if continuing this project

Throughout this project, the guiding principle has been **radical transparency about what's real vs. synthetic vs. estimated** — explicitly labeling proxy data, honestly reporting backtest numbers even when they show the model's advantage shrinking at longer horizons, and documenting assumptions rather than hiding them. This has been treated as a strength for the jury, not a weakness to minimize. Please keep that approach if asked to extend or modify anything.
