/* Historical official Prosol snapshots. Loaded only on the history page. */
let prosolHistoryReports = [];
let prosolHistoryCharts = {};
let predictionRuns = [];
let stegDistricts = [];
let pvLedgerEditing = null;
let lastProsolReport = null;
let lastPredictionRows = [];
let predictionCsvUrl = null;

function historyNumber(value, digits = 1) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function historyEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

function historyDestroyCharts() {
    // The prediction chart has its own lifecycle (it survives snapshot changes),
    // so reloading a report must not tear it down and leave an empty canvas.
    const { predictions, ...snapshotCharts } = prosolHistoryCharts;
    Object.values(snapshotCharts).forEach(chart => chart.destroy());
    prosolHistoryCharts = { ...(predictions ? { predictions } : {}) };
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
        [translate('hist-kpi-installations'), historyNumber(installations?.current_year_to_date, 0)],
        [translate('hist-kpi-capacity'), `${historyNumber(power?.current_year_to_date)} MW`],
        [translate('hist-kpi-production'), `${historyNumber(production?.current_year_to_date)} GWh`],
        [translate('hist-kpi-pending'), historyNumber(pending, 0)],
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
            datasets: [{ label: translate('chart-current-month'), data: national.map(row => row.current_month), backgroundColor: '#DA7756' }, { label: translate('ytd-label'), data: national.map(row => row.current_year_to_date), backgroundColor: '#517A63' }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { zoom: _chartZoom }, scales: { x: { ticks: { maxRotation: 30 } }, y: { beginAtZero: true } } },
    });

    const directions = report.directions || [];
    prosolHistoryCharts.directions = new Chart(document.getElementById('directionHistoryChart'), {
        type: 'bar',
        data: { labels: directions.map(row => row.name), datasets: [{ label: translate('chart-ytd-installs'), data: directions.map(row => row.current_year_to_date), backgroundColor: '#0ea5e9' }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { zoom: _chartZoom }, scales: { x: { beginAtZero: true } } },
    });

    const sizes = report.installation_sizes || [];
    prosolHistoryCharts.sizes = new Chart(document.getElementById('sizeHistoryChart'), {
        type: 'bar',
        data: { labels: sizes.map(row => `${row.system_size_kwc} kWc`), datasets: [{ label: translate('chart-ytd-installs'), data: sizes.map(row => row.current_year_to_date), backgroundColor: '#D9A05B' }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { zoom: _chartZoom }, scales: { y: { beginAtZero: true } } },
    });
}

function renderHistoryTables(report) {
    const districts = report.districts || [];
    document.getElementById('district-history-table').innerHTML = `<thead><tr><th>${translate('district-label')}</th><th>${translate('month-label')}</th><th>${translate('ytd-label')}</th><th>${translate('since-start-label')}</th></tr></thead><tbody>${districts.map(row => `<tr><td>${historyEscape(row.name)}</td><td>${historyNumber(row.current_month, 0)}</td><td>${historyNumber(row.current_year_to_date, 0)}</td><td>${historyNumber(row.since_program_start, 0)}</td></tr>`).join('')}</tbody>`;
    const pending = report.pending_dossiers || [];
    document.getElementById('pending-history-table').innerHTML = `<thead><tr><th>${translate('district-label')}</th><th>${translate('ytd-label')}</th><th>${translate('since-2018-label')}</th><th>${translate('share-label')}</th></tr></thead><tbody>${pending.map(row => `<tr><td>${historyEscape(row.district)}</td><td>${historyNumber(row.current_year_to_date, 0)}</td><td>${historyNumber(row.since_2018, 0)}</td><td>${historyNumber(row.share_pct)}%</td></tr>`).join('')}</tbody>`;
    const installations = report.new_installations_by_district || [];
    document.getElementById('new-installations-table').innerHTML = `<thead><tr><th>${translate('table-direction')}</th><th>${translate('district-label')}</th><th>${translate('official-month-label')}</th><th>${translate('ytd-label')}</th><th>${translate('added-live-label')}</th><th>${translate('current-ytd-label')}</th></tr></thead><tbody>${installations.map(row => `<tr><td>${historyEscape(row.direction)}</td><td>${historyEscape(row.district)}</td><td>${historyNumber(row.new_installations_month, 0)}</td><td>${historyNumber(row.new_installations_ytd, 0)}</td><td>${historyNumber(row.live_new_installations, 0)}</td><td>${historyNumber(row.current_new_installations_ytd, 0)}</td></tr>`).join('')}</tbody>`;
    const districtSelect = document.getElementById('installation-district');
    if (districtSelect && districtSelect.options.length <= 1) {
        const names = stegDistricts.length ? stegDistricts.map(row => row.name) : installations.map(row => row.district);
        districtSelect.innerHTML += names.map(name => `<option value="${historyEscape(name)}">${historyEscape(name)}</option>`).join('');
    }
    renderPvLedger(report.live_updates || []);
}

function renderHistoryMeta(report) {
    document.getElementById('history-meta').textContent = translate('hist-meta', {
        file: report.source_file,
        emitted: report.emission_date || '—',
        reconciliation: translate(report.database?.reconciliation_passed ? 'recon-passed' : 'recon-review'),
    });
}

async function loadProsolHistoryReport(snapshotId) {
    const response = await fetch(`${API_BASE}/reports/prosol/history/${encodeURIComponent(snapshotId)}`);
    if (!response.ok) throw new Error(`Unable to load snapshot (${response.status})`);
    const report = await response.json();
    lastProsolReport = report;
    renderHistoryKpis(report);
    renderHistoryCharts(report);
    renderHistoryTables(report);
    const csvLink = document.getElementById('new-installations-csv');
    if (csvLink) csvLink.href = `${API_BASE}/reports/prosol/history/${encodeURIComponent(snapshotId)}/new-installations.csv`;
    renderHistoryMeta(report);
    document.getElementById('history-content').hidden = false;
}

function setupInstallationUpdateForm(snapshotId, reload) {
    const form = document.getElementById('installation-update-form');
    if (!form || form.dataset.bound) return;
    form.dataset.bound = 'true';
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const status = document.getElementById('installation-update-status');
        const count = Number(document.getElementById('installation-count').value);
        const capacityInput = document.getElementById('installation-capacity').value;
        status.textContent = translate('ledger-saving');
        try {
            const response = await fetch(`${API_BASE}/reports/prosol/updates`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    district: document.getElementById('installation-district').value,
                    new_installations: count,
                    installed_capacity_kwp: capacityInput ? Number(capacityInput) : undefined,
                    report_period: selectedReportPeriod(),
                    source: 'frontend_manual_update',
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Unable to save installation update');
            status.textContent = translate('form-saved', { pvs: result.new_installations, district: result.district });
            form.reset();
            await reload(document.getElementById('report-selector').value);
        } catch (error) {
            status.textContent = error.message;
        }
    });
}

