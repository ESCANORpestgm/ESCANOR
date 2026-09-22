/* Historical official Prosol snapshots. Loaded only on the history page. */
let prosolHistoryReports = [];
let prosolHistoryCharts = {};

function historyNumber(value, digits = 1) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function historyEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

function historyDestroyCharts() {
    Object.values(prosolHistoryCharts).forEach(chart => chart.destroy());
    prosolHistoryCharts = {};
}

function historyFindMetric(rows, text) {
    return rows.find(row => String(row.name || '').toLowerCase().includes(text));
}

function renderHistoryKpis(report) {
    const rows = report.national_rows || [];
    const installations = historyFindMetric(rows, 'installations');
    const power = historyFindMetric(rows, 'puissance installée');
    const production = historyFindMetric(rows, 'production des ipv');
    const pending = (report.pending_dossiers || []).reduce((sum, row) => sum + Number(row.current_year_to_date || 0), 0);
    document.getElementById('history-kpis').innerHTML = [
        ['Installations YTD', historyNumber(installations?.current_year_to_date, 0)],
        ['Capacity YTD', `${historyNumber(power?.current_year_to_date)} MW`],
        ['PV production YTD', `${historyNumber(production?.current_year_to_date)} GWh`],
        ['Pending dossiers YTD', historyNumber(pending, 0)],
    ].map(([label, value]) => `<div class="kpi-card"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div><div class="kpi-sub text-muted">${historyEscape(report.report_period)}</div></div>`).join('');
}

function renderHistoryCharts(report) {
    historyDestroyCharts();
    const rows = report.national_rows || [];
    const national = rows.filter(row => row.current_month !== undefined).slice(0, 5);
    prosolHistoryCharts.national = new Chart(document.getElementById('nationalHistoryChart'), {
        type: 'bar',
        data: {
            labels: national.map(row => String(row.name).replace(/\s*\(.*/, '').slice(0, 28)),
            datasets: [{ label: 'Current month', data: national.map(row => row.current_month), backgroundColor: '#DA7756' }, { label: 'YTD', data: national.map(row => row.current_year_to_date), backgroundColor: '#517A63' }],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { ticks: { maxRotation: 30 } }, y: { beginAtZero: true } } },
    });

    const directions = report.directions || [];
    prosolHistoryCharts.directions = new Chart(document.getElementById('directionHistoryChart'), {
        type: 'bar',
        data: { labels: directions.map(row => row.name), datasets: [{ label: 'YTD installations', data: directions.map(row => row.current_year_to_date), backgroundColor: '#0ea5e9' }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { beginAtZero: true } } },
    });

    const sizes = report.installation_sizes || [];
    prosolHistoryCharts.sizes = new Chart(document.getElementById('sizeHistoryChart'), {
        type: 'bar',
        data: { labels: sizes.map(row => `${row.system_size_kwc} kWc`), datasets: [{ label: 'YTD installations', data: sizes.map(row => row.current_year_to_date), backgroundColor: '#D9A05B' }] },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
    });
}

function renderHistoryTables(report) {
    const districts = report.districts || [];
    document.getElementById('district-history-table').innerHTML = `<thead><tr><th>District</th><th>Month</th><th>YTD</th><th>Since start</th></tr></thead><tbody>${districts.map(row => `<tr><td>${historyEscape(row.name)}</td><td>${historyNumber(row.current_month, 0)}</td><td>${historyNumber(row.current_year_to_date, 0)}</td><td>${historyNumber(row.since_program_start, 0)}</td></tr>`).join('')}</tbody>`;
    const pending = report.pending_dossiers || [];
    document.getElementById('pending-history-table').innerHTML = `<thead><tr><th>District</th><th>YTD</th><th>Since 2018</th><th>Share</th></tr></thead><tbody>${pending.map(row => `<tr><td>${historyEscape(row.district)}</td><td>${historyNumber(row.current_year_to_date, 0)}</td><td>${historyNumber(row.since_2018, 0)}</td><td>${historyNumber(row.share_pct)}%</td></tr>`).join('')}</tbody>`;
}

async function loadProsolHistoryReport(snapshotId) {
    const response = await fetch(`${API_BASE}/reports/prosol/history/${encodeURIComponent(snapshotId)}`);
    if (!response.ok) throw new Error(`Unable to load snapshot (${response.status})`);
    const report = await response.json();
    renderHistoryKpis(report);
    renderHistoryCharts(report);
    renderHistoryTables(report);
    document.getElementById('history-meta').textContent = `Source: ${report.source_file} · Emitted: ${report.emission_date || '—'} · Reconciliation: ${report.database?.reconciliation_passed ? 'passed' : 'review'}`;
    document.getElementById('history-content').hidden = false;
}

async function initProsolHistory() {
    const selector = document.getElementById('report-selector');
    const error = document.getElementById('history-error');
    try {
        const response = await fetch(`${API_BASE}/reports/prosol/history`);
        if (!response.ok) throw new Error(`Unable to load report history (${response.status})`);
        prosolHistoryReports = (await response.json()).reports || [];
        if (!prosolHistoryReports.length) throw new Error('No imported Prosol snapshots found.');
        selector.innerHTML = prosolHistoryReports.map(report => `<option value="${historyEscape(report.snapshot_id)}">${historyEscape(report.report_period)} — ${historyEscape(report.source_file)}</option>`).join('');
        selector.addEventListener('change', () => loadProsolHistoryReport(selector.value).catch(historyLoadError));
        await loadProsolHistoryReport(selector.value);
    } catch (loadError) {
        historyLoadError(loadError);
    }

    function historyLoadError(loadError) {
        error.hidden = false;
        error.textContent = loadError.message;
    }
}
