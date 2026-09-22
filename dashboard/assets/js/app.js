/* ============================================================
   PréSol Dashboard — app.js v3 (STEG Prosol 50-District Release)
   STEG National PV Forecast Platform
   Features:
   - 50 STEG Commercial Districts & 7 Directions de Distribution
   - Prosol Multi-Vector Energy & Fuel Displacement Strip
   - Gross Generation ↔ Net Grid Injection (64.07%) toggle
   - Prosol Report Studio Modal with official KPIs and JSON export
   - Spatial map drilldown with live solar irradiance (GHI), temp, wind, clouds
   - 7-Direction Regional Weather Snapshot Grid
   - Hourly Model Prediction Breakdown (P10/P50/P90 Quantiles)
   - Dynamic Capacity Backlog Pipeline with 30d/90d growth projections
   - Saturation and reverse-flow feeder monitoring
   ============================================================ */

const API_BASE = 'http://localhost:8000';

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
    text:    '#2D2B28',
    muted:   '#7A7771',
    primary: '#DA7756',
    fill:    'rgba(218, 119, 86, 0.12)',
    net:     '#0ea5e9',
    netFill: 'rgba(14, 165, 233, 0.12)',
    good:    '#517A63',
    warn:    '#D9A05B',
    bad:     '#C0392B',
    bg:      '#FFFFFF',
    border:  '#E6E4DD',
};
Chart.defaults.color         = C.muted;
Chart.defaults.font.family   = "'Inter', -apple-system, sans-serif";
Chart.defaults.font.size     = 12;

// ── i18n ────────────────────────────────────────────────────────────────────
const I18N = {
    en: {
        'brand-sub':          'STEG PV Forecasting',
        'nav-national':       'National Overview',
        'nav-regional':       'Regional Analysis',
        'nav-map':            'Spatial Timelapse',
        'nav-perf':           'Model Health',
        'nav-alerts':         'Alerts',
        'nav-registry':       'Park Registry',
        'nav-prosol-report':  'STEG Prosol Report',
        'home-title':         'National Overview',
        'home-sub':           'Aggregated generation forecast for the Tunisian national grid (J to J+3) across 50 STEG commercial districts.',
        'kpi-current':        'Current Estimated Output',
        'kpi-today':          'Peak Forecast (Today)',
        'kpi-tmrw':           'Peak Forecast (Tomorrow)',
        'kpi-capacity':       'Installed Capacity',
        'chart-national-title': 'National PV Generation Forecast',
        'chart-intraday-title': 'Intra-Day Forecast (15-min resolution)',
        'districts-title':    'Regional Analysis',
        'districts-sub':      'Granular P10/P50/P90 forecasts across 50 STEG commercial districts and 7 Directions de Distribution with detailed model predictions.',
        'map-title':          'Spatial Timelapse Map',
        'map-sub':            'Interactive spatial map of all 50 STEG commercial districts. Click any circle to drill down into weather and 72-hour forecast.',
        'perf-title':         'Model Health & Diagnostics',
        'perf-sub':           'Backtesting results and continuous learning retrain history.',
        'perf-hist-title':    'Historical Accuracy (Last 30 Days)',
        'perf-metrics-title': 'Quantile Model Metrics (By Horizon)',
        'perf-retrain-title': 'Continuous Learning — Retrain Log',
        'alerts-title':       'Operational Alerts',
        'alerts-sub':         'Real-time warnings for Dispatching National including reverse flow and feeder saturation risks.',
        'alerts-thresholds':  'Alert Thresholds',
        'alerts-active':      'Active Alerts',
        'alerts-info':        'Alert Types Explained',
        'registry-title':     'PV Park Registry & Pipeline',
        'registry-sub':       'Official data for all 50 STEG commercial districts and dynamic capacity expansion projections.',
        'registry-table-title': 'District Inventory',
        'registry-cards-title': 'Capacity by Direction',
        'districts-label':    'Commercial Districts',
        'filter-all':         'All',
        'table-district':     'District',
        'table-direction':    'Direction',
        'table-capacity':     'Capacity (MWc)',
        'table-peak':         'Peak J+1',
        'search-district-placeholder': '🔍 Search a STEG district…',
        'select-district':    'Select a district',
        'model-detail':       '🔬 Model Prediction Details (P10 / P50 / P90 & Weather)',
        'next-48-hours':      'Next 48 hours',
        'peak-pessimistic':   'P10 (Pessimistic)',
        'peak-median':        'P50 (Median)',
        'peak-optimistic':    'P90 (Optimistic)',
        'peak-hour':          'J+1 Peak Hour',
    },
    fr: {
        'brand-sub':          'Prévision PV STEG',
        'nav-national':       'Vue nationale',
        'nav-regional':       'Analyse régionale',
        'nav-map':            'Carte spatio-temporelle',
        'nav-perf':           'Santé du modèle',
        'nav-alerts':         'Alertes',
        'nav-registry':       'Registre du parc',
        'nav-prosol-report':  'Rapport STEG Prosol',
        'home-title':         'Vue nationale',
        'home-sub':           'Prévision agrégée sur le réseau national (J à J+3) couvrant les 50 districts commerciaux STEG.',
        'kpi-current':        'Production estimée actuelle',
        'kpi-today':          'Pic prévu (aujourd\'hui)',
        'kpi-tmrw':           'Pic prévu (demain)',
        'kpi-capacity':       'Puissance raccordée',
        'chart-national-title': 'Prévision de production PV nationale',
        'chart-intraday-title': 'Prévision intra-journalière (résolution 15 min)',
        'districts-title':    'Analyse régionale',
        'districts-sub':      'Prévisions granulaires P10/P50/P90 par district commercial et Direction avec décomposition des quantiles.',
        'map-title':          'Carte spatio-temporelle',
        'map-sub':            'Carte interactive des 50 districts STEG avec météo solaire en direct et bandes d\'incertitude.',
        'perf-title':         'Santé & diagnostics du modèle',
        'perf-sub':           'Résultats de backtest et historique du réapprentissage continu.',
        'perf-hist-title':    'Précision historique (30 derniers jours)',
        'perf-metrics-title': 'Métriques du modèle quantile (par horizon)',
        'perf-retrain-title': 'Apprentissage continu — journal de réentraînement',
        'alerts-title':       'Alertes opérationnelles',
        'alerts-sub':         'Avertissements en temps réel pour le Dispatching National dont saturation de départs.',
        'alerts-thresholds':  'Seuils d\'alerte',
        'alerts-active':      'Alertes actives',
        'alerts-info':        'Types d\'alertes',
        'registry-title':     'Registre Prosol & Pipeline STEG',
        'registry-sub':       'Données officielles des 50 districts commerciaux STEG et projection dynamique des raccordements.',
        'registry-table-title': 'Inventaire des districts',
        'registry-cards-title': 'Capacité par Direction',
        'districts-label':    'Districts commerciaux',
        'filter-all':         'Tous',
        'table-district':     'District',
        'table-direction':    'Direction',
        'table-capacity':     'Cap (MWc)',
        'table-peak':         'Pic J+1',
        'search-district-placeholder': '🔍 Rechercher un district STEG…',
        'select-district':    'Sélectionnez un district',
        'model-detail':       '🔬 Détail des prédictions du modèle (P10 / P50 / P90 & météo)',
        'next-48-hours':      'Prochaines 48 heures',
        'peak-pessimistic':   'P10 (Pessimiste)',
        'peak-median':        'P50 (Médian)',
        'peak-optimistic':    'P90 (Optimiste)',
        'peak-hour':          'Heure de pic J+1',
    },
    ar: {
        'brand-sub':          'توقعات الطاقة الشمسية — الستاغ',
        'nav-national':       'نظرة عامة وطنية',
        'nav-regional':       'تحليل جهوي',
        'nav-map':            'خريطة التوزيع الزمني',
        'nav-perf':           'صحة النموذج',
        'nav-alerts':         'التنبيهات',
        'nav-registry':       'سجل المنظومات',
        'nav-prosol-report':  'تقرير بروسول الرسمي',
        'home-title':         'نظرة عامة وطنية',
        'home-sub':           'توقعات الإنتاج الوطني المربوط بالشبكة (من اليوم إلى 3 أيام قادمة) عبر 50 إقليماً تجارياً للستاغ.',
        'kpi-current':        'الإنتاج التقديري الحالي',
        'kpi-today':          'الذروة المتوقعة (اليوم)',
        'kpi-tmrw':           'الذروة المتوقعة (غداً)',
        'kpi-capacity':       'القدرة الجملية المركبة',
        'chart-national-title': 'توقعات الإنتاج الوطني للطاقة الشمسية',
        'chart-intraday-title': 'التوقعات خلال اليوم (دقة 15 دقيقة)',
        'districts-title':    'التحليل الجهوي بالأقاليم',
        'districts-sub':      'توقعات مفصلة P10/P50/P90 للأقاليم التجارية الخمسين للستاغ.',
        'map-title':          'الخريطة التفاعلية للأقاليم',
        'map-sub':            'توزيع جغرافي مباشر لإنتاج وأحوال الطقس لـ 50 إقليماً تجارياً للستاغ.',
        'perf-title':         'صحة النموذج والتشخيص',
        'perf-sub':           'نتائج الاختبار التاريخي وسجل إعادة التدريب التلقائي.',
        'perf-hist-title':    'الدقة التاريخية (آخر 30 يوماً)',
        'perf-metrics-title': 'مؤشرات دقة النموذج حسب الأفق',
        'perf-retrain-title': 'التعلم المستمر — سجل إعادة التدريب',
        'alerts-title':       'تنبيهات مركز التحكم الوطني',
        'alerts-sub':         'تحذيرات فورية لتشغيل الشبكة الكهربائية وخطر تدفق الطاقة العكسي.',
        'alerts-thresholds':  'عتبات التنبيه',
        'alerts-active':      'التنبيهات النشطة',
        'alerts-info':        'شرح التنبيهات',
        'registry-title':     'سجل الأقاليم ومخطط التوسعة',
        'registry-sub':       'بيانات رسمية لـ 50 إقليماً تجارياً ومخطط ربط الملفات العالقة.',
        'registry-table-title': 'قائمة الأقاليم',
        'registry-cards-title': 'القدرة حسب إدارة التوزيع',
        'districts-label':    'الأقاليم التجارية',
        'filter-all':         'الكل',
        'table-district':     'الإقليم',
        'table-direction':    'الإدارة',
        'table-capacity':     'القدرة (ميغاواط)',
        'table-peak':         'الذروة غ+1',
        'search-district-placeholder': '🔍 ابحث عن إقليم تابع للستاغ…',
        'select-district':    'اختر إقليماً',
        'model-detail':       '🔬 تفاصيل توقعات النموذج (P10 / P50 / P90 والطقس)',
        'next-48-hours':      'الساعات الـ48 القادمة',
        'peak-pessimistic':   'P10 (متشائم)',
        'peak-median':        'P50 (متوسط)',
        'peak-optimistic':    'P90 (متفائل)',
        'peak-hour':          'ساعة الذروة غ+1',
    }
};