async function initProsolHistory() {
    const selector = document.getElementById('report-selector');
    const error = document.getElementById('history-error');
    try {
        // District names come from the platform registry, not the snapshot, so a
        // connection can be recorded for any district and the history panels can
        // offer every location — fetched first so the first render already has it.
        await loadStegDistricts();
        const response = await fetch(`${API_BASE}/reports/prosol/history`);
        if (!response.ok) throw new Error(`Unable to load report history (${response.status})`);
        prosolHistoryReports = (await response.json()).reports || [];
        if (!prosolHistoryReports.length) throw new Error('No imported Prosol snapshots found.');
        selector.innerHTML = prosolHistoryReports.map(report => `<option value="${historyEscape(report.snapshot_id)}">${historyEscape(report.report_period)} — ${historyEscape(report.source_file)}</option>`).join('');
        selector.addEventListener('change', () => loadProsolHistoryReport(selector.value).catch(historyLoadError));
        await loadProsolHistoryReport(selector.value);
        setupInstallationUpdateForm(selector.value, loadProsolHistoryReport);
        setupPvLedgerActions();
        await initPredictionHistory();
        document.addEventListener('escanor:language-changed', refreshProsolHistoryLanguage);
    } catch (loadError) {
        historyLoadError(loadError);
    }

    function historyLoadError(loadError) {
        error.hidden = false;
        error.textContent = loadError.message;
    }
}

