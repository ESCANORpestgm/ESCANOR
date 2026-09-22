
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
            if (countBadge) {
                const districtLabel = translate('district-count');
                countBadge.textContent = `${filtered.length} ${districtLabel}`;
            }
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
    const drilldownTitle = document.getElementById('drilldown-title');
    if (drilldownTitle) {
        // The placeholder is translated, but a selected district name is data-driven.
        drilldownTitle.removeAttribute('data-i18n');
        drilldownTitle.innerText = translate('district-title', { name });
    }
    const dirBadge = document.getElementById('drilldown-dir-badge');
    if (dirBadge) dirBadge.textContent = translate('direction-label', { name: districtObj.direction });

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
                const p10Value = Number(row.forecast_p10_mw || 0);
                const p50Value = Number(row.forecast_p50_mw || 0);
                const p90Value = Number(row.forecast_p90_mw || 0);
                const unc = Math.max(0, p90Value - p10Value);
                let uncClass = 'low';
                let uncLabel = 'Faible';
                if (p50Value <= 0.05 && p90Value <= 0.05) {
                    uncLabel = 'Nulle (nuit)';
                } else {
                    const ratio = p50Value > 0 ? unc / p50Value : 1;
                    if (ratio >= 0.7) { uncClass = 'high'; uncLabel = 'Élevée'; }
                    else if (ratio >= 0.3) { uncClass = 'mid'; uncLabel = 'Moyenne'; }
                }

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