const SUPPORTED_LANGS = Object.freeze(Object.keys(I18N));
let currentLang = SUPPORTED_LANGS.includes(localStorage.getItem('presol-lang'))
    ? localStorage.getItem('presol-lang')
    : 'en';

function applyI18n(lang) {
    const safeLang = SUPPORTED_LANGS.includes(lang) ? lang : 'en';
    currentLang = safeLang;
    localStorage.setItem('presol-lang', safeLang);
    document.documentElement.lang = safeLang;
    document.documentElement.dir  = safeLang === 'ar' ? 'rtl' : 'ltr';

    document.querySelectorAll('.lang-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.lang === safeLang);
    });

    const dict = I18N[safeLang];
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const value = dict[el.getAttribute('data-i18n')];
        if (!value) return;

        // Preserve badges, icons, and other nested markup inside translated headings.
        if (el.children.length) {
            const textNode = [...el.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
            if (textNode) textNode.textContent = value;
        } else {
            el.textContent = value;
        }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const value = dict[el.getAttribute('data-i18n-placeholder')];
        if (value) el.placeholder = value;
    });
}

// ── Chart Helper ────────────────────────────────────────────────────────────
const _chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: C.bg,
            titleColor: C.text,
            bodyColor: C.muted,
            borderColor: C.border,
            borderWidth: 1,
            padding: 10,
            boxPadding: 4,
            usePointStyle: true,
        },
    },
    scales: {
        x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 8, maxRotation: 0 },
        },
        y: {
            grid: { color: 'rgba(230, 228, 221, 0.6)' },
            border: { display: false },
            beginAtZero: true,
            ticks: { callback: v => `${v} MW` },
        },
    },
};

function makeChart(ctx, extraConfig = {}) {
    return new Chart(ctx, {
        type: 'line',
        options: {
            ..._chartDefaults,
            ...extraConfig,
            scales: {
                x: { ..._chartDefaults.scales.x, ...(extraConfig.scales?.x || {}) },
                y: { ..._chartDefaults.scales.y, ...(extraConfig.scales?.y || {}) },
            },
        },
    });
}

function p10p50p90Datasets(labels, p10, p50, p90, customColor = C.primary, customFill = C.fill) {
    return [
        {
            label: 'P90 (Optimistic)',
            data: p90,
            borderColor: 'transparent',
            backgroundColor: customFill,
            fill: '+1',
            pointRadius: 0,
        },
        {
            label: 'P50 (Median)',
            data: p50,
            borderColor: customColor,
            backgroundColor: 'transparent',
            borderWidth: 2.2,
            pointRadius: 0,
            tension: 0.35,
        },
        {
            label: 'P10 (Pessimistic)',
            data: p10,
            borderColor: 'transparent',
            backgroundColor: 'transparent',
            pointRadius: 0,
        },
    ];
}

