// ═══════════════════════════════════════════════════════════════════════════
// PAGE 8: WHAT-IF SCENARIO SIMULATOR (Multi-Scope)
// ═══════════════════════════════════════════════════════════════════════════

async function initScenarios() {
    // ── Charts ────────────────────────────────────────────────────────────
    const ctx = document.getElementById('scenarioChart').getContext('2d');
    const chart = makeChart(ctx, {
        scales: {
            ..._chartDefaults.scales,
            y: { ..._chartDefaults.scales.y, title: { display: true, text: 'MW' } }
        }
    });

    const compareCtx = document.getElementById('compareChart');
    const compareChart = compareCtx ? new Chart(compareCtx, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    backgroundColor: C.bg, titleColor: C.text, bodyColor: C.muted,
                    borderColor: C.border, borderWidth: 1, padding: 10, boxPadding: 4,
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                y: { grid: { color: 'rgba(230,228,221,0.6)' }, border: { display: false },
                     beginAtZero: true, ticks: { callback: v => `${v} MW` } },
            }
        }
    }) : null;

    // ── Preset definitions ────────────────────────────────────────────────
    const PRESETS = {
        'clear-sky':    { cloud: -50, temp:   0, irradiance: 115, soiling:  0 },
        'partly-cloudy': { cloud:  30, temp:   0, irradiance:  90, soiling:  5 },
        'overcast':     { cloud: 100, temp:  -2, irradiance:  45, soiling: 10 },
        'heatwave':     { cloud:   0, temp:  15, irradiance: 105, soiling:  5 },
        'dust-storm':   { cloud:  20, temp:   5, irradiance:  40, soiling: 55 },
        'heavy-rain':   { cloud: 100, temp:  -5, irradiance:  30, soiling: 15 },
    };

    // ── Data cache: { national: [], direction: { DIR: [] }, district: { NAME: [] } }
    const cache = { national: [], direction: {}, district: {} };
    const todayStr = new Date().toISOString().split('T')[0];

    function todayFilter(rows) {
        if (!rows || !rows.length) return [];
        const filtered = rows.filter(r => (r.timestamp || '').startsWith(todayStr));
        return filtered.length >= 12 ? filtered : rows.slice(0, 24);
    }

    // ── Initial parallel fetch ───────────────────────────────────────────
    try {
        const [natRes, dirRes] = await Promise.all([
            fetch(`${API_BASE}/forecast/national?horizon_days=1`),
            fetch(`${API_BASE}/forecast/districts?horizon_days=1`),
        ]);
        cache.national = todayFilter(await natRes.json());
        const dirData  = await dirRes.json();

        // Group direction rows by name
        (dirData || []).forEach(row => {
            const name = (row.direction || row.district || '').toUpperCase();
            if (!name) return;
            if (!cache.direction[name]) cache.direction[name] = [];
            cache.direction[name].push(row);
        });
        // Apply today filter to each direction
        Object.keys(cache.direction).forEach(k => {
            cache.direction[k] = todayFilter(cache.direction[k]);
        });
    } catch (e) {
        console.error('[scenarios] initial fetch error', e);
        return;
    }

    if (!cache.national.length) return;

    // ── Populate dropdowns ────────────────────────────────────────────────
    const directionNames = Object.keys(cache.direction).sort();
    const dirSelect = document.getElementById('select-direction');
    const distSelect = document.getElementById('select-district');

    directionNames.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        dirSelect.appendChild(opt);
    });

    // District dropdown: build from district names listed in each direction
    const allDistricts = [];
    try {
        // Fetch district list from the steg-districts endpoint (uses first district per direction for names)
        const distListRes = await fetch(`${API_BASE}/steg-districts`);
        if (distListRes.ok) {
            const distList = await distListRes.json();
            (distList || []).forEach(d => {
                const name = (d.name || d.district || '').toUpperCase();
                if (name && !allDistricts.includes(name)) allDistricts.push(name);
            });
        }
    } catch (_) {}

    // Fallback: hardcode the 50 known districts from steg_districts.py
    if (!allDistricts.length) {
        const FALLBACK_DISTRICTS = [
            'TUNIS VILLE','ARIANA','EZZAHRA','MOUROUJ','KRAM','BARDO','MANNOUBA','EL MENZAH',
            'ZAGHOUAN','BIZERTE','MENZEL BOURGUIBA','NABEUL','MENZEL B-ZELFA','MENZEL TEMIME','HAMMAMET',
            'BEJA','JENDOUBA','KEF','SILIANA','TABARKA',
            'SOUSSE','SOUSSE NORD','MONASTIR','MOKNINE','MAHDIA','KAIROUAN','KAIROUAN NORD','EL JEM','MSAKEN','ENFIDHA',
            'SFAX VILLE','JBENIANA','SFAX NORD','MAHRES','SFAX SUD',
            'GAFSA','TOZEUR','KEBILI','METLAOUI',
            'GABES','GABES NORD','TATAOUINE','ZARZIS','BEN GUERDENE','JERBA','MEDNINE',
        ];
        FALLBACK_DISTRICTS.forEach(d => allDistricts.push(d));
    }
    allDistricts.sort().forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        distSelect.appendChild(opt);
    });

    // ── Scope state ──────────────────────────────────────────────────────
    let currentScope = 'national';
    let activeRows = cache.national;
    let scopeCapacity = null;  // MWc (for utilization display)

    const scopeCapEl = document.getElementById('scope-capacity');
    const comparePanel = document.getElementById('compare-panel');

    function setScope(scope) {
        currentScope = scope;
        dirSelect.hidden  = scope !== 'direction';
        distSelect.hidden = scope !== 'district';

        // Show comparison panel only for national scope
        if (comparePanel) comparePanel.hidden = scope !== 'national';

        // Reset active rows based on scope
        if (scope === 'national') {
            activeRows = cache.national;
            scopeCapacity = null;
            scopeCapEl.textContent = '';
        } else if (scope === 'direction') {
            const sel = dirSelect.value.toUpperCase();
            activeRows = sel ? (cache.direction[sel] || []) : [];
            scopeCapacity = null;
            scopeCapEl.textContent = sel ? `Direction: ${sel}` : '';
        } else {
            activeRows = [];
            scopeCapEl.textContent = '';
        }

        // Re-render with current params
        render(readSliders());
    }

    // Direction change → fetch if not cached, then re-render
    dirSelect.addEventListener('change', async () => {
        const name = dirSelect.value.toUpperCase();
        if (!name) { activeRows = []; render(readSliders()); return; }
        if (!cache.direction[name] || !cache.direction[name].length) {
            try {
                const res = await fetch(`${API_BASE}/forecast/direction/${encodeURIComponent(name)}?horizon_days=1`);
                const data = await res.json();
                cache.direction[name] = todayFilter(Array.isArray(data) ? data : []);
            } catch (_) { cache.direction[name] = []; }
        }
        activeRows = cache.direction[name] || [];
        scopeCapEl.textContent = `Direction: ${name}`;
        render(readSliders());
    });

    // District change → fetch if not cached, then re-render
    distSelect.addEventListener('change', async () => {
        const name = distSelect.value.toUpperCase();
        if (!name) { activeRows = []; scopeCapacity = null; scopeCapEl.textContent = ''; render(readSliders()); return; }
        if (!cache.district[name] || !cache.district[name].length) {
            try {
                const res = await fetch(`${API_BASE}/forecast/steg-district/${encodeURIComponent(name)}?horizon_days=1`);
                const data = await res.json();
                cache.district[name] = todayFilter(Array.isArray(data) ? data : []);
            } catch (_) { cache.district[name] = []; }
        }
        activeRows = cache.district[name] || [];
        scopeCapEl.textContent = `District: ${name}`;
        render(readSliders());
    });

    // Scope toggle buttons
    document.querySelectorAll('.scope-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            setScope(btn.dataset.scope);
        });
    });

    // ── Slider refs ──────────────────────────────────────────────────────
    const sliders = {
        cloud:      document.getElementById('slider-cloud'),
        temp:       document.getElementById('slider-temp'),
        irradiance: document.getElementById('slider-irradiance'),
        soiling:    document.getElementById('slider-soiling'),
    };
    const valEls = {
        cloud:      document.getElementById('val-cloud'),
        temp:       document.getElementById('val-temp'),
        irradiance: document.getElementById('val-irradiance'),
        soiling:    document.getElementById('val-soiling'),
    };

    function readSliders() {
        return {
            cloud:      +sliders.cloud.value,
            temp:       +sliders.temp.value,
            irradiance: +sliders.irradiance.value,
            soiling:    +sliders.soiling.value,
        };
    }

    function updateValLabels(p) {
        valEls.cloud.textContent      = `${p.cloud > 0 ? '+' : ''}${p.cloud}%`;
        valEls.temp.textContent       = `${p.temp > 0 ? '+' : ''}${p.temp}°C`;
        valEls.irradiance.textContent = `${p.irradiance}%`;
        valEls.soiling.textContent    = `${p.soiling}%`;
        // Update slider track gradient fill
        Object.values(sliders).forEach(updateSliderFill);
    }

    function updateSliderFill(slider) {
        const min = +slider.min, max = +slider.max, val = +slider.value;
        const pct = ((val - min) / (max - min)) * 100;
        slider.style.background = `linear-gradient(90deg, #DA7756 0%, #DA7756 ${pct}%, #E6E4DD ${pct}%, #E6E4DD 100%)`;
    }

    function setSliders(p) {
        sliders.cloud.value      = p.cloud;
        sliders.temp.value       = p.temp;
        sliders.irradiance.value = p.irradiance;
        sliders.soiling.value    = p.soiling;
        updateValLabels(p);
    }

    Object.values(sliders).forEach(s => {
        s.addEventListener('input', () => {
            updateValLabels(readSliders());
        });
        // Initial gradient fill
        updateSliderFill(s);
    });

    // ── Physics engine ───────────────────────────────────────────────────
    function applyScenario(baseP50, params) {
        const { cloud, temp, irradiance, soiling } = params;
        const cloudFactor = 1.0 - (cloud / 100) * 0.8;
        const irrFactor   = irradiance / 100;
        const combinedIrr = Math.sqrt(Math.max(0, cloudFactor * irrFactor));
        const tempFactor  = 1.0 - 0.004 * Math.max(0, temp);
        const soilFactor  = 1.0 - soiling / 100;
        const factor = Math.min(1.3, Math.max(0, combinedIrr * tempFactor * soilFactor));
        return +(baseP50 * factor).toFixed(3);
    }

    // Compute KPIs for a set of rows + params (used by comparison chart too)
    function computeKPIs(rows, params) {
        let basePeak = 0, scenPeak = 0, baseEnergy = 0, scenEnergy = 0;
        rows.forEach(row => {
            const p50 = row.forecast_p50_mw;
            const adj = applyScenario(p50, params);
            if (p50 > basePeak) basePeak = p50;
            if (adj > scenPeak) scenPeak = adj;
            baseEnergy += p50;
            scenEnergy += adj;
        });
        const dropPct   = basePeak > 0 ? ((scenPeak - basePeak) / basePeak * 100) : 0;
        const energyLoss = baseEnergy - scenEnergy;
        return { basePeak, scenPeak, dropPct, energyLoss };
    }

    // ── Main render ──────────────────────────────────────────────────────
    function render(params) {
        const rows = activeRows;
        if (!rows || !rows.length) {
            chart.data = { labels: [], datasets: [] };
            chart.update();
            document.getElementById('kpi-base-peak').textContent  = '—';
            document.getElementById('kpi-scen-peak').textContent  = '—';
            document.getElementById('kpi-drop').textContent       = '—';
            document.getElementById('kpi-energy-loss').textContent = '—';
            document.getElementById('scenario-tbody').innerHTML   = '';
            return;
        }

        const labels = [], baseVals = [], scenVals = [];
        const kpi = computeKPIs(rows, params);

        rows.forEach(row => {
            const p50 = row.forecast_p50_mw;
            labels.push(formatTs(row.timestamp));
            baseVals.push(p50);
            scenVals.push(applyScenario(p50, params));
        });

        // Time-series chart
        chart.data = {
            labels,
            datasets: [
                {
                    label: translate('chart-baseline'),
                    data: baseVals,
                    borderColor: C.muted,
                    backgroundColor: 'rgba(122,119,113,0.1)',
                    borderWidth: 2, borderDash: [6, 3],
                    fill: false, pointRadius: 0, tension: 0.35,
                },
                {
                    label: translate('chart-scenario'),
                    data: scenVals,
                    borderColor: C.primary,
                    backgroundColor: C.fill,
                    borderWidth: 2.5, fill: true,
                    pointRadius: 0, tension: 0.35,
                },
            ]
        };
        chart.update();

        // KPI cards
        document.getElementById('kpi-base-peak').textContent    = `${kpi.basePeak.toFixed(1)} MW`;
        document.getElementById('kpi-scen-peak').textContent    = `${kpi.scenPeak.toFixed(1)} MW`;
        document.getElementById('kpi-drop').textContent         = `${kpi.dropPct > 0 ? '+' : ''}${kpi.dropPct.toFixed(1)}%`;
        document.getElementById('kpi-energy-loss').textContent  = `${kpi.energyLoss.toFixed(1)} MWh`;

        const dropEl = document.getElementById('kpi-drop');
        dropEl.style.color = kpi.dropPct < 0 ? C.bad : kpi.dropPct > 0 ? C.good : C.muted;

        // Hourly table
        const tbody = document.getElementById('scenario-tbody');
        tbody.innerHTML = '';
        rows.forEach((row, i) => {
            const base = baseVals[i], scen = scenVals[i];
            const delta = scen - base;
            const pct   = base > 0 ? (delta / base * 100) : 0;
            const tr = document.createElement('tr');
            const isDaylight = base > 0.01;
            tr.innerHTML = `
                <td>${labels[i]}</td>
                <td>${base.toFixed(2)}</td>
                <td>${scen.toFixed(2)}</td>
                <td style="color:${delta < -0.01 ? C.bad : delta > 0.01 ? C.good : C.muted}">${delta >= 0 ? '+' : ''}${delta.toFixed(2)}</td>
                <td style="color:${pct < -1 ? C.bad : pct > 1 ? C.good : C.muted}">${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%</td>
            `;
            if (!isDaylight) tr.style.opacity = '0.35';
            tbody.appendChild(tr);
        });

        // Multi-direction comparison (only when scope = national)
        if (currentScope === 'national' && compareChart) renderComparison(params);
    }

    // ── Multi-direction comparison ────────────────────────────────────────
    async function renderComparison(params) {
        if (!comparePanel || !compareChart) return;
        comparePanel.hidden = false;

        const results = [];
        for (const dirName of directionNames) {
            let rows = cache.direction[dirName] || [];
            // Fetch if not yet loaded
            if (!rows.length) {
                try {
                    const res = await fetch(`${API_BASE}/forecast/direction/${encodeURIComponent(dirName)}?horizon_days=1`);
                    const data = await res.json();
                    rows = todayFilter(Array.isArray(data) ? data : []);
                    cache.direction[dirName] = rows;
                } catch (_) { rows = []; }
            }
            if (!rows.length) continue;
            const kpi = computeKPIs(rows, params);
            results.push({ name: dirName, ...kpi });
        }

        if (!results.length) return;

        // Sort by reduction % (worst first)
        results.sort((a, b) => a.dropPct - b.dropPct);

        const labels = results.map(r => r.name);
        const baseData = results.map(r => +r.basePeak.toFixed(2));
        const scenData = results.map(r => +r.scenPeak.toFixed(2));

        compareChart.data = {
            labels,
            datasets: [
                {
                    label: translate('chart-baseline'),
                    data: baseData,
                    backgroundColor: 'rgba(122,119,113,0.35)',
                    borderColor: C.muted,
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: translate('chart-scenario'),
                    data: scenData,
                    backgroundColor: C.fill,
                    borderColor: C.primary,
                    borderWidth: 1,
                    borderRadius: 4,
                },
            ]
        };
        compareChart.update();

        // Comparison table
        const tbody = document.getElementById('compare-tbody');
        tbody.innerHTML = '';
        results.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${r.name}</strong></td>
                <td>${r.basePeak.toFixed(2)}</td>
                <td>${r.scenPeak.toFixed(2)}</td>
                <td style="color:${r.dropPct < 0 ? C.bad : r.dropPct > 0 ? C.good : C.muted}">${r.dropPct >= 0 ? '+' : ''}${r.dropPct.toFixed(1)}%</td>
                <td style="color:${r.energyLoss > 0 ? C.bad : C.muted}">${r.energyLoss.toFixed(1)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    // ── Preset buttons ────────────────────────────────────────────────────
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const preset = PRESETS[btn.dataset.preset];
            if (!preset) return;
            setSliders(preset);
            render(preset);
            document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // ── Apply / Reset buttons ────────────────────────────────────────────
    document.getElementById('btn-apply').addEventListener('click', () => {
        const params = readSliders();
        render(params);
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    });

    document.getElementById('btn-reset').addEventListener('click', () => {
        setSliders({ cloud: 0, temp: 0, irradiance: 100, soiling: 0 });
        render({ cloud: 0, temp: 0, irradiance: 100, soiling: 0 });
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    });

    // ── Initial render ────────────────────────────────────────────────────
    render({ cloud: 0, temp: 0, irradiance: 100, soiling: 0 });
}
