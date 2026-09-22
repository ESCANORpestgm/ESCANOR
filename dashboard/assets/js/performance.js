
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