async function loadStegDistricts() {
    if (stegDistricts.length) return stegDistricts;
    try {
        const response = await fetch(`${API_BASE}/steg-districts`);
        if (response.ok) stegDistricts = await response.json();
    } catch (error) {
        console.warn('[prosol-history] district registry unavailable:', error);
    }
    return stegDistricts;
}

/* Re-render the parts built as HTML strings; [data-i18n] nodes are handled by
   applyI18n itself, so without this the tables keep the previous language. */
async function refreshProsolHistoryLanguage() {
    if (lastProsolReport) {
        renderHistoryKpis(lastProsolReport);
        renderHistoryCharts(lastProsolReport);
        renderHistoryTables(lastProsolReport);
        renderHistoryMeta(lastProsolReport);
    }
    renderPredictionLocations();
    try { await loadPredictionHistory(); }
    catch (error) { console.warn('[prosol-history] prediction history re-render failed:', error); }
}

/* ── Live PV update ledger: edit, reverse and delete recorded connections ─── */

function currentLedgerUpdates() {
    return (lastProsolReport && lastProsolReport.live_updates) || [];
}

/* The report selector is keyed by snapshot id, but an update's report_period is
   a yyyy-MM period — sending the selector value stored the hash as the period. */
function selectedReportPeriod() {
    const snapshotId = document.getElementById('report-selector').value;
    const report = prosolHistoryReports.find(row => row.snapshot_id === snapshotId);
    return report ? report.report_period : undefined;
}

function ledgerDistrictOptions(selected) {
    const names = stegDistricts.length ? stegDistricts.map(row => row.name) : [];
    const options = names.length ? names : Array.from(document.getElementById('installation-district').options).map(option => option.value).filter(Boolean);
    return options.map(name => `<option value="${historyEscape(name)}"${name === selected ? ' selected' : ''}>${historyEscape(name)}</option>`).join('');
}

function ledgerRow(row) {
    const actions = `<td class="ledger-actions">
        <button type="button" class="btn btn-secondary btn-tiny" data-ledger-action="edit" data-update-id="${historyEscape(row.update_id)}">${translate('act-edit')}</button>
        <button type="button" class="btn btn-secondary btn-tiny" data-ledger-action="reverse" data-update-id="${historyEscape(row.update_id)}">${translate('act-reverse')}</button>
        <button type="button" class="btn btn-secondary btn-tiny btn-danger" data-ledger-action="delete" data-update-id="${historyEscape(row.update_id)}">${translate('act-delete')}</button>
    </td>`;
    if (pvLedgerEditing !== row.update_id) {
        return `<tr>
            <td>${historyEscape((row.recorded_at || '').slice(0, 16).replace('T', ' '))}${row.amended_at ? `<div class="text-muted">${translate('ledger-amended')} ${historyEscape(row.amended_at.slice(0, 16).replace('T', ' '))}</div>` : ''}</td>
            <td>${historyEscape(row.district)}</td>
            <td>${historyEscape(row.direction)}</td>
            <td>${historyNumber(row.new_installations, 0)}</td>
            <td>${historyNumber(row.installed_capacity_kwp)}</td>
            <td>${historyEscape(row.report_period)}</td>
            <td>${historyEscape(row.source)}${row.notes ? `<div class="text-muted">${historyEscape(row.notes)}</div>` : ''}</td>
            ${actions}
        </tr>`;
    }
    return `<tr class="ledger-editing">
        <td>${historyEscape((row.recorded_at || '').slice(0, 16).replace('T', ' '))}</td>
        <td><select data-field="district">${ledgerDistrictOptions(row.district)}</select></td>
        <td>${historyEscape(row.direction)}</td>
        <td><input data-field="new_installations" type="number" step="1" value="${Number(row.new_installations)}"></td>
        <td><input data-field="installed_capacity_kwp" type="number" step="0.01" value="${Number(row.installed_capacity_kwp)}"></td>
        <td><input data-field="report_period" type="month" value="${historyEscape(row.report_period)}"></td>
        <td><input data-field="notes" type="text" value="${historyEscape(row.notes || '')}"></td>
        <td class="ledger-actions">
            <button type="button" class="btn btn-primary btn-tiny" data-ledger-action="save" data-update-id="${historyEscape(row.update_id)}">${translate('act-save')}</button>
            <button type="button" class="btn btn-secondary btn-tiny" data-ledger-action="cancel">${translate('act-cancel')}</button>
        </td>
    </tr>`;
}

