/* ============================================================
   ESCANOR Dashboard — app lifecycle and page router
   Depends on: i18n.js, utils.js (loaded before this file)
   ============================================================ */

// ── Page router ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    validateTranslations();
    await applyI18n(currentLang);

    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => applyI18n(btn.dataset.lang));
    });

    await fetchStatus();
    await fetchAlertBadge();

    // Wire Prosol modal trigger on all pages if button exists
    setupProsolReportModal();

    const page = document.body.getAttribute('data-page');
    if (page === 'home')           initHome();
    if (page === 'districts')      initDistricts();
    if (page === 'map')            initTimelapseMap();
    if (page === 'performance')    initPerformance();
    if (page === 'alerts')         initAlerts();
    if (page === 'registry')       initRegistry();
    if (page === 'prosol-history') initProsolHistory();
    if (page === 'scenarios')      initScenarios();
});

// ── Prosol Report Studio Modal (global) ─────────────────────────────────────

function setupProsolReportModal() {
    const btnOpen = document.getElementById('btn-open-prosol-modal');
    const modal = document.getElementById('prosolModal');
    const btnClose = document.getElementById('btnCloseProsolModal');
    const btnDownload = document.getElementById('btnDownloadProsolJson');
    const reportLink = document.getElementById('btn-open-prosol-html');
    const freshSummaryUrl = () => `${API_BASE}/reports/prosol/summary?_=${Date.now()}`;
    const freshReportUrl = () => `${API_BASE}/reports/prosol/html?_=${Date.now()}`;

    if (reportLink) {
        reportLink.href = freshReportUrl();
        reportLink.addEventListener('click', () => {
            reportLink.href = freshReportUrl();
        });
    }
    if (!btnOpen || !modal) return;

    btnOpen.addEventListener('click', async () => {
        modal.classList.remove('hidden');
        const previewEl = document.getElementById('modalMetricsPreview');
        if (!previewEl) return;
        try {
            const res = await fetch(freshSummaryUrl(), { cache: 'no-store' });
            if (!res.ok) throw new Error(`Report summary request failed with ${res.status}`);
            const data = await res.json();
            const ind = data.indicators || [];
            const pInst = ind.find(x => x.id === 2)?.since_2011 ?? 0;
            const nInst = ind.find(x => x.id === 1)?.since_2011 ?? 0;
            const nPending = data.recap_executions?.pending_current ?? 0;
            const compRate = data.recap_executions?.completion_rate_pct ?? 0;
            previewEl.innerHTML = `
                <div class="preview-stat-box">
                    <div class="val">${pInst.toFixed(1)} MWc</div>
                    <div class="lbl">Puissance Cumulée Raccordée</div>
                </div>
                <div class="preview-stat-box">
                    <div class="val">${nInst.toLocaleString()}</div>
                    <div class="lbl">Installations Réalisées</div>
                </div>
                <div class="preview-stat-box">
                    <div class="val">${nPending.toLocaleString()}</div>
                    <div class="lbl">Dossiers en Attente</div>
                </div>
                <div class="preview-stat-box">
                    <div class="val">${compRate.toFixed(1)}%</div>
                    <div class="lbl">Taux d'Exécution Q1 2026</div>
                </div>
            `;
        } catch (e) {
            previewEl.innerHTML = `<div style="grid-column:span 2;color:var(--status-bad);">Impossible de charger la synthèse.</div>`;
        }
    });

    if (btnClose) {
        btnClose.addEventListener('click', () => modal.classList.add('hidden'));
    }

    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.add('hidden');
    });

    if (btnDownload) {
        btnDownload.addEventListener('click', async () => {
            try {
                const res = await fetch(freshSummaryUrl(), { cache: 'no-store' });
                if (!res.ok) throw new Error(`Report summary request failed with ${res.status}`);
                const json = await res.json();
                const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'steg_prosol_summary.json';
                a.click();
                URL.revokeObjectURL(url);
            } catch (e) {
                alert('Erreur lors du téléchargement');
            }
        });
    }
}
