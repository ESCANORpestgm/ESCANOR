/* PréSol Dashboard entrypoint. Page logic is split by responsibility for easier maintenance. */
(function loadDashboardModules() {
    const modules = [
        'core.js',
        'home.js',
        'districts.js',
        'map.js',
        'performance.js',
        'alerts.js',
        'registry.js',
        'prosol-history.js',
    ];

    modules.forEach(module => {
        document.write(`<script src="assets/js/${module}"><\/script>`);
    });
}());