function nowAnnotation() {
    return {
        nowLine: {
            type: 'line',
            xMin: 'Now',
            xMax: 'Now',
            borderColor: '#DA7756',
            borderWidth: 1.5,
            borderDash: [4, 4],
            label: {
                display: true,
                content: 'Now',
                position: 'start',
                backgroundColor: 'rgba(218, 119, 86, 0.9)',
                color: '#fff',
                font: { size: 10, weight: '600' },
                padding: { top: 2, bottom: 2, left: 5, right: 5 },
                borderRadius: 3,
            },
        },
    };
}

function formatTs(tsStr) {
    const d = new Date(tsStr);
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const h = d.getHours().toString().padStart(2, '0');
    return `${days[d.getDay()]} ${h}:00`;
}

// ── Global Status Poller ───────────────────────────────────────────────────
async function fetchStatus() {
    try {
        const [statusRes, cacheRes] = await Promise.all([
            fetch(`${API_BASE}/status`),
            fetch(`${API_BASE}/cache/status`),
        ]);
        const data  = await statusRes.json();
        const cache = await cacheRes.json();

        const dot = document.getElementById('status-dot');
        const stText = document.getElementById('status-text');
        if (stText) stText.innerText = `API: ${data.data_source} (${data.districts_count || 50} dist)`;
        const stCap = document.getElementById('status-cap');
        if (stCap) stCap.innerText = `Cap: ${data.total_capacity_mwc} MWc`;
        if (cache.is_stale && dot) dot.classList.add('warn');

        const ageEl = document.getElementById('cache-age-display');
        if (ageEl && cache.cache_age_min !== null) {
            ageEl.innerText = `Updated ${cache.cache_age_min} min ago`;
        }

        const dsSrc = document.getElementById('kpi-datasource');
        if (dsSrc) dsSrc.innerText = `Source: ${data.data_source}`;
    } catch (e) {
        const txt = document.getElementById('status-text');
        if (txt) txt.innerText = 'API Offline';
        const dot = document.getElementById('status-dot');
        if (dot) { dot.style.background = C.bad; dot.classList.add('warn'); }
    }
}

async function fetchAlertBadge() {
    try {
        const res  = await fetch(`${API_BASE}/alerts`);
        const data = await res.json();
        const count = data.count || 0;
        document.querySelectorAll('#nav-alert-badge').forEach(el => {
            el.textContent = count;
            el.classList.toggle('visible', count > 0);
        });
    } catch (_) {}
}

// ── ROUTER ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    applyI18n(currentLang);

    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => applyI18n(btn.dataset.lang));
    });

    await fetchStatus();
    await fetchAlertBadge();

    // Wire Prosol modal trigger on all pages if button exists
    setupProsolReportModal();

    const page = document.body.getAttribute('data-page');
    if (page === 'home')        initHome();
    if (page === 'districts')   initDistricts();
    if (page === 'map')         initTimelapseMap();
    if (page === 'performance') initPerformance();
    if (page === 'alerts')      initAlerts();
    if (page === 'registry')    initRegistry();
});