function renderPvLedger(updates) {
    const table = document.getElementById('pv-ledger-table');
    const totalPvs = updates.reduce((sum, row) => sum + Number(row.new_installations || 0), 0);
    const counter = document.getElementById('pv-ledger-count');
    if (counter) counter.textContent = translate('ledger-count', { count: updates.length, pvs: historyNumber(totalPvs, 0) });
    const head = `<thead><tr><th>${translate('ledger-recorded')}</th><th>${translate('district-label')}</th><th>${translate('table-direction')}</th><th>${translate('new-pvs')}</th><th>${translate('ledger-capacity')}</th><th>${translate('ledger-period')}</th><th>${translate('ledger-source')}</th><th>${translate('ledger-actions')}</th></tr></thead>`;
    if (!updates.length) {
        table.innerHTML = `${head}<tbody><tr><td colspan="8" class="text-muted">${translate('ledger-empty')}</td></tr></tbody>`;
        return;
    }
    table.innerHTML = `${head}<tbody>${updates.map(ledgerRow).join('')}</tbody>`;
}

function ledgerPayload(tr) {
    const read = field => tr.querySelector(`[data-field="${field}"]`)?.value;
    return {
        district: read('district'),
        new_installations: Number(read('new_installations')),
        installed_capacity_kwp: Number(read('installed_capacity_kwp')),
        report_period: read('report_period'),
        notes: read('notes'),
    };
}

async function requestLedger(url, options, statusMessage) {
    const status = document.getElementById('installation-update-status');
    try {
        const response = await fetch(url, options);
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
        if (status) status.textContent = statusMessage(result);
        await loadProsolHistoryReport(document.getElementById('report-selector').value);
    } catch (requestError) {
        if (status) status.textContent = requestError.message;
    }
}

