/* ESCANOR Dashboard entrypoint. Loads modules in dependency order. */
(function loadDashboardModules() {
    const modules = [
        'i18n.js',          // Translations + language engine (no deps)
        'utils.js',         // Design tokens, Chart.js helpers, status poller (uses translate from i18n)
        'core.js',          // Page router + Prosol modal (uses i18n + utils)
        'home.js',          // Page: National Overview
        'districts.js',     // Page: Regional Analysis
        'map.js',           // Page: Spatial Timelapse
        'performance.js',   // Page: Model Health
        'alerts.js',        // Page: Alerts
        'registry.js',      // Page: Park Registry
        'prosol-history.js',// Page: Prosol History
        'scenarios.js',     // Page: What-If Scenarios
    ];

    modules.forEach(module => {
        document.write(`<script src="assets/js/${module}"><\/script>`);
    });
}());