// ═══════════════════════════════════════════════════════════════════════════
// PROSOL REPORT STUDIO MODAL (Global)
// ═══════════════════════════════════════════════════════════════════════════
function setupProsolReportModal() {
    const btnOpen = document.getElementById('btn-open-prosol-modal');
    const modal = document.getElementById('prosolModal');
    const btnClose = document.getElementById('btnCloseProsolModal');
    const btnDownload = document.getElementById('btnDownloadProsolJson');

    if (!btnOpen || !modal) return;

    btnOpen.addEventListener('click', async () => {
        modal.classList.remove('hidden');
        const previewEl = document.getElementById('modalMetricsPreview');
        if (!previewEl) return;
        try {
            const res = await fetch(`${API_BASE}/reports/prosol/summary`);
            const data = await res.json();
            const ind = data.indicators || [];
            const pInst = ind.find(x => x.id === 2)?.since_2011 || 456.0;
            const nInst = ind.find(x => x.id === 1)?.since_2011 || 144979;
            const nPending = data.recap_executions?.pending_current || 5475;
            const compRate = data.recap_executions?.completion_rate_pct || 74.7;
            previewEl.innerHTML = `
                <div class="preview-stat-box">
                    <div class="val">${pInst.toFixed(1)} MWc</div>
                    <div class="lbl">Puissance Cumulée Raccordée</div>
                </div>
                <div class="preview-stat-box">
                    <div class="val">${nInst.toLocaleString()}</div>
                    <div class="lbl">Installations Réalisées</div>
                </div>
                <div class="preview-stat-box">
                    <div class="val">${nPending.toLocaleString()}</div>
                    <div class="lbl">Dossiers en Attente</div>
                </div>
                <div class="preview-stat-box">
                    <div class="val">${compRate.toFixed(1)}%</div>
                    <div class="lbl">Taux d'Exécution Q1 2026</div>
                </div>
            `;
        } catch (e) {
            previewEl.innerHTML = `<div style="grid-column:span 2;color:var(--status-bad);">Impossible de charger la synthèse.</div>`;
        }
    });

    if (btnClose) {
        btnClose.addEventListener('click', () => modal.classList.add('hidden'));
    }

    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.add('hidden');
    });

    if (btnDownload) {
        btnDownload.addEventListener('click', async () => {
            try {
                const res = await fetch(`${API_BASE}/reports/prosol/summary`);
                const json = await res.json();
                const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'steg_prosol_summary.json';
                a.click();
                URL.revokeObjectURL(url);
            } catch (e) {
                alert('Erreur lors du téléchargement');
            }
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE 1: NATIONAL OVERVIEW
// ═══════════════════════════════════════════════════════════════════════════
async function initHome() {
    const ctx = document.getElementById('nationalChart').getContext('2d');
    const chart = makeChart(ctx, {
        plugins: {
            ..._chartDefaults.plugins,
            annotation: { annotations: nowAnnotation() },
        }
    });

    let nationalData = [];
    let isNetMode = false;

    // Prosol Displacement KPI Strip fetch
    try {
        const dispRes = await fetch(`${API_BASE}/displacement/summary`);
        if (dispRes.ok) {
            const d = await dispRes.json();
            const elMwh = document.getElementById('kpi-prosol-mwh');
            const elInj = document.getElementById('kpi-prosol-injected');
            const elTep = document.getElementById('kpi-prosol-tep');
            const elCost = document.getElementById('kpi-prosol-cost');
            const elCo2 = document.getElementById('kpi-prosol-co2');

            if (elMwh) elMwh.textContent = `${d.mwh_gross_generated.toLocaleString()} MWh`;
            if (elInj) elInj.textContent = `${d.mwh_injected_to_grid.toLocaleString()} MWh`;
            if (elTep) elTep.textContent = `${d.fuel_saved_tep.toLocaleString()} tep`;
            if (elCost) elCost.textContent = `${d.cost_saved_dt.toLocaleString()} DT`;
            if (elCo2) elCo2.textContent = `${d.co2_avoided_tonnes.toLocaleString()} t`;
        }
    } catch (e) { console.warn('Displacement summary fetch error', e); }

    // National Forecast fetch
    try {
        const res  = await fetch(`${API_BASE}/forecast/national?horizon_days=3&split=true`);
        nationalData = await res.json();

        let todayPeak = 0, tmrwPeak = 0;
        let currentEst = 0, currentUnc = 0, todayUnc = 0, tmrwUnc = 0;

        const nowHour  = new Date().getHours();
        const todayStr = new Date().toISOString().split('T')[0];
        const tmrwStr  = new Date(Date.now() + 86400000).toISOString().split('T')[0];

        nationalData.forEach((row, i) => {
            const d       = new Date(row.timestamp);
            const dateStr = row.timestamp.split(' ')[0];
            const unc     = row.forecast_p90_mw - row.forecast_p10_mw;

            if (i === 0 || (d.getHours() === nowHour && dateStr === todayStr)) {
                currentEst = row.forecast_p50_mw;
                currentUnc = unc;
            }
            if (dateStr === todayStr && row.forecast_p50_mw > todayPeak) {
                todayPeak = row.forecast_p50_mw; todayUnc = unc;
            }
            if (dateStr === tmrwStr && row.forecast_p50_mw > tmrwPeak) {
                tmrwPeak = row.forecast_p50_mw; tmrwUnc = unc;
            }
        });

        document.getElementById('kpi-current').innerHTML       = `${currentEst.toFixed(1)} <span>MW</span>`;
        document.getElementById('kpi-peak-today').innerHTML    = `${todayPeak.toFixed(1)} <span>MW</span>`;
        document.getElementById('kpi-peak-tmrw').innerHTML     = `${tmrwPeak.toFixed(1)} <span>MW</span>`;
        document.getElementById('kpi-current-unc').textContent = `±${(currentUnc/2).toFixed(1)} MW`;
        document.getElementById('kpi-today-unc').textContent   = `±${(todayUnc/2).toFixed(1)} MW`;
        document.getElementById('kpi-tmrw-unc').textContent    = `±${(tmrwUnc/2).toFixed(1)} MW`;

        updateNationalChart();
    } catch (e) { console.error('Home national fetch error', e); }

    function updateNationalChart() {
        if (!nationalData.length) return;
        const labels = [];
        const p10 = [], p50 = [], p90 = [];

        nationalData.forEach(row => {
            labels.push(formatTs(row.timestamp));
            if (isNetMode) {
                const factor = 0.6407;
                p10.push(+(row.forecast_p10_mw * factor).toFixed(2));
                p50.push(row.forecast_injected_mw !== undefined ? row.forecast_injected_mw : +(row.forecast_p50_mw * factor).toFixed(2));
                p90.push(+(row.forecast_p90_mw * factor).toFixed(2));
            } else {
                p10.push(row.forecast_p10_mw);
                p50.push(row.forecast_p50_mw);
                p90.push(row.forecast_p90_mw);
            }
        });

        const color = isNetMode ? C.net : C.primary;
        const fill  = isNetMode ? C.netFill : C.fill;
        chart.data = { labels, datasets: p10p50p90Datasets(labels, p10, p50, p90, color, fill) };
        chart.update();
    }

    // Wire Gross / Net toggle pills
    const btnGross = document.getElementById('btn-toggle-gross');
    const btnNet = document.getElementById('btn-toggle-net');
    if (btnGross && btnNet) {
        btnGross.addEventListener('click', () => {
            isNetMode = false;
            btnGross.classList.add('active');
            btnNet.classList.remove('active');
            updateNationalChart();
        });
        btnNet.addEventListener('click', () => {
            isNetMode = true;
            btnNet.classList.add('active');
            btnGross.classList.remove('active');
            updateNationalChart();
        });
    }

    // ── Intraday 15-min chart ────────────────────────────────────────────
    const idCtx = document.getElementById('intradayChart');
    if (!idCtx) return;
    const idChart = makeChart(idCtx.getContext('2d'), {
        scales: {
            ..._chartDefaults.scales,
            y: { ..._chartDefaults.scales.y, ticks: { callback: v => `${v.toFixed(1)} MW` } }
        }
    });

    try {
        const res  = await fetch(`${API_BASE}/forecast/intraday`);
        const resp = await res.json();
        const data = resp.data || [];

        const banner = document.getElementById('intraday-banner');
        if (banner) banner.style.display = resp.bias_corrected ? 'flex' : 'none';

        const labels = [], p10 = [], p50 = [], p90 = [];
        data.forEach(row => {
            const d = new Date(row.timestamp);
            const h = d.getHours().toString().padStart(2, '0');
            const m = d.getMinutes().toString().padStart(2, '0');
            labels.push(`${h}:${m}`);
            p10.push(row.forecast_p10_mw);
            p50.push(row.forecast_p50_mw);
            p90.push(row.forecast_p90_mw);
        });

        idChart.data = { labels, datasets: p10p50p90Datasets(labels, p10, p50, p90) };
        idChart.update();
    } catch (e) { console.error('Intraday chart error', e); }
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE 2: REGIONAL ANALYSIS (50 STEG Districts + Model Prediction Breakdown)
// ═══════════════════════════════════════════════════════════════════════════
let distChartInstance = null;
let selectedDistrictRow = null;

async function initDistricts() {
    const ctx = document.getElementById('districtChart').getContext('2d');
    distChartInstance = makeChart(ctx, {
        plugins: {
            ..._chartDefaults.plugins,
            legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
            annotation: { annotations: nowAnnotation() },
        }
    });

    try {
        const [distRes, dirsRes] = await Promise.all([
            fetch(`${API_BASE}/steg-districts`),
            fetch(`${API_BASE}/districts`),
        ]);
        const districts = await distRes.json();
        const directions = await dirsRes.json();

        // Populate Direction filter pills
        const pillsContainer = document.getElementById('directionFilterPills');
        if (pillsContainer) {
            directions.forEach(dir => {
                const btn = document.createElement('button');
                btn.className = 'filter-pill';
                btn.dataset.direction = dir;
                btn.textContent = dir;
                pillsContainer.appendChild(btn);
            });
        }

        // Fetch forecasts to compute peak J+1 per district
        const fcRes = await fetch(`${API_BASE}/forecast/timelapse?hours=48`);
        const frames = await fcRes.json();

        const peakMap = {};
        const tomorrowStr = new Date(Date.now() + 86400000).toISOString().split('T')[0];

        frames.forEach(frame => {
            if (frame.timestamp.startsWith(tomorrowStr)) {
                frame.governorates.forEach(g => {
                    const name = g.governorate.toUpperCase();
                    if (!peakMap[name] || g.p50 > peakMap[name]) {
                        peakMap[name] = g.p50;
                    }
                });
            }
        });

        const tbody = document.getElementById('district-tbody');
        let currentFilterDir = 'ALL';

        const rows = districts.map(d => ({
            name: d.name,
            direction: d.direction,
            governorate: d.governorate,
            cap: d.installed_capacity_mwc,
            peak: peakMap[d.name.toUpperCase()] || 0.0,
            pending: d.pending_dossiers,
            execRate: d.execution_rate_pct,
        })).sort((a, b) => b.cap - a.cap);

        const renderTable = () => {
            tbody.innerHTML = '';
            const term = (document.getElementById('search-dist')?.value || '').toLowerCase();
            const filtered = rows.filter(r => {
                const matchDir = currentFilterDir === 'ALL' || r.direction.toUpperCase() === currentFilterDir.toUpperCase();
                const matchTerm = r.name.toLowerCase().includes(term) || r.direction.toLowerCase().includes(term) || r.governorate.toLowerCase().includes(term);
                return matchDir && matchTerm;
            });

            filtered.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${r.name}</strong></td>
                    <td><span class="registry-district-tag">${r.direction}</span></td>
                    <td class="mono">${r.cap.toFixed(1)}</td>
                    <td class="mono" style="color:var(--accent-primary);font-weight:600;">${r.peak.toFixed(1)}</td>
                `;
                tr.onclick = () => {
                    if (selectedDistrictRow) selectedDistrictRow.classList.remove('selected');
                    tr.classList.add('selected');
                    selectedDistrictRow = tr;
                    loadDistrictForecastDetails(r);
                };
                tbody.appendChild(tr);
            });

            // Update badge count
            const countBadge = document.getElementById('dist-count-badge');
            if (countBadge) countBadge.textContent = `${filtered.length} DISTRICTS`;
        };

        // Wire filter pills
        pillsContainer?.addEventListener('click', (e) => {
            if (e.target.classList.contains('filter-pill')) {
                pillsContainer.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
                e.target.classList.add('active');
                currentFilterDir = e.target.dataset.direction;
                renderTable();
            }
        });

        document.getElementById('search-dist')?.addEventListener('input', renderTable);

        renderTable();
        if (tbody.firstChild) tbody.firstChild.click();

    } catch (e) { console.error('Districts fetch error', e); }
}

async function loadDistrictForecastDetails(districtObj) {
    const name = districtObj.name;
    document.getElementById('drilldown-title').innerText = `District STEG: ${name}`;
    const dirBadge = document.getElementById('drilldown-dir-badge');
    if (dirBadge) dirBadge.textContent = `Direction: ${districtObj.direction}`;

    try {
        const res = await fetch(`${API_BASE}/forecast/steg-district/${encodeURIComponent(name)}?horizon_days=3`);
        if (!res.ok) throw new Error('Failed to fetch district forecast');
        const data = await res.json();

        const labels = [], p10 = [], p50 = [], p90 = [];
        let peakVal = 0, peakTime = '--:--', peakP10 = 0, peakP90 = 0;
        const tomorrowStr = new Date(Date.now() + 86400000).toISOString().split('T')[0];

        data.forEach(row => {
            labels.push(formatTs(row.timestamp));
            p10.push(row.forecast_p10_mw);
            p50.push(row.forecast_p50_mw);
            p90.push(row.forecast_p90_mw);

            if (row.timestamp.startsWith(tomorrowStr) && row.forecast_p50_mw > peakVal) {
                peakVal = row.forecast_p50_mw;
                peakP10 = row.forecast_p10_mw;
                peakP90 = row.forecast_p90_mw;
                const d = new Date(row.timestamp);
                peakTime = `${d.getHours().toString().padStart(2, '0')}:00`;
            }
        });

        // Update Peak Prediction Card
        const peakCard = document.getElementById('peakPredictionCard');
        if (peakCard) {
            peakCard.style.display = 'grid';
            document.getElementById('peak-p10').textContent = `${peakP10.toFixed(1)} MW`;
            document.getElementById('peak-p50').textContent = `${peakVal.toFixed(1)} MW`;
            document.getElementById('peak-p90').textContent = `${peakP90.toFixed(1)} MW`;
            document.getElementById('peak-time').textContent = peakTime;
        }

        distChartInstance.data = { labels, datasets: p10p50p90Datasets(labels, p10, p50, p90) };
        distChartInstance.options.plugins.annotation = { annotations: nowAnnotation() };
        distChartInstance.update();

        // Populate Hour-by-Hour Model Prediction Breakdown Table
        const predTbody = document.getElementById('predictionBreakdownTbody');
        if (predTbody) {
            predTbody.innerHTML = '';
            // Show next 48 hours
            data.slice(0, 48).forEach(row => {
                const unc = row.uncertainty_mw || (row.forecast_p90_mw - row.forecast_p10_mw);
                const ratio = row.uncertainty_ratio || (row.forecast_p50_mw > 0 ? unc / row.forecast_p50_mw : 0);
                let uncClass = 'low';
                let uncLabel = 'Faible';
                if (ratio >= 0.7) { uncClass = 'high'; uncLabel = 'Élevée'; }
                else if (ratio >= 0.3) { uncClass = 'mid'; uncLabel = 'Moyenne'; }

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${formatTs(row.timestamp)}</strong></td>
                    <td class="mono text-warn">${row.forecast_p10_mw.toFixed(2)}</td>
                    <td class="mono" style="color:var(--accent-primary);font-weight:700;">${row.forecast_p50_mw.toFixed(2)}</td>
                    <td class="mono text-good">${row.forecast_p90_mw.toFixed(2)}</td>
                    <td><span class="unc-pill ${uncClass}">±${(unc/2).toFixed(1)} MW (${uncLabel})</span></td>
                    <td class="mono">${row.ghi_wm2 !== undefined ? Math.round(row.ghi_wm2) : '--'}</td>
                    <td class="mono">${row.temp_c !== undefined ? row.temp_c.toFixed(1) : '--'}</td>
                    <td class="mono">${row.cloud_cover_pct !== undefined ? Math.round(row.cloud_cover_pct) : '--'}</td>
                `;
                predTbody.appendChild(tr);
            });
        }
    } catch (e) { console.error('District detail error', e); }
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE 3: MAP TIMELAPSE & WEATHER DATA
// ═══════════════════════════════════════════════════════════════════════════
let timelapseFrames  = [];
let currentFrameIdx  = 0;
let isPlaying        = false;
let playInterval;
let leafletMap;
let layerGroup;
let drilldownChart   = null;

function uncertaintyColor(ratio) {
    if (ratio < 0.3)  return C.good;
    if (ratio < 0.7)  return C.warn;
    return C.bad;
}

async function initTimelapseMap() {
    leafletMap = L.map('map').setView([34.0, 9.5], 6);

    // OpenStreetMap standard tile layer (free, open, no API key required, no watermarks)
    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        minZoom: 5,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'
    });

    // Light Neutral Canvas layer (clean dashboard look, no watermarks)
    const lightCanvas = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 16,
        minZoom: 5,
        attribution: 'Tiles &copy; Esri, DeLorme, NAVTEQ'
    });

    // Set OpenStreetMap as the active basemap
    osmLayer.addTo(leafletMap);

    // Layer switcher control for users
    L.control.layers({
        '🗺️ OpenStreetMap': osmLayer,
        '🏢 Gris Neutre (Light Canvas)': lightCanvas
    }, null, { position: 'topright' }).addTo(leafletMap);

    layerGroup = L.layerGroup().addTo(leafletMap);

    // Fetch 50 STEG districts coordinates
    const coordMap = {};
    try {
        const distRes = await fetch(`${API_BASE}/steg-districts`);
        if (distRes.ok) {
            const districts = await distRes.json();
            districts.forEach(d => {
                coordMap[d.name.toUpperCase()] = {
                    lat: d.lat,
                    lon: d.lon,
                    dust: d.dust_loss_pct,
                    cap: d.installed_capacity_mwc,
                    dir: d.direction,
                };
            });
        }
    } catch (e) {
        console.warn('District coordinates fetch fallback:', e);
    }

    try {
        const res = await fetch(`${API_BASE}/forecast/timelapse?hours=48`);
        timelapseFrames = await res.json();
        timelapseFrames.forEach(f => {
            f.governorates.forEach(g => {
                const meta = coordMap[g.governorate.toUpperCase()];
                if (meta) {
                    g.lat = meta.lat;
                    g.lon = meta.lon;
                    g.dust = meta.dust;
                    g.cap = meta.cap;
                    g.direction = meta.dir;
                }
            });
        });

        document.getElementById('time-slider').max = timelapseFrames.length - 1;
        renderFrame(0);

        document.getElementById('time-slider').addEventListener('input', e => renderFrame(parseInt(e.target.value)));
        document.getElementById('play-btn').addEventListener('click', () => {
            isPlaying = !isPlaying;
            document.getElementById('play-btn').innerText = isPlaying ? '⏸ Pause' : '▶ Play';
            if (isPlaying) {
                playInterval = setInterval(() => {
                    currentFrameIdx = (currentFrameIdx + 1) % timelapseFrames.length;
                    document.getElementById('time-slider').value = currentFrameIdx;
                    renderFrame(currentFrameIdx);
                }, 750);
            } else {
                clearInterval(playInterval);
            }
        });
    } catch (e) { console.error('Timelapse error', e); }

    // Close drilldown panel
    document.getElementById('drilldown-close')?.addEventListener('click', () => {
        document.getElementById('map-drilldown').classList.remove('open');
    });

    // Populate 7-Direction Regional Weather Snapshot Grid
    loadDirectionWeatherGrid();
}

