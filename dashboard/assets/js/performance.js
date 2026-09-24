
// ═══════════════════════════════════════════════════════════════════════════
// PAGE 4: PERFORMANCE / MODEL HEALTH
// ═══════════════════════════════════════════════════════════════════════════
async function initPerformance() {
    const ctx = document.getElementById('historyChart').getContext('2d');
    const histChart = makeChart(ctx, {
        plugins: {
            ..._chartDefaults.plugins,
            legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
        },
        scales: {
            x: {
                ticks: {
                    autoSkip: true,
                    maxTicksLimit: 31,
                    maxRotation: 0,
                    callback(value) {
                        const date = new Date(this.getLabelForValue(value));
                        return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                    },
                },
            },
        },
    });

    try {
        const res  = await fetch(`${API_BASE}/history/national`);
        const data = await res.json();
        const historyMeta = document.getElementById('history-meta');
        if (historyMeta && data.length) {
            const first = new Date(data[0].timestamp).toLocaleDateString();
            const last = new Date(data[data.length - 1].timestamp).toLocaleDateString();
            historyMeta.textContent = `${data.length} hourly national rows · ${first} – ${last} · Source: ${data[0].source || 'legacy history'}${data[0].dataset_path ? ` · ${data[0].dataset_path}` : ''}`;
        }
        const labels = [], actual = [], p50 = [], p10 = [], p90 = [];
        data.forEach(row => {
            labels.push(row.timestamp);
            actual.push(row.actual_mw);
            p50.push(row.forecast_p50_mw ?? row.forecast_mw ?? null);
            p10.push(row.forecast_p10_mw);
            p90.push(row.forecast_p90_mw);
        });

        histChart.data = {
            labels,
            datasets: [
                {
                    label: 'P90 (Upper bound)',
                    data: p90,
                    borderColor: 'rgba(217, 160, 91, 0.9)',
                    backgroundColor: C.fill,
                    borderWidth: 1.2,
                    borderDash: [4, 3],
                    fill: false,
                    pointRadius: 0,
                },
                {
                    label: 'P10 (Lower bound)',
                    data: p10,
                    borderColor: 'rgba(217, 160, 91, 0.9)',
                    backgroundColor: C.fill,
                    borderWidth: 1.2,
                    borderDash: [4, 3],
                    fill: '-1',
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
                    label: 'P50 Forecast (Median)',
                    data: p50,
                    borderColor: '#2563eb',
                    backgroundColor: 'transparent',
                    borderWidth: 3,
                    borderDash: [],
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    order: 10,
                    tension: 0.2,
                },
            ]
        };
        histChart.update();
    } catch (e) {
        console.error('History chart error', e);
        const historyMeta = document.getElementById('history-meta');
        if (historyMeta) historyMeta.textContent = 'Historical dataset unavailable.';
    }
    const reloadHistoryButton = document.getElementById('reload-history-btn');
    if (reloadHistoryButton) reloadHistoryButton.addEventListener('click', () => window.location.reload());

    // ── Daily Accuracy Trends ─────────────────────────────────────────────
    try {
        const dailyRes = await fetch(`${API_BASE}/history/daily`);
        if (dailyRes.ok) {
            const daily = await dailyRes.json();
            const dailyMeta = document.getElementById('daily-meta');
            if (dailyMeta && daily.length) {
                const avgMae = daily.reduce((s, d) => s + (d.mae_mw || 0), 0) / daily.length;
                const avgCov = daily.reduce((s, d) => s + (d.coverage_pct || 0), 0) / daily.length;
                dailyMeta.textContent = `${daily.length} days · Avg MAE: ${avgMae.toFixed(2)} MW · Avg coverage: ${avgCov.toFixed(1)}%`;
            }
            const dLabels = daily.map(d => d.date);
            const simpleLineOpts = {
                ..._chartDefaults,
                plugins: {
                    ..._chartDefaults.plugins,
                    legend: { display: true, position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } },
                },
                scales: {
                    x: { ticks: { autoSkip: true, maxTicksLimit: 15, maxRotation: 0 } },
                    y: { beginAtZero: true },
                },
            };
            new Chart(document.getElementById('dailyErrorChart'), {
                type: 'line',
                data: {
                    labels: dLabels,
                    datasets: [
                        {
                            label: 'MAE (MW)',
                            data: daily.map(d => d.mae_mw),
                            borderColor: '#2563eb',
                            backgroundColor: 'rgba(37,99,235,0.08)',
                            borderWidth: 2,
                            pointRadius: 2,
                            pointHoverRadius: 5,
                            tension: 0.3,
                            fill: true,
                        },
                        {
                            label: 'RMSE (MW)',
                            data: daily.map(d => d.rmse_mw),
                            borderColor: 'rgba(218, 119, 86, 0.9)',
                            borderWidth: 1.5,
                            pointRadius: 1,
                            borderDash: [4, 3],
                            tension: 0.3,
                            fill: false,
                        },
                    ],
                },
                options: { ...simpleLineOpts, scales: { ...simpleLineOpts.scales, y: { ...simpleLineOpts.scales.y, title: { display: true, text: 'MW' } } } },
            });
            new Chart(document.getElementById('dailyCoverageChart'), {
                type: 'line',
                data: {
                    labels: dLabels,
                    datasets: [
                        {
                            label: 'P10–P90 Coverage (%)',
                            data: daily.map(d => d.coverage_pct),
                            borderColor: '#7c3aed',
                            backgroundColor: 'rgba(124,58,237,0.08)',
                            borderWidth: 2,
                            pointRadius: 2,
                            tension: 0.3,
                            fill: true,
                            yAxisID: 'y',
                        },
                        {
                            label: 'Bias (MW)',
                            data: daily.map(d => d.bias_mw),
                            borderColor: '#C0392B',
                            borderWidth: 1.5,
                            pointRadius: 1,
                            borderDash: [4, 3],
                            tension: 0.3,
                            fill: false,
                            yAxisID: 'y1',
                        },
                    ],
                },
                options: {
                    ...simpleLineOpts,
                    scales: {
                        x: simpleLineOpts.scales.x,
                        y: { beginAtZero: true, max: 100, position: 'left', ticks: { callback: v => `${v}%` }, title: { display: true, text: 'Coverage' } },
                        y1: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Bias (MW)' } },
                    },
                },
            });
        }
    } catch (e) { console.error('Daily accuracy error', e); }

    // ── Feature Importance (training-info) ─────────────────────────────────────────────
    try {
        const trainingInfoRes = await fetch(`${API_BASE}/model/training-info?_=${Date.now()}`, { cache: 'no-store' });
        if (trainingInfoRes.ok) {
            const trainingInfo = await trainingInfoRes.json();
            _renderFeatureImportanceChart(trainingInfo.feature_importance, trainingInfo.model_info);
        }
    } catch (e) {
        console.error('Training info error', e);
    }

    // Training loss and validation accuracy
    try {
        const validationResponse = await fetch(`${API_BASE}/model/validation?_=${Date.now()}`, { cache: 'no-store' });
        if (!validationResponse.ok) throw new Error(`Validation metrics request failed with ${validationResponse.status}`);
        const validation = await validationResponse.json();
        const train = validation.training || {};
        const test = validation.validation || {};
        const validationMeta = document.getElementById('validation-meta');
        if (validationMeta) {
            validationMeta.textContent = `Source: ${validation.source} · Split: ${validation.split_timestamp} · Samples: ${Number(train.samples || 0).toLocaleString()} train / ${Number(test.samples || 0).toLocaleString()} validation · Validation MAE: ${Number(test.mae_mw || 0).toFixed(2)} MW · RMSE: ${Number(test.rmse_mw || 0).toFixed(2)} MW`;
        }
        const stages = ['Training', 'Validation'];
        const simpleOptions = {
            ..._chartDefaults,
            plugins: {
                ..._chartDefaults.plugins,
                legend: { display: true, position: 'bottom' },
            },
            scales: {
                x: { ..._chartDefaults.scales.x },
                y: { beginAtZero: true },
            },
        };
        new Chart(document.getElementById('lossChart'), {
            type: 'bar',
            data: {
                labels: stages,
                datasets: [{
                    label: 'Pinball loss',
                    data: [train.pinball_loss, test.pinball_loss],
                    backgroundColor: ['rgba(218, 119, 86, 0.65)', 'rgba(218, 119, 86, 0.35)'],
                    borderColor: C.primary,
                    borderWidth: 1,
                }],
            },
            options: simpleOptions,
        });
        new Chart(document.getElementById('accuracyChart'), {
            type: 'bar',
            data: {
                labels: stages,
                datasets: [
                    {
                        label: 'Accuracy (100 − nRMSE)',
                        data: [train.accuracy_pct, test.accuracy_pct],
                        backgroundColor: ['rgba(37, 99, 235, 0.65)', 'rgba(37, 99, 235, 0.35)'],
                        borderColor: '#2563eb',
                        borderWidth: 1,
                    },
                    {
                        label: 'P10–P90 coverage',
                        data: [train.coverage_pct, test.coverage_pct],
                        backgroundColor: ['rgba(124, 58, 237, 0.65)', 'rgba(124, 58, 237, 0.35)'],
                        borderColor: '#7c3aed',
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                ...simpleOptions,
                scales: {
                    x: { ..._chartDefaults.scales.x },
                    y: { beginAtZero: true, max: 100, ticks: { callback: value => `${value}%` } },
                },
            },
        });
    } catch (error) {
        const validationError = document.getElementById('validation-error');
        if (validationError) {
            validationError.hidden = false;
            validationError.textContent = `Could not load training/validation metrics: ${error.message}`;
        }
    }

    // ── Training Progression ─────────────────────────────────────────────
    try {
        const progRes = await fetch(`${API_BASE}/model/training-progression`);
        if (progRes.ok) {
            const runs = await progRes.json();
            const progMeta = document.getElementById('progression-meta');
            const progTableWrap = document.getElementById('progression-table-wrap');
            if (runs.length === 0) {
                if (progMeta) progMeta.textContent = 'No training runs recorded yet. Run `python models/history.py` to generate.';
            } else {
                const promoted = runs.filter(r => r.promoted).length;
                if (progMeta) progMeta.textContent = `${runs.length} training runs · ${promoted} promoted to production`;

                // Chart: MAE progression across runs
                const labels = runs.map(r => `Run ${r.step}`);
                const maeData = runs.map(r => r.mae_mw);
                const coverageData = runs.map(r => r.coverage_pct);
                const bgColors = runs.map(r => r.promoted ? 'rgba(37,99,235,0.7)' : 'rgba(122,119,113,0.5)');
                const borderColors = runs.map(r => r.promoted ? '#2563eb' : '#7A7771');

                new Chart(document.getElementById('progressionChart'), {
                    type: 'bar',
                    data: {
                        labels,
                        datasets: [
                            {
                                label: 'MAE (MW)',
                                data: maeData,
                                backgroundColor: bgColors,
                                borderColor: borderColors,
                                borderWidth: 1,
                                yAxisID: 'y',
                            },
                            {
                                label: 'Coverage (%)',
                                data: coverageData,
                                type: 'line',
                                borderColor: '#7c3aed',
                                backgroundColor: 'transparent',
                                borderWidth: 2,
                                pointRadius: 4,
                                pointBackgroundColor: '#7c3aed',
                                tension: 0.2,
                                yAxisID: 'y1',
                            },
                        ],
                    },
                    options: {
                        ..._chartDefaults,
                        plugins: {
                            ..._chartDefaults.plugins,
                            legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
                        },
                        scales: {
                            x: { grid: { display: false } },
                            y: { beginAtZero: true, position: 'left', title: { display: true, text: 'MAE (MW)' }, grid: { color: 'rgba(230,228,221,0.6)' } },
                            y1: { position: 'right', max: 100, grid: { drawOnChartArea: false }, title: { display: true, text: 'Coverage (%)' }, ticks: { callback: v => `${v}%` } },
                        },
                    },
                });

                // Table
                let tableHtml = '<table class="data-table"><thead><tr>';
                tableHtml += '<th>Step</th><th>Run ID</th><th>Source</th><th>Features</th><th>MAE (MW)</th><th>nRMSE</th><th>Coverage</th><th>Drift</th><th>Status</th>';
                tableHtml += '</tr></thead><tbody>';
                runs.forEach(r => {
                    const maeStr = r.mae_mw != null ? Number(r.mae_mw).toFixed(2) : '—';
                    const nrmseStr = r.nrmse_pct != null ? Number(r.nrmse_pct).toFixed(2) + '%' : '—';
                    const covStr = r.coverage_pct != null ? Number(r.coverage_pct).toFixed(1) + '%' : '—';
                    const driftStr = r.drift_ratio_pct != null ? Number(r.drift_ratio_pct).toFixed(1) + '%' : '—';
                    const statusTag = r.promoted
                        ? '<span class="baseline-chip" style="background:rgba(37,99,235,0.15);color:#2563eb;">PROMOTED</span>'
                        : '<span class="text-muted">—</span>';
                    const shortId = (r.run_id || '').replace('training_', '').substring(0, 20);
                    tableHtml += `<tr>
                        <td><strong>${r.step}</strong></td>
                        <td class="mono" style="font-size:0.78rem;">${shortId}</td>
                        <td>${r.source || '—'}</td>
                        <td>${r.feature_version || '—'}</td>
                        <td class="mono">${maeStr}</td>
                        <td class="mono">${nrmseStr}</td>
                        <td class="mono">${covStr}</td>
                        <td class="mono">${driftStr}</td>
                        <td>${statusTag}</td>
                    </tr>`;
                });
                tableHtml += '</tbody></table>';
                if (progTableWrap) progTableWrap.innerHTML = tableHtml;
            }
        }
    } catch (e) { console.error('Training progression error', e); }

    try {
        const rooftopResponse = await fetch(`${API_BASE}/history/rooftop`);
        const rooftop = await rooftopResponse.json();
        const rooftopSummary = document.getElementById('history-rooftop-summary');
        const provenanceBadge = document.getElementById('data-provenance-badge');
        const source = String(rooftop.source || '').toLowerCase();
        const isSynthetic = source.includes('synthetic');
        const isPvgis = source.includes('pvgis');
        if (provenanceBadge && rooftopResponse.ok) {
            provenanceBadge.hidden = false;
            provenanceBadge.textContent = isSynthetic
                ? 'SYNTHETIC VALIDATION DATA'
                : isPvgis ? 'PVGIS MODELED DATA' : 'REAL VALIDATED DATA';
            provenanceBadge.classList.toggle('warning', isSynthetic || isPvgis);
            provenanceBadge.classList.toggle('verified', !isSynthetic && !isPvgis);
        }
        if (rooftopSummary && rooftopResponse.ok) {
            rooftopSummary.textContent = `Rooftop fleet: ${Number(rooftop.pv_count).toLocaleString()} standardized PVs · ${(Number(rooftop.installed_capacity_kwp) / 1000).toFixed(1)} MWc · ${rooftop.districts} districts · ${rooftop.source}`;
        }
    } catch (e) { console.error('Rooftop history summary error', e); }


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
                <td class="mono text-muted">${r.nrmse_persist_24h_pct?.toFixed(2) ?? '—'}%</td>
                <td class="mono text-muted">${r.nrmse_persist_168h_pct?.toFixed(2) ?? '—'}%</td>
                <td class="mono text-muted">${r.nrmse_clearsky_pct?.toFixed(2)}%</td>
                <td class="mono">${r.coverage_pct?.toFixed(1)}%</td>
                <td class="mono text-muted">${r.samples?.toLocaleString() ?? '—'}</td>`;
            tbody.appendChild(tr);
        });
    } catch (e) { console.error('Metrics error', e); }

    // Retrain log
    try {
        const res  = await fetch(`${API_BASE}/retrain/status`);
        const data = await res.json();
        const learningStatus = document.getElementById('continuous-learning-status');
        if (learningStatus && data.schedule) {
            learningStatus.textContent = data.schedule.enabled
                ? `Continuous learning: daily candidate training from the ${data.schedule.source}; ${data.schedule.promotion_policy}.`
                : 'Continuous learning is disabled.';
        }
        const container = document.getElementById('retrain-log-list') || document.getElementById('retrain-log');
        container.innerHTML = '';
        const events = data.retrain_log || [];
        if (events.length === 0) {
            container.innerHTML = '<div class="text-muted" style="padding:1rem;">No retrain events yet — continuous learning loop active.</div>';
        } else {
            events.forEach(ev => {
            const div = document.createElement('div');
            div.className = `retrain-event ${ev.retrained ? 'retrained' : 'no-action'}`;
            // Build enhanced detail block
            let detailHtml = '';
            const baselines = ev.baseline_maes || {};
            const hasBaselines = typeof baselines === 'object' && Object.keys(baselines).length > 0;
            if (ev.retrained) {
                detailHtml += `<strong>Model Retrained${ev.candidate_promoted ? ' & Promoted' : ''}</strong>`;
                detailHtml += `<div class="retrain-time">${ev.timestamp}</div>`;
                detailHtml += `<div class="retrain-detail-grid">`;
                detailHtml += `<span class="retrain-detail-label">Our MAE</span><span class="retrain-detail-value mono">${ev.our_mae_mw != null ? Number(ev.our_mae_mw).toFixed(2) : (ev.model_mae_mw != null ? Number(ev.model_mae_mw).toFixed(2) : '—')} MW</span>`;
                if (ev.candidate_mae_mw != null) detailHtml += `<span class="retrain-detail-label">Candidate MAE</span><span class="retrain-detail-value mono text-good">${Number(ev.candidate_mae_mw).toFixed(2)} MW</span>`;
                detailHtml += `<span class="retrain-detail-label">Best Baseline</span><span class="retrain-detail-value mono">${ev.best_baseline_mae_mw != null ? Number(ev.best_baseline_mae_mw).toFixed(2) : (ev.persistence_mae_mw != null ? Number(ev.persistence_mae_mw).toFixed(2) : '—')} MW</span>`;
                detailHtml += `<span class="retrain-detail-label">Drift Ratio</span><span class="retrain-detail-value mono${ev.drift_ratio_pct > 85 ? ' text-warn' : ''}">${ev.drift_ratio_pct != null ? Number(ev.drift_ratio_pct).toFixed(1) + '%' : '—'}</span>`;
                if (ev.candidate_model_version) detailHtml += `<span class="retrain-detail-label">Model Version</span><span class="retrain-detail-value mono">${ev.candidate_model_version}</span>`;
                detailHtml += `</div>`;
                if (hasBaselines) {
                    detailHtml += `<div class="retrain-baselines"><span class="retrain-detail-label">Baseline breakdown:</span>`;
                    for (const [name, mae] of Object.entries(baselines)) {
                        detailHtml += `<span class="baseline-chip">${name}: <strong>${Number(mae).toFixed(2)} MW</strong></span>`;
                    }
                    detailHtml += `</div>`;
                }
            } else {
                detailHtml += `<strong>Drift Check Passed — No Retrain Needed</strong>`;
                detailHtml += `<div class="retrain-time">${ev.timestamp}</div>`;
                detailHtml += `<div class="retrain-detail-grid">`;
                detailHtml += `<span class="retrain-detail-label">Our MAE</span><span class="retrain-detail-value mono">${ev.our_mae_mw != null ? Number(ev.our_mae_mw).toFixed(2) : (ev.model_mae_mw != null ? Number(ev.model_mae_mw).toFixed(2) : '—')} MW</span>`;
                detailHtml += `<span class="retrain-detail-label">Best Baseline</span><span class="retrain-detail-value mono">${ev.best_baseline_mae_mw != null ? Number(ev.best_baseline_mae_mw).toFixed(2) : (ev.persistence_mae_mw != null ? Number(ev.persistence_mae_mw).toFixed(2) : '—')} MW</span>`;
                detailHtml += `<span class="retrain-detail-label">Drift Ratio</span><span class="retrain-detail-value mono text-good">${ev.drift_ratio_pct != null ? Number(ev.drift_ratio_pct).toFixed(1) + '%' : '—'}</span>`;
                detailHtml += `</div>`;
                if (hasBaselines) {
                    detailHtml += `<div class="retrain-baselines"><span class="retrain-detail-label">Baseline breakdown:</span>`;
                    for (const [name, mae] of Object.entries(baselines)) {
                        detailHtml += `<span class="baseline-chip">${name}: <strong>${Number(mae).toFixed(2)} MW</strong></span>`;
                    }
                    detailHtml += `</div>`;
                }
            }
            div.innerHTML = `<span class="retrain-icon">${ev.retrained ? '🔄' : '✓'}</span><div>${detailHtml}</div>`;
                container.appendChild(div);
            });
            // Render drift comparison chart if we have retrain events with baselines
            _renderDriftBaselineChart(events);
        }
    } catch (e) { console.error('Retrain log error', e); }

    // Model version registry
    try {
        const [productionResponse, versionsResponse] = await Promise.all([
            fetch(`${API_BASE}/models/production`),
            fetch(`${API_BASE}/models/versions`),
        ]);
        const production = (await productionResponse.json()).production;
        const versions = (await versionsResponse.json()).models || [];
        const productionEl = document.getElementById('production-model');
        productionEl.textContent = production
            ? `Production: ${production.model_version} · MAE ${production.metrics?.MAE_MW ?? '—'} MW`
            : 'No registered production model yet. A registry baseline is created on the first drift/retraining run.';
        document.getElementById('model-versions-table').innerHTML = `<thead><tr><th>Version</th><th>Status</th><th>Created</th><th>MAE</th><th>Training run</th></tr></thead><tbody>${versions.map(model => `<tr><td>${model.model_version}</td><td>${model.status}</td><td>${model.created_at}</td><td>${model.metrics?.MAE_MW ?? '—'} MW</td><td>${model.training_run_id}</td></tr>`).join('')}</tbody>`;
    } catch (e) { console.error('Model registry error', e); }

    // ── Retrain sources ─────────────────────────────────────────────────────

    const retrainProgress = document.getElementById('retrain-progress');
    const allRetrainBtns = document.querySelectorAll('.retrain-source-btn');

    function setRetrainBusy(btn, busy, labelBusy) {
        btn.disabled = busy;
        const original = btn.dataset.originalLabel || btn.textContent;
        if (busy) {
            btn.dataset.originalLabel = original;
            btn.innerHTML = `⏳ ${labelBusy || 'Starting\u2026'}`;
        } else {
            btn.innerHTML = btn.dataset.originalLabel || original;
        }
        allRetrainBtns.forEach(b => { if (b !== btn) b.disabled = busy; });
        retrainProgress.hidden = !busy;
        if (busy) retrainProgress.querySelector('.retrain-progress-fill').style.width = '60%';
    }

    async function pollRetrainComplete(statusEl, successPrefix) {
        for (let attempt = 0; attempt < 20; attempt++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
                const statusRes = await fetch(`${API_BASE}/retrain/status`);
                const statusData = await statusRes.json();
                const latest = (statusData.retrain_log || [])[0];
                if (latest && new Date(latest.timestamp).getTime() > Date.now() - 120_000) {
                    retrainProgress.hidden = true;
                    allRetrainBtns.forEach(b => { b.disabled = false; b.innerHTML = b.dataset.originalLabel || b.textContent; });
                    if (latest.retrained || latest.candidate_promoted) {
                        statusEl.textContent = `✅ ${successPrefix || 'Retrain complete'} — ${latest.candidate_model_version || 'new model'} promoted.`;
                        statusEl.style.color = 'var(--status-good)';
                    } else {
                        statusEl.textContent = `✓ Drift check passed — no retrain needed (MAE ${latest.model_mae_mw?.toFixed(2)} MW).`;
                        statusEl.style.color = 'var(--status-warn)';
                    }
                    return;
                }
            } catch (_) {}
        }
        retrainProgress.hidden = true;
        allRetrainBtns.forEach(b => { b.disabled = false; b.innerHTML = b.dataset.originalLabel || b.textContent; });
        statusEl.textContent = '⚠ Retrain may still be running. Check the log below.';
        statusEl.style.color = 'var(--status-warn)';
    }

    // Card 1 — Latest validated snapshot
    const retrainButton = document.getElementById('manual-retrain-btn');
    const retrainStatus = document.getElementById('manual-retrain-status');
    if (retrainButton) {
        retrainButton.addEventListener('click', async () => {
            retrainStatus.textContent = '';
            setRetrainBusy(retrainButton, true, 'Retraining…');
            try {
                const response = await fetch(`${API_BASE}/models/retrain`, { method: 'POST' });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Unable to start retraining');
                retrainStatus.textContent = `${result.message} Rows: ${result.rows}, locations: ${result.locations}.`;
                retrainStatus.style.color = 'var(--status-good)';
                pollRetrainComplete(retrainStatus, 'Model retrained');
            } catch (error) {
                retrainStatus.textContent = error.message;
                retrainStatus.style.color = 'var(--status-bad)';
                setRetrainBusy(retrainButton, false);
            }
        });
    }

    // Card 2 — Upload CSV
    const csvInput = document.getElementById('retrain-csv-input');
    const csvFilename = document.getElementById('retrain-csv-filename');
    const uploadBtn = document.getElementById('retrain-upload-btn');
    const uploadStatus = document.getElementById('retrain-upload-status');

    if (csvInput) {
        csvInput.addEventListener('change', () => {
            const file = csvInput.files[0];
            if (file) {
                csvFilename.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
                csvFilename.style.color = 'var(--text-primary)';
                uploadBtn.disabled = false;
            } else {
                csvFilename.textContent = 'No file selected';
                csvFilename.style.color = '';
                uploadBtn.disabled = true;
            }
        });
    }

    if (uploadBtn) {
        uploadBtn.addEventListener('click', async () => {
            const file = csvInput?.files[0];
            if (!file) return;
            uploadStatus.textContent = '';
            setRetrainBusy(uploadBtn, true, 'Uploading…');
            const formData = new FormData();
            formData.append('file', file);
            try {
                const response = await fetch(`${API_BASE}/models/retrain/upload`, {
                    method: 'POST',
                    body: formData,
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Upload failed');
                uploadStatus.textContent = `${result.message} Rows: ${result.rows}, locations: ${result.locations}.`;
                uploadStatus.style.color = 'var(--status-good)';
                csvInput.value = '';
                csvFilename.textContent = 'No file selected';
                csvFilename.style.color = '';
                uploadBtn.disabled = true;
                pollRetrainComplete(uploadStatus, 'Model retrained from upload');
            } catch (error) {
                uploadStatus.textContent = error.message;
                uploadStatus.style.color = 'var(--status-bad)';
                setRetrainBusy(uploadBtn, false);
            }
        });
    }

    // Card 3 — Synthetic data
    const synthBtn = document.getElementById('retrain-synth-btn');
    const synthStatus = document.getElementById('retrain-synth-status');
    const synthStart = document.getElementById('retrain-synth-start');
    const synthEnd = document.getElementById('retrain-synth-end');

    if (synthBtn) {
        synthBtn.addEventListener('click', async () => {
            synthStatus.textContent = '';
            const startDate = synthStart?.value || '2024-01-01';
            const endDate = synthEnd?.value || '2025-01-01';
            setRetrainBusy(synthBtn, true, 'Generating data…');
            try {
                const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
                const response = await fetch(`${API_BASE}/models/retrain/synthetic?${params}`, {
                    method: 'POST',
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Synthetic generation failed');
                synthStatus.textContent = `${result.message} Rows: ${result.rows}, locations: ${result.locations}.`;
                synthStatus.style.color = 'var(--status-good)';
                pollRetrainComplete(synthStatus, 'Model retrained from synthetic data');
            } catch (error) {
                synthStatus.textContent = error.message;
                synthStatus.style.color = 'var(--status-bad)';
                setRetrainBusy(synthBtn, false);
            }
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// FEATURE IMPORTANCE CHART
// ═══════════════════════════════════════════════════════════════════════════
function _renderFeatureImportanceChart(featureImportance, modelInfo) {
    const metaEl = document.getElementById('feature-importance-meta');
    const infoBar = document.getElementById('model-info-bar');
    const canvas = document.getElementById('featureImportanceChart');

    if (!featureImportance || featureImportance.length === 0) {
        if (metaEl) metaEl.textContent = 'Feature importance unavailable. Run `python models/ml_forecast.py` to train models.';
        return;
    }

    // Normalize importances to percentages for readability
    const total = featureImportance.reduce((s, f) => s + f.importance, 0);
    const features = featureImportance.map(f => ({
        ...f,
        pct: total > 0 ? (f.importance / total * 100) : 0,
    }));

    if (metaEl) {
        metaEl.textContent = `${features.length} features · normalized split importance from P50 ensemble`;
    }

    if (infoBar && modelInfo) {
        const gpuBadge = modelInfo.gpu_enabled ? '🟢 GPU' : '⚪ CPU';
        const parts = [
            `Model: ${modelInfo.model_type}`,
            modelInfo.ensemble_size ? `Ensemble: ${modelInfo.ensemble_size} models/quantile` : '',
            modelInfo.feature_count ? `Features: ${modelInfo.feature_count}` : '',
            `Device: ${gpuBadge}`,
        ].filter(Boolean);
        infoBar.textContent = parts.join(' · ');
        if (modelInfo.default_params) {
            const params = modelInfo.default_params;
            infoBar.innerHTML += `<br><span style="font-size:0.78rem;opacity:0.8;">Hyperparams: n_est=${params.n_estimators}, depth=${params.max_depth}, lr=${params.learning_rate}, leaves=${params.num_leaves}</span>`;
        }
    }

    // Color features by category
    const featureColors = features.map(f => {
        const name = f.feature;
        if (['ghi_wm2', 'dni_wm2', 'dhi_wm2', 'cos_zenith', 'clearsky_index', 'rolling_ghi_3h'].includes(name)) return '#2563eb'; // solar
        if (['temp_c', 'ghi_x_temp'].includes(name)) return '#C0392B'; // temperature
        if (['hour', 'hour_sin', 'hour_cos', 'day_of_year_sin', 'day_of_year_cos'].includes(name)) return '#7c3aed'; // temporal
        if (['cloud_cover_pct'].includes(name)) return '#0ea5e9'; // weather
        if (['capacity_mwc', 'dust_loss_pct', 'climate_zone_id'].includes(name)) return '#D9A05B'; // structural
        return '#7A7771'; // other
    });

    const ctx = canvas.getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: features.map(f => f.feature),
            datasets: [{
                label: 'Importance %',
                data: features.map(f => Number(f.pct.toFixed(2))),
                backgroundColor: featureColors.map(c => c + 'cc'),
                borderColor: featureColors,
                borderWidth: 1,
            }],
        },
        options: {
            ..._chartDefaults,
            indexAxis: 'y',
            plugins: {
                ..._chartDefaults.plugins,
                legend: { display: false },
                tooltip: {
                    ..._chartDefaults.plugins.tooltip,
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.x.toFixed(2)}% of total importance`,
                    },
                },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: 'rgba(230, 228, 221, 0.6)' },
                    ticks: { callback: v => `${v}%` },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { family: "'JetBrains Mono', monospace", size: 11 } },
                },
            },
        },
    });
}

