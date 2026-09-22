
// ═══════════════════════════════════════════════════════════════════════════
// PAGE 5: ALERTS & SATURATION MONITORING
// ═══════════════════════════════════════════════════════════════════════════
const ALERT_REFRESH_INTERVAL_MS = 60 * 1000;

function updateAlertBadges(count) {
    document.querySelectorAll('#nav-alert-badge').forEach(el => {
        el.textContent = count;
        el.classList.toggle('visible', count > 0);
    });

    const countBadge = document.getElementById('alert-count-badge');
    if (countBadge) {
        countBadge.textContent = count === 1 ? '1 active' : `${count} active`;
    }
}

function updateRetrainingStatus(alerts) {
    const status = document.getElementById('model-retraining-alert-status');
    if (!status) return;

    const retrainingAlert = alerts.find(alert =>
        alert.type === 'MODEL_RETRAINING_STARTED' ||
        alert.type === 'MODEL_RETRAINING_FAILED'
    );

    if (!retrainingAlert) {
        status.hidden = true;
        status.className = 'retraining-alert-status';
        status.textContent = '';
        return;
    }

    const failed = retrainingAlert.type === 'MODEL_RETRAINING_FAILED';
    status.hidden = false;
    status.className = `retraining-alert-status ${failed ? 'failed' : 'running'}`;
    status.textContent = failed
        ? `⚠️ Automatic retraining failed. ${retrainingAlert.detail || 'Check the model logs for details.'}`
        : '🔄 Automatic retraining is currently running. The candidate model will be promoted only if validation improves.';
}

function renderAlerts(alerts) {
    const list = document.getElementById('alert-list');
    if (!list) return;

    list.innerHTML = '';
    updateAlertBadges(alerts.length);
    updateRetrainingStatus(alerts);

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
        const failed = alert.type === 'MODEL_RETRAINING_FAILED';
        const div = document.createElement('div');
        div.className = `alert-item ${isCrit || failed ? 'critical' : 'warning'}`;
        const icon = alert.type === 'SATURATION_RISK'
            ? '⚡'
            : alert.type === 'MODEL_RETRAINING_STARTED'
                ? '🔄'
                : failed ? '⛔' : (isCrit ? '⚠️' : 'ℹ️');
        const type = document.createElement('div');
        type.className = 'alert-type';
        type.textContent = `${String(alert.type || '').replace(/_/g, ' ')}${alert.district ? ` (${alert.district})` : ''}`;
        const detail = document.createElement('div');
        detail.className = 'alert-detail';
        detail.textContent = alert.detail || '';
        const timestamp = document.createElement('div');
        timestamp.className = 'alert-ts';
        timestamp.textContent = alert.timestamp || '';

        const body = document.createElement('div');
        body.className = 'alert-body';
        body.append(type, detail, timestamp);
        const iconElement = document.createElement('span');
        iconElement.className = 'alert-icon';
        iconElement.textContent = icon;
        div.append(iconElement, body);
        list.appendChild(div);
    });
}

async function refreshAlerts() {
    const list = document.getElementById('alert-list');
    try {
        const params = new URLSearchParams();
        const uncertainty = document.getElementById('unc-threshold');
        const ramp = document.getElementById('ramp-threshold');
        if (uncertainty && uncertainty.value) params.set('uncertainty_threshold_mw', uncertainty.value);
        if (ramp && ramp.value) params.set('ramp_threshold_pct', ramp.value);
        const query = params.toString();
        const res = await fetch(`${API_BASE}/alerts${query ? `?${query}` : ''}`);
        if (!res.ok) throw new Error(`Alerts request failed with ${res.status}`);
        const data = await res.json();
        renderAlerts(data.alerts || []);
    } catch (e) {
        updateAlertBadges(0);
        const status = document.getElementById('model-retraining-alert-status');
        if (status) status.hidden = true;
        if (list) list.innerHTML = '<div class="no-alerts"><span class="no-alert-icon">❌</span>Could not reach API to fetch alerts.</div>';
    }
}

async function initAlerts() {
    await refreshAlerts();

    const refreshButton = document.getElementById('refresh-alerts-btn');
    if (refreshButton && !refreshButton.dataset.bound) {
        refreshButton.dataset.bound = 'true';
        refreshButton.addEventListener('click', refreshAlerts);
    }

    if (window.__alertsPollTimer) clearInterval(window.__alertsPollTimer);
    window.__alertsPollTimer = window.setInterval(refreshAlerts, ALERT_REFRESH_INTERVAL_MS);
}
