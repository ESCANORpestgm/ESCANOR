
// ═══════════════════════════════════════════════════════════════════════════
// PAGE 6: PARK REGISTRY & EXPANSION PIPELINE (50 STEG Districts)
// ═══════════════════════════════════════════════════════════════════════════
async function initRegistry() {
    try {
        const [distRes, pipeRes] = await Promise.all([
            fetch(`${API_BASE}/steg-districts`),
            fetch(`${API_BASE}/registry/pipeline`),
        ]);
        const districts = await distRes.json();
        const pipeline  = await pipeRes.json();

        // KPIs
        const totalCap = districts.reduce((s, d) => s + d.installed_capacity_mwc, 0);
        const totalPending = districts.reduce((s, d) => s + (d.pending_dossiers || 0), 0);
        const avgExec = districts.reduce((s, d) => s + (d.execution_rate_pct || 75.0), 0) / districts.length;

        document.getElementById('reg-total-cap').innerHTML = `${totalCap.toFixed(1)} <span style="font-size:1rem;color:var(--text-secondary);">MWc</span>`;
        document.getElementById('reg-pending').innerHTML   = `${totalPending.toLocaleString()} <span style="font-size:1rem;color:var(--text-secondary);">demandes</span>`;
        document.getElementById('reg-exec-rate').innerHTML = `${avgExec.toFixed(1)} <span style="font-size:1rem;color:var(--text-secondary);">%</span>`;

        // Collect unique Directions for dropdown filter
        const directions = [...new Set(districts.map(d => d.direction))].sort();
        const distFilter = document.getElementById('reg-district-filter');
        if (distFilter) {
            directions.forEach(dir => {
                const opt = document.createElement('option');
                opt.value = dir; opt.textContent = dir;
                distFilter.appendChild(opt);
            });
        }

        // Tab Switching
        const tabBtnInv = document.getElementById('tabBtnInventory');
        const tabBtnPipe = document.getElementById('tabBtnPipeline');
        const tabContentInv = document.getElementById('tabContentInventory');
        const tabContentPipe = document.getElementById('tabContentPipeline');

        tabBtnInv?.addEventListener('click', () => {
            tabBtnInv.classList.add('active');
            tabBtnPipe?.classList.remove('active');
            tabContentInv.style.display = 'block';
            tabContentPipe.style.display = 'none';
        });

        tabBtnPipe?.addEventListener('click', () => {
            tabBtnPipe.classList.add('active');
            tabBtnInv?.classList.remove('active');
            tabContentPipe.style.display = 'block';
            tabContentInv.style.display = 'none';
        });

        // Render Helpers
        const tbodyInv  = document.getElementById('registry-tbody');
        const tbodyPipe = document.getElementById('pipeline-tbody');
        const cardsGrid = document.getElementById('registry-cards');

        const renderInventory = (data) => {
            if (!tbodyInv) return;
            tbodyInv.innerHTML = '';
            data.forEach(d => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${d.name}</strong></td>
                    <td><span class="registry-district-tag">${d.direction}</span></td>
                    <td>${d.governorate}</td>
                    <td class="mono" style="font-weight:600;">${d.installed_capacity_mwc.toFixed(1)}</td>
                    <td class="mono">${(d.dust_loss_pct * 100).toFixed(1)}%</td>
                    <td class="mono ${d.pending_dossiers > 100 ? 'text-warn' : 'text-muted'}">${d.pending_dossiers}</td>
                    <td class="mono text-good">${(d.execution_rate_pct || 75.0).toFixed(1)}%</td>
                    <td class="text-muted mono" style="font-size:0.8rem;">${d.lat?.toFixed(3)}, ${d.lon?.toFixed(3)}</td>`;
                tbodyInv.appendChild(tr);
            });
        };

        const renderPipeline = (pipeData) => {
            if (!tbodyPipe) return;
            tbodyPipe.innerHTML = '';
            pipeData.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${p.district}</strong></td>
                    <td><span class="registry-district-tag">${p.direction}</span></td>
                    <td class="mono">${p.current_mwc.toFixed(1)} MWc</td>
                    <td class="mono text-warn">${p.pending_dossiers}</td>
                    <td class="mono">${p.exec_rate_pct.toFixed(1)}%</td>
                    <td class="mono">${p.projected_mwc_30d.toFixed(1)} MWc</td>
                    <td class="mono" style="font-weight:700;">${p.projected_mwc_90d.toFixed(1)} MWc</td>
                    <td><span class="growth-badge">+${p.added_mwc_90d.toFixed(2)} MWc</span></td>`;
                tbodyPipe.appendChild(tr);
            });
        };

        const renderCards = (data) => {
            if (!cardsGrid) return;
            cardsGrid.innerHTML = '';
            // Group by Direction
            const byDir = {};
            data.forEach(d => {
                if (!byDir[d.direction]) byDir[d.direction] = { cap: 0, count: 0, pending: 0, districts: [] };
                byDir[d.direction].cap += d.installed_capacity_mwc;
                byDir[d.direction].count += 1;
                byDir[d.direction].pending += (d.pending_dossiers || 0);
                byDir[d.direction].districts.push(d.name);
            });

            Object.keys(byDir).sort().forEach(dir => {
                const info = byDir[dir];
                const card = document.createElement('div');
                card.className = 'registry-card';
                card.innerHTML = `
                    <div class="registry-card-header">
                        <span class="registry-gov-name">Direction ${dir}</span>
                        <span class="registry-district-tag">${info.count} districts</span>
                    </div>
                    <div class="registry-stats">
                        <div class="registry-stat">
                            <div class="stat-label">Puissance Totale</div>
                            <div class="stat-value" style="color:var(--accent-primary);">${info.cap.toFixed(1)} MWc</div>
                        </div>
                        <div class="registry-stat">
                            <div class="stat-label">Dossiers en Instance</div>
                            <div class="stat-value text-warn">${info.pending}</div>
                        </div>
                    </div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.6rem;line-height:1.4;">
                        ${info.districts.slice(0, 6).join(', ')}${info.districts.length > 6 ? ` (+${info.districts.length - 6} autres)` : ''}
                    </div>`;
                cardsGrid.appendChild(card);
            });
        };

        renderInventory(districts);
        renderPipeline(pipeline);
        renderCards(districts);

        // Search & filter
        const filterFn = () => {
            const term = (document.getElementById('reg-search')?.value || '').toLowerCase();
            const selectedDir = distFilter?.value || '';
            const filtered = districts.filter(d =>
                (d.name.toLowerCase().includes(term) || d.direction.toLowerCase().includes(term) || d.governorate.toLowerCase().includes(term)) &&
                (!selectedDir || d.direction === selectedDir)
            );
            renderInventory(filtered);
            const filteredPipe = pipeline.filter(p =>
                (p.district.toLowerCase().includes(term) || p.direction.toLowerCase().includes(term)) &&
                (!selectedDir || p.direction === selectedDir)
            );
            renderPipeline(filteredPipe);
            renderCards(filtered);
        };

        document.getElementById('reg-search')?.addEventListener('input', filterFn);
        distFilter?.addEventListener('change', filterFn);

    } catch (e) { console.error('Registry fetch error', e); }
}