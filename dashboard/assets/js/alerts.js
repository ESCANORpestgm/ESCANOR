
// ═══════════════════════════════════════════════════════════════════════════
// PAGE 5: ALERTS & SATURATION MONITORING
// ═══════════════════════════════════════════════════════════════════════════
async function initAlerts() {
    const list = document.getElementById('alert-list');
    try {
        const res  = await fetch(`${API_BASE}/alerts`);
        const data = await res.json();
        const alerts = data.alerts || [];
        list.innerHTML = '';

        if (alerts.length === 0) {
            list.innerHTML = `
                <div class="no-alerts">
                    <span class="no-alert-icon">✅</span>
                    All operational parameters within nominal thresholds. No active alerts.
                </div>`;
            return;
        }

        alerts.forEach(alert => {
            const isCrit = alert.severity === 'critical';
            const div = document.createElement('div');
            div.className = `alert-item ${isCrit ? 'critical' : 'warning'}`;
            const icon = alert.type === 'SATURATION_RISK' ? '⚡' : (isCrit ? '⚠️' : 'ℹ️');
            div.innerHTML = `
                <span class="alert-icon">${icon}</span>
                <div class="alert-body">
                    <div class="alert-type">${alert.type.replace(/_/g, ' ')} ${alert.district ? `(${alert.district})` : ''}</div>
                    <div class="alert-detail">${alert.detail}</div>
                    <div class="alert-ts">${alert.timestamp}</div>
                </div>`;
            list.appendChild(div);
        });
    } catch (e) {
        if (list) list.innerHTML = `<div class="no-alerts"><span class="no-alert-icon">❌</span>Could not reach API to fetch alerts.</div>`;
    }
}
