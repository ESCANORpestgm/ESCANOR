
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

    // Saved forecast-versus-actual evaluations
    let evaluationChart = null;
    const evaluationSelector = document.getElementById('evaluation-selector');
    const evaluationError = document.getElementById('evaluation-error');
    const evaluationSummary = document.getElementById('evaluation-summary');
    async function loadEvaluation(evaluationId) {
        const [detailRes, valuesRes] = await Promise.all([
            fetch(`${API_BASE}/evaluations/${encodeURIComponent(evaluationId)}`),
            fetch(`${API_BASE}/evaluations/${encodeURIComponent(evaluationId)}/values`),
        ]);
        if (!detailRes.ok || !valuesRes.ok) throw new Error('Could not load saved evaluation');
        const detail = await detailRes.json();
        const values = await valuesRes.json();
        const labels = values.map(row => formatTs(row.target_timestamp_utc));
        const datasets = [
            { label: 'P90', data: values.map(row => row.forecast_p90_kw), borderColor: 'transparent', backgroundColor: C.fill, fill: '+1', pointRadius: 0 },
            { label: 'Actual', data: values.map(row => row.power_kw), borderColor: C.good, borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: 'P50 Forecast', data: values.map(row => row.forecast_p50_kw), borderColor: C.primary, borderWidth: 2, borderDash: [3, 3], pointRadius: 0, tension: 0.2 },
            { label: 'P10', data: values.map(row => row.forecast_p10_kw), borderColor: 'transparent', backgroundColor: 'transparent', pointRadius: 0 },
        ];
        if (evaluationChart) evaluationChart.destroy();
        evaluationChart = new Chart(document.getElementById('evaluationChart'), { type: 'line', data: { labels, datasets }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'top' } }, scales: { y: { beginAtZero: true, title: { display: true, text: 'kW' } } } } });
        const horizon = (detail.horizon_metrics || []).map(row => `${row.horizon_bucket}: MAE ${Number(row.mae_kw).toFixed(2)} kW, coverage ${Number(row.p10_p90_coverage_pct).toFixed(1)}%`).join(' · ');
        evaluationSummary.textContent = `Matched rows: ${detail.rows_matched || values.length}${horizon ? ` · ${horizon}` : ''}`;
    }
    try {
        const response = await fetch(`${API_BASE}/evaluations/history`);
        const records = (await response.json()).evaluations || [];
        if (!records.length) throw new Error('No saved forecast evaluations yet. Run reports/forecast_evaluator.py with real forecast and actual CSV files.');
        evaluationSelector.innerHTML = records.map(record => `<option value="${record.evaluation_id}">${record.evaluation_id} (${record.rows_matched} rows)</option>`).join('');
        evaluationSelector.addEventListener('change', () => loadEvaluation(evaluationSelector.value).catch(error => { evaluationError.style.display = 'block'; evaluationError.textContent = error.message; }));
        await loadEvaluation(evaluationSelector.value);
    } catch (e) {
        evaluationError.style.display = 'block';
        evaluationError.textContent = e.message;
    }

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
        const container = document.getElementById('retrain-log-list') || document.getElementById('retrain-log');
        container.innerHTML = '';
        const events = data.retrain_log || [];
        if (events.length === 0) {
            container.innerHTML = '<div class="text-muted" style="padding:1rem;">No retrain events yet — continuous learning loop active.</div>';
        } else {
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

    const retrainButton = document.getElementById('manual-retrain-btn');
    const retrainStatus = document.getElementById('manual-retrain-status');
    if (retrainButton) {
        retrainButton.addEventListener('click', async () => {
            retrainButton.disabled = true;
            retrainButton.textContent = '⏳ Starting…';
            retrainStatus.textContent = '';
            try {
                const response = await fetch(`${API_BASE}/models/retrain`, { method: 'POST' });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Unable to start retraining');
                retrainStatus.textContent = `${result.message} Rows: ${result.rows}, buffer days: ${result.buffer_days}.`;
                retrainStatus.style.color = 'var(--status-good)';
                setTimeout(async () => {
                    try {
                        const statusResponse = await fetch(`${API_BASE}/retrain/status`);
                        const status = await statusResponse.json();
                        const latest = (status.retrain_log || [])[0];
                        if (latest) {
                            retrainStatus.textContent = latest.candidate_promoted
                                ? `Completed: ${latest.candidate_model_version} promoted to production.`
                                : `Completed: candidate ${latest.candidate_model_version || 'was not promoted'} — ${latest.promotion_reason || 'review the model registry.'}`;
                        }
                    } catch (_) {}
                    retrainButton.disabled = false;
                    retrainButton.textContent = '🔄 Run retraining';
                }, 3000);
            } catch (error) {
                retrainStatus.textContent = error.message;
                retrainStatus.style.color = 'var(--status-bad)';
                retrainButton.disabled = false;
                retrainButton.textContent = '🔄 Run retraining';
            }
        });
    }
}
