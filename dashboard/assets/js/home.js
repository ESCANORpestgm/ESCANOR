
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


    // National Forecast fetch
    try {
        const res  = await fetch(`${API_BASE}/forecast/national?horizon_days=3&split=true`);
        nationalData = await res.json();

        let todayPeak = 0, tmrwPeak = 0;
        let currentEst = 0, currentUnc = 0, todayUnc = 0, tmrwUnc = 0;

        const nowTs  = Date.now();
        const todayStr = new Date().toISOString().split('T')[0];
        const tmrwStr  = new Date(Date.now() + 86400000).toISOString().split('T')[0];

        // Work on a chronologically sorted copy — the API rows are not
        // guaranteed to arrive in timestamp order.
        const sortedRows = [...nationalData].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

        // "Now" row = first forecast point at or after the current time;
        // once the horizon starts in the past (e.g. evening), fall back to
        // the latest row not after now, else the very first row.
        const nowRow = sortedRows.find(r => new Date(r.timestamp).getTime() >= nowTs)
            || [...sortedRows].reverse().find(r => new Date(r.timestamp).getTime() < nowTs)
            || sortedRows[0];
        if (nowRow) {
            currentEst = nowRow.forecast_p50_mw;
            currentUnc = nowRow.forecast_p90_mw - nowRow.forecast_p10_mw;
        }

        sortedRows.forEach(row => {
            const dateStr = row.timestamp.split(' ')[0].split('T')[0];
            const unc     = row.forecast_p90_mw - row.forecast_p10_mw;

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