// ═══════════════════════════════════════════════════════════════════════════
// DRIFT BASELINE CHART
// ═══════════════════════════════════════════════════════════════════════════
function _renderDriftBaselineChart(events) {
    // Filter events that have baseline data
    const eventsWithBaselines = events.filter(
        ev => ev.our_mae_mw != null && (ev.best_baseline_mae_mw != null || ev.baseline_maes)
    ).slice(0, 5); // latest 5

    if (eventsWithBaselines.length === 0) return;

    const wrapper = document.getElementById('drift-chart-wrapper');
    if (wrapper) wrapper.style.display = 'block';

    const canvas = document.getElementById('driftBaselineChart');
    if (!canvas) return;

    const labels = eventsWithBaselines.map(ev => {
        const d = new Date(ev.timestamp);
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }).reverse();

    const datasets = [
        {
            label: 'Our Model MAE',
            data: eventsWithBaselines.map(ev => Number(ev.our_mae_mw)).reverse(),
            backgroundColor: 'rgba(218, 119, 86, 0.7)',
            borderColor: C.primary,
            borderWidth: 1,
        },
    ];

    // Add each baseline type as a separate dataset
    const baselineNames = new Set();
    eventsWithBaselines.forEach(ev => {
        if (ev.baseline_maes && typeof ev.baseline_maes === 'object') {
            Object.keys(ev.baseline_maes).forEach(name => baselineNames.add(name));
        }
    });

    const baselineColors = {
        'persistence_24h': '#0ea5e9',
        'persistence_168h': '#7c3aed',
        'climatology': '#517A63',
    };

    baselineNames.forEach(name => {
        datasets.push({
            label: name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
            data: eventsWithBaselines.map(ev => {
                const baselines = ev.baseline_maes || {};
                return baselines[name] != null ? Number(baselines[name]) : null;
            }).reverse(),
            backgroundColor: (baselineColors[name] || '#7A7771') + 'aa',
            borderColor: baselineColors[name] || '#7A7771',
            borderWidth: 1,
        });
    });

    // If we only have best_baseline_mae_mw (old format), add that
    if (baselineNames.size === 0 && eventsWithBaselines[0].best_baseline_mae_mw != null) {
        datasets.push({
            label: 'Best Baseline MAE',
            data: eventsWithBaselines.map(ev => Number(ev.best_baseline_mae_mw)).reverse(),
            backgroundColor: 'rgba(81, 122, 99, 0.5)',
            borderColor: C.good,
            borderWidth: 1,
        });
    }

    new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: { labels, datasets },
        options: {
            ..._chartDefaults,
            plugins: {
                ..._chartDefaults.plugins,
                legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } },
                title: { display: true, text: 'MAE Comparison Across Retrain Events', font: { size: 13, weight: '500' } },
            },
            scales: {
                x: { grid: { display: false } },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(230, 228, 221, 0.6)' },
                    ticks: { callback: v => `${v} MW` },
                    title: { display: true, text: 'Mean Absolute Error (MW)', font: { size: 11 } },
                },
            },
        },
    });
}