function setupPvLedgerActions() {
    const table = document.getElementById('pv-ledger-table');
    if (!table || table.dataset.bound) return;
    table.dataset.bound = 'true';
    table.addEventListener('click', async event => {
        const button = event.target.closest('[data-ledger-action]');
        if (!button) return;
        const action = button.dataset.ledgerAction;
        const updateId = button.dataset.updateId;
        if (action === 'edit') { pvLedgerEditing = updateId; renderPvLedger(currentLedgerUpdates()); return; }
        if (action === 'cancel') { pvLedgerEditing = null; renderPvLedger(currentLedgerUpdates()); return; }
        if (action === 'save') {
            pvLedgerEditing = null;
            await requestLedger(`${API_BASE}/reports/prosol/updates/${encodeURIComponent(updateId)}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ledgerPayload(button.closest('tr'))),
            }, () => translate('ledger-saved'));
            return;
        }
        if (action === 'reverse') {
            if (!window.confirm(translate('ledger-confirm-reverse'))) return;
            await requestLedger(`${API_BASE}/reports/prosol/updates/${encodeURIComponent(updateId)}/reverse`, { method: 'POST' }, result => translate('ledger-reversed', { district: result.district }));
            return;
        }
        if (action === 'delete') {
            if (!window.confirm(translate('ledger-confirm-delete'))) return;
            await requestLedger(`${API_BASE}/reports/prosol/updates/${encodeURIComponent(updateId)}`, { method: 'DELETE' }, () => translate('ledger-deleted'));
        }
    });
}

/* ── Saved prediction history: issued forecast runs from the store ────────── */

function predictionStampLabel(issuedAt) {
    return String(issuedAt || '').slice(0, 16).replace('T', ' ');
}

function predictionLocations() {
    const level = document.getElementById('pred-level').value;
    if (level === 'direction') return [...new Set(stegDistricts.map(row => String(row.direction).toUpperCase()))].sort();
    if (level === 'steg_district') return stegDistricts.map(row => String(row.name).toUpperCase()).sort();
    return [];
}

function renderPredictionLocations() {
    const wrap = document.getElementById('pred-location-wrap');
    const select = document.getElementById('pred-location');
    const locations = predictionLocations();
    wrap.hidden = locations.length === 0;
    if (!locations.length) { select.innerHTML = ''; return; }
    const preferred = select.value;
    select.innerHTML = locations.map(name => `<option value="${historyEscape(name)}"${name === preferred ? ' selected' : ''}>${historyEscape(name)}</option>`).join('');
}

function predictionQuery() {
    const level = document.getElementById('pred-level').value;
    const params = new URLSearchParams({ level, days: '14' });
    if (level !== 'national') params.set('location', document.getElementById('pred-location').value);
    const issuedAt = document.getElementById('pred-run').value;
    if (issuedAt) params.set('issued_at', issuedAt);
    return params;
}

function renderPredictionChart(payload, latest) {
    if (prosolHistoryCharts.predictions) prosolHistoryCharts.predictions.destroy();
    const rows = payload.data || [];
    const labels = rows.map(row => String(row.target_timestamp).slice(5, 16).replace('T', ' '));
    const series = (name, rows_, color, dashed) => ({
        label: name, data: rows_.map(row => row.forecast_p50_mw), borderColor: color,
        backgroundColor: `${color}22`, borderWidth: dashed ? 1.5 : 2.2, borderDash: dashed ? [5, 4] : [],
        pointRadius: 0, tension: 0.3,
    });
    const datasets = [series(translate('pred-series-selected'), rows, '#DA7756', false)];
    if (latest && latest.issued_at !== payload.issued_at) {
        datasets.push(series(`${translate('pred-series-latest')} (${predictionStampLabel(latest.issued_at)})`, latest.data || [], '#517A63', true));
    }
    prosolHistoryCharts.predictions = new Chart(document.getElementById('predictionHistoryChart'), {
        type: 'line', data: { labels, datasets },
        options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: true }, zoom: _chartZoom }, scales: { x: { ticks: { maxRotation: 60, autoSkip: true } }, y: { beginAtZero: true, title: { display: true, text: 'MW' } } } },
    });
}

function renderPredictionRuns() {
    const table = document.getElementById('pred-run-table');
    const head = `<thead><tr><th>${translate('pred-issued-run')}</th><th>${translate('pred-window')}</th><th>${translate('pred-rows')}</th><th>${translate('pred-source')}</th></tr></thead>`;
    if (!predictionRuns.length) {
        table.innerHTML = `${head}<tbody><tr><td colspan="4" class="text-muted">${translate('pred-empty')}</td></tr></tbody>`;
        return;
    }
    table.innerHTML = `${head}<tbody>${predictionRuns.map(row => `<tr><td>${historyEscape(predictionStampLabel(row.issued_at))}</td><td>${historyEscape(String(row.target_start).slice(0, 10))} → ${historyEscape(String(row.target_end).slice(0, 13).replace('T', ' '))}</td><td>${historyNumber(row.rows, 0)}</td><td>${historyEscape(row.data_source)}</td></tr>`).join('')}</tbody>`;
}

function downloadPredictionCsv() {
    const header = 'issued_at,level,location,target_timestamp,forecast_p10_mw,forecast_p50_mw,forecast_p90_mw,horizon_hours,data_source';
    const lines = lastPredictionRows.map(row => [row.issued_at, row.level, row.location, row.target_timestamp, row.forecast_p10_mw, row.forecast_p50_mw, row.forecast_p90_mw, row.horizon_hours, row.data_source].join(','));
    const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv' });
    const link = document.getElementById('pred-csv');
    // Revoke the previous object URL rather than layering one-shot listeners.
    if (predictionCsvUrl) URL.revokeObjectURL(predictionCsvUrl);
    predictionCsvUrl = URL.createObjectURL(blob);
    link.href = predictionCsvUrl;
    link.download = `prediction_history_${predictionQuery().get('level')}_${(document.getElementById('pred-run').value || 'all').slice(0, 13)}.csv`;
}

async function loadPredictionHistory() {
    const meta = document.getElementById('pred-meta');
    const params = predictionQuery();
    const response = await fetch(`${API_BASE}/forecast/history?${params.toString()}`);
    if (!response.ok) throw new Error(`Unable to load prediction history (${response.status})`);
    const payload = await response.json();
    lastPredictionRows = payload.data || [];
    // The newest run on record, so the same target hours can be compared
    // across issue times — that difference is the point of keeping history.
    let latest = null;
    if (predictionRuns.length && params.get('issued_at') !== predictionRuns[0].issued_at) {
        const latestParams = new URLSearchParams(params);
        latestParams.set('issued_at', predictionRuns[0].issued_at);
        const latestResponse = await fetch(`${API_BASE}/forecast/history?${latestParams.toString()}`);
        if (latestResponse.ok) latest = await latestResponse.json();
    }
    renderPredictionChart(payload, latest);
    renderPredictionRuns();
    downloadPredictionCsv();
    const window_ = lastPredictionRows.length ? `${String(lastPredictionRows[0].target_timestamp).slice(0, 16)} → ${String(lastPredictionRows[lastPredictionRows.length - 1].target_timestamp).slice(0, 16)}` : '—';
    meta.textContent = translate('pred-meta', { runs: predictionRuns.length, rows: lastPredictionRows.length, window: window_, issued: predictionStampLabel(payload.issued_at) });
}

async function initPredictionHistory() {
    const levelSelect = document.getElementById('pred-level');
    const locationSelect = document.getElementById('pred-location');
    const runSelect = document.getElementById('pred-run');
    const meta = document.getElementById('pred-meta');
    function showPredictionError(error) {
        meta.textContent = error.message;
        renderPredictionRuns();
    }
    try {
        const runsResponse = await fetch(`${API_BASE}/forecast/history/runs`);
        await loadStegDistricts();
        predictionRuns = runsResponse.ok ? (await runsResponse.json()).runs || [] : [];
        if (runsResponse.ok && predictionRuns.length) {
            runSelect.innerHTML = predictionRuns.map(row => `<option value="${historyEscape(row.issued_at)}">${historyEscape(predictionStampLabel(row.issued_at))} · ${historyNumber(row.rows, 0)} ${translate('pred-rows-short')}</option>`).join('');
        } else {
            runSelect.innerHTML = `<option value="">${translate('pred-no-runs')}</option>`;
        }
        renderPredictionLocations();
        levelSelect.addEventListener('change', () => { renderPredictionLocations(); loadPredictionHistory().catch(showPredictionError); });
        locationSelect.addEventListener('change', () => loadPredictionHistory().catch(showPredictionError));
        runSelect.addEventListener('change', () => loadPredictionHistory().catch(showPredictionError));
        await loadPredictionHistory();
    } catch (error) {
        showPredictionError(error);
    }
}
