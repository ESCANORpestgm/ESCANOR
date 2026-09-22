
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
const DIRECTION_ZOOM_MAX = 7;


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
        leafletMap.on('zoomend', () => renderFrame(currentFrameIdx));

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
    if (leafletMap.getZoom() <= DIRECTION_ZOOM_MAX) {
        renderDirectionMarkers(frame);
    } else {
        renderDistrictMarkers(frame);
    }
}

function markerStyle(p50, utilization, uncertaintyRatio) {
    return {
        color: uncertaintyColor(uncertaintyRatio || 0),
        weight: 2.5,
        fillColor: C.primary,
        fillOpacity: Math.min(0.95, Math.max(0.3, (utilization || 0) / 100)),
        radius: Math.max(7, Math.sqrt(Math.max(p50, 0)) * 4.2),
    };
}


function renderDistrictMarkers(frame) {
    frame.governorates.forEach(g => {
        if (!g.lat || !g.lon || g.p50 <= 0.03) return;
        const marker = L.circleMarker([g.lat, g.lon], markerStyle(g.p50, g.utilization_pct, g.uncertainty_ratio));
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

function renderDirectionMarkers(frame) {
    const directions = {};
    frame.governorates.forEach(g => {
        if (!g.lat || !g.lon || g.p50 <= 0.03) return;
        const direction = g.direction || 'STEG';
        const item = directions[direction] ||= {
            lat: 0, lon: 0, count: 0, p10: 0, p50: 0, p90: 0, capacity: 0,
        };
        item.lat += g.lat;
        item.lon += g.lon;
        item.count += 1;
        item.p10 += g.p10 || 0;
        item.p50 += g.p50 || 0;
        item.p90 += g.p90 || 0;
        item.capacity += Number(g.cap || 0);
    });

    Object.entries(directions).forEach(([direction, item]) => {
        item.lat /= item.count;
        item.lon /= item.count;
        const uncertainty = item.p90 - item.p10;
        const utilization = item.capacity ? 100 * item.p50 / item.capacity : 0;
        const marker = L.circleMarker([item.lat, item.lon], markerStyle(item.p50, utilization, uncertainty / Math.max(item.p50, 0.01)));
        marker.bindPopup(
            `<strong>${direction}</strong><br>` +
            `${item.count} districts<br>` +
            `P50: <strong>${item.p50.toFixed(2)} MW</strong><br>` +
            `Uncertainty: ±${(uncertainty / 2).toFixed(2)} MW<br>` +
            `<small>Direction-level statistics only</small>`
        );
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
                plugins: { legend: { display: false }, tooltip: { backgroundColor: C.bg, titleColor: C.text, bodyColor: C.muted, borderColor: C.border, borderWidth: 1 }, zoom: _chartZoom },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
                    y: { grid: { color: 'rgba(230,228,221,0.5)' }, border: { display: false }, beginAtZero: true, ticks: { font: { size: 10 } } }
                },
            }
        });
    } catch (e) { console.error('Drilldown chart error', e); }
}