async function loadDirectionWeatherGrid() {
    const grid = document.getElementById('weatherDirectionGrid');
    if (!grid) return;
    try {
        const res = await fetch(`${API_BASE}/forecast/map?horizon_hours=0`);
        const snap = await res.json();
        const dists = snap.districts || snap.governorates || [];

        // Aggregate weather by Direction
        const dirMap = {};
        dists.forEach(d => {
            const dir = d.direction || d.district || 'AUTRE';
            if (!dirMap[dir]) {
                dirMap[dir] = { count: 0, ghi: 0, temp: 0, cloud: 0, wind: 0, p50: 0 };
            }
            dirMap[dir].count += 1;
            dirMap[dir].ghi   += (d.ghi_wm2 || 0);
            dirMap[dir].temp  += (d.temp_c || 0);
            dirMap[dir].cloud += (d.cloud_cover_pct || 0);
            dirMap[dir].wind  += (d.wind_speed_ms || 0);
            dirMap[dir].p50   += (d.forecast_p50_mw || 0);
        });

        grid.innerHTML = '';
        Object.keys(dirMap).sort().forEach(dir => {
            const item = dirMap[dir];
            const avgGhi   = Math.round(item.ghi / item.count);
            const avgTemp  = (item.temp / item.count).toFixed(1);
            const avgCloud = Math.round(item.cloud / item.count);
            const avgWind  = (item.wind / item.count).toFixed(1);

            const card = document.createElement('div');
            card.className = 'weather-card';
            card.innerHTML = `
                <div class="weather-card-header">
                    <span class="weather-card-title">${dir}</span>
                    <span class="weather-card-badge">${item.count} districts</span>
                </div>
                <div class="weather-card-metrics">
                    <div>☀️ <strong>${avgGhi}</strong> W/m² GHI</div>
                    <div>🌡️ <strong>${avgTemp}</strong> °C</div>
                    <div>☁️ <strong>${avgCloud}%</strong> nuages</div>
                    <div>💨 <strong>${avgWind}</strong> m/s vent</div>
                </div>
                <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:2px;">
                    PV en service: <strong style="color:var(--accent-primary);">${item.p50.toFixed(1)} MW</strong>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (e) { console.error('Weather grid error', e); }
}

function renderFrame(idx) {
    currentFrameIdx = idx;
    const frame = timelapseFrames[idx];
    if (!frame) return;

    const d = new Date(frame.timestamp);
    document.getElementById('time-display').innerText =
        `${d.toLocaleDateString('en-GB')} ${d.getHours()}:00`;
    document.getElementById('map-nat-total').innerText =
        `${frame.national_total_mw.toFixed(1)} MW`;

    layerGroup.clearLayers();
    frame.governorates.forEach(g => {
        if (!g.lat || !g.lon) return;
        if (g.p50 <= 0.03) return; // skip night zeros

        const radius  = Math.max(5, Math.sqrt(g.p50) * 4.2);
        const opacity = Math.min(0.95, Math.max(0.3, g.utilization_pct / 100));
        const uncColor = uncertaintyColor(g.uncertainty_ratio || 0);

        const marker = L.circleMarker([g.lat, g.lon], {
            color:       uncColor,
            weight:      2.5,
            fillColor:   C.primary,
            fillOpacity: opacity,
            radius:      radius,
        });

        marker.bindPopup(
            `<strong>${g.governorate}</strong><br>` +
            `Direction: ${g.direction || 'STEG'}<br>` +
            `P50: <strong>${g.p50.toFixed(2)} MW</strong> (${g.utilization_pct}% util.)<br>` +
            `Uncertainty: ±${((g.p90 - g.p10) / 2).toFixed(2)} MW<br>` +
            `☁️ ${g.cloud_cover_pct}% nuages | ☀️ ${Math.round(g.ghi_wm2 || 0)} W/m²<br>` +
            `<small style="color:var(--accent-primary);">Cliquez pour détails météo & prévision</small>`
        );

        marker.on('click', () => openMapDrilldown(g.governorate, g));
        marker.addTo(layerGroup);
    });
}

async function openMapDrilldown(districtName, currentData) {
    const panel = document.getElementById('map-drilldown');
    panel.classList.add('open');
    document.getElementById('drilldown-gov-title').textContent = districtName;

    document.getElementById('dd-p50').textContent  = `${currentData.p50.toFixed(1)}`;
    document.getElementById('dd-util').textContent = `${currentData.utilization_pct}`;
    document.getElementById('dd-unc').textContent  =
        `${((currentData.p90 - currentData.p10) / 2).toFixed(1)}`;

    // Populate Weather items in Drilldown
    const elGhi = document.getElementById('dd-ghi');
    const elTemp = document.getElementById('dd-temp');
    const elCloud = document.getElementById('dd-cloud');
    const elWind = document.getElementById('dd-wind');
    const elDust = document.getElementById('dd-dust');

    if (elGhi) elGhi.textContent = currentData.ghi_wm2 !== undefined ? Math.round(currentData.ghi_wm2) : '--';
    if (elTemp) elTemp.textContent = currentData.temp_c !== undefined ? currentData.temp_c.toFixed(1) : '--';
    if (elCloud) elCloud.textContent = currentData.cloud_cover_pct !== undefined ? Math.round(currentData.cloud_cover_pct) : '--';
    if (elWind) elWind.textContent = currentData.wind_speed_ms !== undefined ? currentData.wind_speed_ms.toFixed(1) : '3.0';
    if (elDust) elDust.textContent = currentData.dust !== undefined ? `${(currentData.dust * 100).toFixed(1)}%` : '2.0%';

    // Load 72h forecast curve for this district
    try {
        const res  = await fetch(`${API_BASE}/forecast/steg-district/${encodeURIComponent(districtName)}?horizon_days=3`);
        const data = await res.json();
        const labels = [], p10 = [], p50 = [], p90 = [];
        data.forEach(row => {
            labels.push(formatTs(row.timestamp));
            p10.push(row.forecast_p10_mw);
            p50.push(row.forecast_p50_mw);
            p90.push(row.forecast_p90_mw);
        });

        const ctx = document.getElementById('drilldownChart').getContext('2d');
        if (drilldownChart) drilldownChart.destroy();
        drilldownChart = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets: p10p50p90Datasets(labels, p10, p50, p90) },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { display: false }, tooltip: { backgroundColor: C.bg, titleColor: C.text, bodyColor: C.muted, borderColor: C.border, borderWidth: 1 } },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
                    y: { grid: { color: 'rgba(230,228,221,0.5)' }, border: { display: false }, beginAtZero: true, ticks: { font: { size: 10 } } }
                },
            }
        });
    } catch (e) { console.error('Drilldown chart error', e); }
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE 4: PERFORMANCE / MODEL HEALTH
// ═══════════════════════════════════════════════════════════════════════════
async function initPerformance() {
    const ctx = document.getElementById('historyChart').getContext('2d');
    const histChart = makeChart(ctx, {
        plugins: {
            ..._chartDefaults.plugins,
            legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
        }
    });

    try {
        const res  = await fetch(`${API_BASE}/history/national`);
        const data = await res.json();
        const labels = [], actual = [], p50 = [], p10 = [], p90 = [];
        data.forEach(row => {
            labels.push(formatTs(row.timestamp));
            actual.push(row.actual_mw);
            p50.push(row.forecast_p50_mw || row.forecast_mw);
            p10.push(row.forecast_p10_mw);
            p90.push(row.forecast_p90_mw);
        });

        histChart.data = {
            labels,
            datasets: [
                {
                    label: 'P90 (Optimistic)',
                    data: p90,
                    borderColor: 'transparent',
                    backgroundColor: C.fill,
                    fill: '+1',
                    pointRadius: 0,
                },
                {
                    label: 'Actual (Realized)',
                    data: actual,
                    borderColor: C.good,
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.2,
                },
                {
                    label: 'P50 Forecast',
                    data: p50,
                    borderColor: C.primary,
                    borderWidth: 2,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    tension: 0.2,
                },
                {
                    label: 'P10 (Pessimistic)',
                    data: p10,
                    borderColor: 'transparent',
                    backgroundColor: 'transparent',
                    pointRadius: 0,
                },
            ]
        };
        histChart.update();
    } catch (e) { console.error('History chart error', e); }

    // Metrics table
    try {
        const res = await fetch(`${API_BASE}/metrics`);
        const rows = await res.json();
        const tbody = document.getElementById('metrics-tbody');
        tbody.innerHTML = '';
        rows.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${r.horizon_bucket}</strong></td>
                <td class="mono text-good">${r.nrmse_ours_pct?.toFixed(2)}%</td>
                <td class="mono text-muted">${r.nrmse_persistence_pct?.toFixed(2)}%</td>
                <td class="mono text-muted">${r.nrmse_clearsky_pct?.toFixed(2)}%</td>
                <td class="mono">${r.coverage_pct?.toFixed(1)}%</td>`;
            tbody.appendChild(tr);
        });
    } catch (e) { console.error('Metrics error', e); }

    // Retrain log
    try {
        const res  = await fetch(`${API_BASE}/retrain/status`);
        const data = await res.json();
        const container = document.getElementById('retrain-log-list');
        container.innerHTML = '';
        const events = data.retrain_log || [];
        if (events.length === 0) {
            container.innerHTML = '<div class="text-muted" style="padding:1rem;">No retrain events yet — continuous learning loop active.</div>';
            return;
        }
        events.forEach(ev => {
            const div = document.createElement('div');
            div.className = `retrain-event ${ev.retrained ? 'retrained' : 'no-action'}`;
            div.innerHTML = `
                <span class="retrain-icon">${ev.retrained ? '🔄' : '✓'}</span>
                <div>
                    <strong>${ev.retrained ? 'Model Retrained' : 'Drift Check Passed — No Retrain Needed'}</strong>
                    <div class="retrain-time">${ev.timestamp} | MAE: ${ev.model_mae_mw?.toFixed(2)} MW | Baseline: ${ev.persistence_mae_mw?.toFixed(2)} MW</div>
                </div>`;
            container.appendChild(div);
        });
    } catch (e) { console.error('Retrain log error', e); }
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE 5: ALERTS & SATURATION MONITORING
// ═══════════════════════════════════════════════════════════════════════════
async function initAlerts() {
    const list = document.getElementById('alert-list');
    try {
        const res  = await fetch(`${API_BASE}/alerts`);
        const data = await res.json();
        const alerts = data.alerts || [];
        list.innerHTML = '';

        if (alerts.length === 0) {
            list.innerHTML = `
                <div class="no-alerts">
                    <span class="no-alert-icon">✅</span>
                    All operational parameters within nominal thresholds. No active alerts.
                </div>`;
            return;
        }

        alerts.forEach(alert => {
            const isCrit = alert.severity === 'critical';
            const div = document.createElement('div');
            div.className = `alert-item ${isCrit ? 'critical' : 'warning'}`;
            const icon = alert.type === 'SATURATION_RISK' ? '⚡' : (isCrit ? '⚠️' : 'ℹ️');
            div.innerHTML = `
                <span class="alert-icon">${icon}</span>
                <div class="alert-body">
                    <div class="alert-type">${alert.type.replace(/_/g, ' ')} ${alert.district ? `(${alert.district})` : ''}</div>
                    <div class="alert-detail">${alert.detail}</div>
                    <div class="alert-ts">${alert.timestamp}</div>
                </div>`;
            list.appendChild(div);
        });
    } catch (e) {
        if (list) list.innerHTML = `<div class="no-alerts"><span class="no-alert-icon">❌</span>Could not reach API to fetch alerts.</div>`;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// PAGE 6: PARK REGISTRY & EXPANSION PIPELINE (50 STEG Districts)
// ═══════════════════════════════════════════════════════════════════════════
async function initRegistry() {
    try {
        const [distRes, pipeRes] = await Promise.all([
            fetch(`${API_BASE}/steg-districts`),
            fetch(`${API_BASE}/registry/pipeline`),
        ]);
        const districts = await distRes.json();
        const pipeline  = await pipeRes.json();

        // KPIs
        const totalCap = districts.reduce((s, d) => s + d.installed_capacity_mwc, 0);
        const totalPending = districts.reduce((s, d) => s + (d.pending_dossiers || 0), 0);
        const avgExec = districts.reduce((s, d) => s + (d.execution_rate_pct || 75.0), 0) / districts.length;

        document.getElementById('reg-total-cap').innerHTML = `${totalCap.toFixed(1)} <span style="font-size:1rem;color:var(--text-secondary);">MWc</span>`;
        document.getElementById('reg-pending').innerHTML   = `${totalPending.toLocaleString()} <span style="font-size:1rem;color:var(--text-secondary);">demandes</span>`;
        document.getElementById('reg-exec-rate').innerHTML = `${avgExec.toFixed(1)} <span style="font-size:1rem;color:var(--text-secondary);">%</span>`;

        // Collect unique Directions for dropdown filter
        const directions = [...new Set(districts.map(d => d.direction))].sort();
        const distFilter = document.getElementById('reg-district-filter');
        if (distFilter) {
            directions.forEach(dir => {
                const opt = document.createElement('option');
                opt.value = dir; opt.textContent = dir;
                distFilter.appendChild(opt);
            });
        }

        // Tab Switching
        const tabBtnInv = document.getElementById('tabBtnInventory');
        const tabBtnPipe = document.getElementById('tabBtnPipeline');
        const tabContentInv = document.getElementById('tabContentInventory');
        const tabContentPipe = document.getElementById('tabContentPipeline');

        tabBtnInv?.addEventListener('click', () => {
            tabBtnInv.classList.add('active');
            tabBtnPipe?.classList.remove('active');
            tabContentInv.style.display = 'block';
            tabContentPipe.style.display = 'none';
        });

        tabBtnPipe?.addEventListener('click', () => {
            tabBtnPipe.classList.add('active');
            tabBtnInv?.classList.remove('active');
            tabContentPipe.style.display = 'block';
            tabContentInv.style.display = 'none';
        });

        // Render Helpers
        const tbodyInv  = document.getElementById('registry-tbody');
        const tbodyPipe = document.getElementById('pipeline-tbody');
        const cardsGrid = document.getElementById('registry-cards');

        const renderInventory = (data) => {
            if (!tbodyInv) return;
            tbodyInv.innerHTML = '';
            data.forEach(d => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${d.name}</strong></td>
                    <td><span class="registry-district-tag">${d.direction}</span></td>
                    <td>${d.governorate}</td>
                    <td class="mono" style="font-weight:600;">${d.installed_capacity_mwc.toFixed(1)}</td>
                    <td class="mono">${(d.dust_loss_pct * 100).toFixed(1)}%</td>
                    <td class="mono ${d.pending_dossiers > 100 ? 'text-warn' : 'text-muted'}">${d.pending_dossiers}</td>
                    <td class="mono text-good">${(d.execution_rate_pct || 75.0).toFixed(1)}%</td>
                    <td class="text-muted mono" style="font-size:0.8rem;">${d.lat?.toFixed(3)}, ${d.lon?.toFixed(3)}</td>`;
                tbodyInv.appendChild(tr);
            });
        };

        const renderPipeline = (pipeData) => {
            if (!tbodyPipe) return;
            tbodyPipe.innerHTML = '';
            pipeData.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${p.district}</strong></td>
                    <td><span class="registry-district-tag">${p.direction}</span></td>
                    <td class="mono">${p.current_mwc.toFixed(1)} MWc</td>
                    <td class="mono text-warn">${p.pending_dossiers}</td>
                    <td class="mono">${p.exec_rate_pct.toFixed(1)}%</td>
                    <td class="mono">${p.projected_mwc_30d.toFixed(1)} MWc</td>
                    <td class="mono" style="font-weight:700;">${p.projected_mwc_90d.toFixed(1)} MWc</td>
                    <td><span class="growth-badge">+${p.added_mwc_90d.toFixed(2)} MWc</span></td>`;
                tbodyPipe.appendChild(tr);
            });
        };

        const renderCards = (data) => {
            if (!cardsGrid) return;
            cardsGrid.innerHTML = '';
            // Group by Direction
            const byDir = {};
            data.forEach(d => {
                if (!byDir[d.direction]) byDir[d.direction] = { cap: 0, count: 0, pending: 0, districts: [] };
                byDir[d.direction].cap += d.installed_capacity_mwc;
                byDir[d.direction].count += 1;
                byDir[d.direction].pending += (d.pending_dossiers || 0);
                byDir[d.direction].districts.push(d.name);
            });

            Object.keys(byDir).sort().forEach(dir => {
                const info = byDir[dir];
                const card = document.createElement('div');
                card.className = 'registry-card';
                card.innerHTML = `
                    <div class="registry-card-header">
                        <span class="registry-gov-name">Direction ${dir}</span>
                        <span class="registry-district-tag">${info.count} districts</span>
                    </div>
                    <div class="registry-stats">
                        <div class="registry-stat">
                            <div class="stat-label">Puissance Totale</div>
                            <div class="stat-value" style="color:var(--accent-primary);">${info.cap.toFixed(1)} MWc</div>
                        </div>
                        <div class="registry-stat">
                            <div class="stat-label">Dossiers en Instance</div>
                            <div class="stat-value text-warn">${info.pending}</div>
                        </div>
                    </div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.6rem;line-height:1.4;">
                        ${info.districts.slice(0, 6).join(', ')}${info.districts.length > 6 ? ` (+${info.districts.length - 6} autres)` : ''}
                    </div>`;
                cardsGrid.appendChild(card);
            });
        };

        renderInventory(districts);
        renderPipeline(pipeline);
        renderCards(districts);

        // Search & filter
        const filterFn = () => {
            const term = (document.getElementById('reg-search')?.value || '').toLowerCase();
            const selectedDir = distFilter?.value || '';
            const filtered = districts.filter(d =>
                (d.name.toLowerCase().includes(term) || d.direction.toLowerCase().includes(term) || d.governorate.toLowerCase().includes(term)) &&
                (!selectedDir || d.direction === selectedDir)
            );
            renderInventory(filtered);
            const filteredPipe = pipeline.filter(p =>
                (p.district.toLowerCase().includes(term) || p.direction.toLowerCase().includes(term)) &&
                (!selectedDir || p.direction === selectedDir)
            );
            renderPipeline(filteredPipe);
            renderCards(filtered);
        };

        document.getElementById('reg-search')?.addEventListener('input', filterFn);
        distFilter?.addEventListener('change', filterFn);

    } catch (e) { console.error('Registry fetch error', e); }
}