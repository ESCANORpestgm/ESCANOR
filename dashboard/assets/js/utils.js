/* ============================================================
   ESCANOR Dashboard — shared utilities
   Design tokens, Chart.js helpers, API constants, status poller
   ============================================================ */

const API_BASE = 'http://localhost:8000';

// ── Design tokens ───────────────────────────────────────────────────────────

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
if (typeof Chart !== 'undefined') {
    Chart.defaults.color       = C.muted;
    Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
    Chart.defaults.font.size   = 12;
}

// ── Chart.js helpers ────────────────────────────────────────────────────────

if (typeof zoomPlugin !== 'undefined' && typeof Chart !== 'undefined') Chart.register(zoomPlugin);

const _chartZoom = {
    pan: { enabled: true, mode: 'x' },
    zoom: { wheel: { enabled: true }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x' },
};

const _chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
        legend: { display: false },
        zoom: _chartZoom,
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
            label: 'P90 (Upper bound)',
            data: p90,
            borderColor: 'rgba(217, 160, 91, 0.9)',
            backgroundColor: customFill,
            borderWidth: 1.2,
            borderDash: [4, 3],
            fill: false,
            pointRadius: 0,
            tension: 0.25,
        },
        {
            label: 'P10 (Lower bound)',
            data: p10,
            borderColor: 'rgba(217, 160, 91, 0.9)',
            backgroundColor: customFill,
            borderWidth: 1.2,
            borderDash: [4, 3],
            fill: '-1',
            pointRadius: 0,
            tension: 0.25,
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

// ── Global status poller ────────────────────────────────────────────────────

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
        if (stCap) stCap.innerText = translate('capacity-status', { value: data.total_capacity_mwc });
        if (cache.is_stale && dot) dot.classList.add('warn');

        const ageEl = document.getElementById('cache-age-display');
        if (ageEl && cache.cache_age_min !== null) {
            ageEl.innerText = translate('updated-minutes', { minutes: cache.cache_age_min });
        }

        const dsSrc = document.getElementById('kpi-datasource');
        if (dsSrc) dsSrc.innerText = translate('source-status', { source: data.data_source });
    } catch (e) {
        const txt = document.getElementById('status-text');
        if (txt) txt.innerText = translate('api-offline');
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
