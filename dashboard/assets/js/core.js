/* ============================================================
   PréSol Dashboard — app.js v3 (STEG Prosol 50-District Release)
   STEG National PV Forecast Platform
   Features:
   - 50 STEG Commercial Districts & 7 Directions de Distribution
   - Prosol Multi-Vector Energy & Fuel Displacement Strip
   - Gross Generation ↔ Net Grid Injection (64.07%) toggle
   - Prosol Report Studio Modal with official KPIs and JSON export
   - Spatial map drilldown with live solar irradiance (GHI), temp, wind, clouds
   - 7-Direction Regional Weather Snapshot Grid
   - Hourly Model Prediction Breakdown (P10/P50/P90 Quantiles)
   - Dynamic Capacity Backlog Pipeline with 30d/90d growth projections
   - Saturation and reverse-flow feeder monitoring
   ============================================================ */

const API_BASE = 'http://localhost:8000';

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
    text:    '#2D2B28',
    muted:   '#7A7771',
    primary: '#DA7756',
    fill:    'rgba(218, 119, 86, 0.12)',
    net:     '#0ea5e9',
    netFill: 'rgba(14, 165, 233, 0.12)',
    good:    '#517A63',
    warn:    '#D9A05B',
    bad:     '#C0392B',
    bg:      '#FFFFFF',
    border:  '#E6E4DD',
};
if (typeof Chart !== 'undefined') {
    Chart.defaults.color       = C.muted;
    Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
    Chart.defaults.font.size   = 12;
}

// ── i18n ────────────────────────────────────────────────────────────────────
const I18N = {
    en: {
        'brand-sub':          'STEG PV Forecasting',
        'nav-national':       'National Overview',
        'nav-regional':       'Regional Analysis',
        'nav-map':            'Spatial Timelapse',
        'nav-perf':           'Model Health',
        'nav-alerts':         'Alerts',
        'nav-registry':       'Park Registry',
        'nav-prosol-report':  'STEG Prosol Report',
        'nav-prosol-history': 'Prosol History',
        'home-title':         'National Overview',
        'home-sub':           'Aggregated generation forecast for the Tunisian national grid (J to J+3) across 50 STEG commercial districts.',
        'kpi-current':        'Current Estimated Output',
        'kpi-today':          'Peak Forecast (Today)',
        'kpi-tmrw':           'Peak Forecast (Tomorrow)',
        'kpi-capacity':       'Installed Capacity',
        'chart-national-title': 'National PV Generation Forecast',
        'chart-intraday-title': 'Intra-Day Forecast (15-min resolution)',
        'districts-title':    'Regional Analysis',
        'districts-sub':      'Granular P10/P50/P90 forecasts across 50 STEG commercial districts and 7 Directions de Distribution with detailed model predictions.',
        'map-title':          'Spatial Timelapse Map',
        'map-sub':            'Interactive spatial map of all 50 STEG commercial districts. Click any circle to drill down into weather and 72-hour forecast.',
        'perf-title':         'Model Health & Diagnostics',
        'perf-sub':           'Backtesting results and continuous learning retrain history.',
        'perf-hist-title':    'Historical Accuracy (Last 30 Days)',
        'perf-metrics-title': 'Quantile Model Metrics (By Horizon)',
        'perf-retrain-title': 'Continuous Learning — Retrain Log',
        'alerts-title':       'Operational Alerts',
        'alerts-sub':         'Real-time warnings for Dispatching National including reverse flow and feeder saturation risks.',
        'alerts-thresholds':  'Alert Thresholds',
        'alerts-active':      'Active Alerts',
        'alerts-info':        'Alert Types Explained',
        'registry-title':     'PV Park Registry & Pipeline',
        'registry-sub':       'Official data for all 50 STEG commercial districts and dynamic capacity expansion projections.',
        'registry-table-title': 'District Inventory',
        'registry-cards-title': 'Capacity by Direction',
        'districts-label':    'Commercial Districts',
        'filter-all':         'All',
        'district-count':     'DISTRICTS',
        'api-offline':        'API Offline',
        'updated-minutes':    'Updated {{minutes}} min ago',
        'capacity-status':    'Capacity: {{value}} MWc',
        'source-status':      'Source: {{source}}',
        'district-title':     'STEG District: {{name}}',
        'direction-label':    'Direction: {{name}}',
        'table-district':     'District',
        'table-direction':    'Direction',
        'table-capacity':     'Capacity (MWc)',
        'table-peak':         'Peak J+1',
        'search-district-placeholder': '🔍 Search a STEG district…',
        'select-district':    'Select a district',
        'model-detail':       '🔬 Model Prediction Details (P10 / P50 / P90 & Weather)',
        'next-48-hours':      'Next 48 hours',
        'peak-pessimistic':   'P10 (Pessimistic)',
        'peak-median':        'P50 (Median)',
        'peak-optimistic':    'P90 (Optimistic)',
        'peak-hour':          'J+1 Peak Hour',
        'status-connecting':  'Connecting…',
        'status-cap':         'Capacity: -- MWc',
        'prosol-history-title': 'Prosol Report History',
        'prosol-history-sub': 'Immutable monthly rooftop-PV snapshots aligned with the official STEG report structure.',
        'report-snapshot':     'Report snapshot',
        'loading':             'Loading…',
        'national-metrics':    'National metrics',
        'installations-direction': 'Installations by Direction',
        'district-snapshot':   'District snapshot',
        'pending-dossiers':    'Pending dossiers',
        'add-installations':   'Add new rooftop PV installations',
        'select-district-option': 'Select district…',
        'new-pvs':             'New PVs',
        'capacity-optional':   'Capacity (kWc, optional)',
        'add-installations-button': 'Add installations',
        'new-installed-pvs':   'New installed PVs by district',
        'download-csv':        'Download CSV',
        'official-prosol-note': 'Official Prosol installation counts for the selected snapshot; aggregated district data, not individual rooftop records.',
        'installation-sizes': 'Installation sizes (kWc)',
        'saved-evaluations':   'Saved Forecast Evaluations',
        'synthetic-validation': 'Synthetic validation only',
                'pvgis-modeled':      'PVGIS modeled data',
        'observations':        'Observations',
        'forecast-refresh':    'Forecast refresh',
        'candidate-training':  'Candidate training',
        'daily':               'Daily',
        'every-15-minutes':    'Every 15 minutes',
        'current-source':      'Current source',
        'continuous-status':   'Continuous learning: daily candidate training from the latest validated rooftop measurement snapshot; promotion only when candidate validation improves.',
        'play': 'Play', 'aggregate': 'Aggregate:', 'low-uncertainty': 'Low uncertainty', 'medium-uncertainty': 'Medium', 'high-uncertainty': 'High',
        'refresh-alerts': 'Refresh Alerts', 'uncertainty-threshold': 'Uncertainty threshold (MW)', 'ramp-threshold': 'Ramp-down threshold (%)',
        'all-directions': 'All Directions', 'commercial-district': 'Commercial District', 'governorate': 'Governorate',
        'installed-capacity': 'Installed Capacity (MWc)', 'pending-dossiers-label': 'Pending dossiers', 'execution-rate': 'Execution rate', 'district-label': 'District', 'month-label': 'Month', 'ytd-label': 'YTD', 'since-start-label': 'Since start', 'share-label': 'Share', 'official-month-label': 'Official month', 'added-live-label': 'Added live', 'current-ytd-label': 'Current YTD',
    },
    fr: {
        'brand-sub':          'Prévision PV STEG',
        'nav-national':       'Vue nationale',
        'nav-regional':       'Analyse régionale',
        'nav-map':            'Carte spatio-temporelle',
        'nav-perf':           'Santé du modèle',
        'nav-alerts':         'Alertes',
        'nav-registry':       'Registre du parc',
        'nav-prosol-report':  'Rapport STEG Prosol',
        'nav-prosol-history': 'Historique Prosol',
        'home-title':         'Vue nationale',
        'home-sub':           'Prévision agrégée sur le réseau national (J à J+3) couvrant les 50 districts commerciaux STEG.',
        'kpi-current':        'Production estimée actuelle',
        'kpi-today':          'Pic prévu (aujourd\'hui)',
        'kpi-tmrw':           'Pic prévu (demain)',
        'kpi-capacity':       'Puissance raccordée',
        'chart-national-title': 'Prévision de production PV nationale',
        'chart-intraday-title': 'Prévision intra-journalière (résolution 15 min)',
        'districts-title':    'Analyse régionale',
        'districts-sub':      'Prévisions granulaires P10/P50/P90 par district commercial et Direction avec décomposition des quantiles.',
        'map-title':          'Carte spatio-temporelle',
        'map-sub':            'Carte interactive des 50 districts STEG avec météo solaire en direct et bandes d\'incertitude.',
        'perf-title':         'Santé & diagnostics du modèle',
        'perf-sub':           'Résultats de backtest et historique du réapprentissage continu.',
        'perf-hist-title':    'Précision historique (30 derniers jours)',
        'perf-metrics-title': 'Métriques du modèle quantile (par horizon)',
        'perf-retrain-title': 'Apprentissage continu — journal de réentraînement',
        'alerts-title':       'Alertes opérationnelles',
        'alerts-sub':         'Avertissements en temps réel pour le Dispatching National dont saturation de départs.',
        'alerts-thresholds':  'Seuils d\'alerte',
        'alerts-active':      'Alertes actives',
        'alerts-info':        'Types d\'alertes',
        'registry-title':     'Registre Prosol & Pipeline STEG',
        'registry-sub':       'Données officielles des 50 districts commerciaux STEG et projection dynamique des raccordements.',
        'registry-table-title': 'Inventaire des districts',
        'registry-cards-title': 'Capacité par Direction',
        'districts-label':    'Districts commerciaux',
        'filter-all':         'Tous',
        'district-count':     'DISTRICTS',
        'api-offline':        'API hors ligne',
        'updated-minutes':    'Mis à jour il y a {{minutes}} min',
        'capacity-status':    'Capacité : {{value}} MWc',
        'source-status':      'Source : {{source}}',
        'district-title':     'District STEG : {{name}}',
        'direction-label':    'Direction : {{name}}',
        'table-district':     'District',
        'table-direction':    'Direction',
        'table-capacity':     'Cap (MWc)',
        'table-peak':         'Pic J+1',
        'search-district-placeholder': '🔍 Rechercher un district STEG…',
        'select-district':    'Sélectionnez un district',
        'model-detail':       '🔬 Détail des prédictions du modèle (P10 / P50 / P90 & météo)',
        'next-48-hours':      'Prochaines 48 heures',
        'peak-pessimistic':   'P10 (Pessimiste)',
        'peak-median':        'P50 (Médian)',
        'peak-optimistic':    'P90 (Optimiste)',
        'peak-hour':          'Heure de pic J+1',
        'status-connecting':  'Connexion…',
        'status-cap':         'Capacité : -- MWc',
        'prosol-history-title': 'Historique des rapports Prosol',
        'prosol-history-sub': 'Instantanés mensuels immuables du photovoltaïque résidentiel selon la structure officielle STEG.',
        'report-snapshot':     'Instantané du rapport',
        'loading':             'Chargement…',
        'national-metrics':    'Indicateurs nationaux',
        'installations-direction': 'Installations par Direction',
        'district-snapshot':   'Situation par district',
        'pending-dossiers':    'Dossiers en instance',
        'add-installations':   'Ajouter de nouvelles installations PV',
        'select-district-option': 'Sélectionnez un district…',
        'new-pvs':             'Nouveaux PV',
        'capacity-optional':   'Puissance (kWc, facultatif)',
        'add-installations-button': 'Ajouter les installations',
        'new-installed-pvs':   'Nouvelles installations PV par district',
        'download-csv':        'Télécharger le CSV',
        'official-prosol-note': 'Comptages officiels Prosol pour l’instantané sélectionné ; données agrégées par district, sans systèmes individuels.',
        'installation-sizes': 'Puissances des installations (kWc)',
        'saved-evaluations':   'Évaluations de prévisions enregistrées',
        'synthetic-validation': 'Validation synthétique uniquement',
                'pvgis-modeled':      'Données modélisées PVGIS',
        'observations':        'Observations',
        'forecast-refresh':    'Actualisation des prévisions',
        'candidate-training':  'Entraînement candidat',
        'daily':               'Quotidien',
        'every-15-minutes':    'Toutes les 15 minutes',
        'current-source':      'Source actuelle',
        'continuous-status':   'Apprentissage continu : entraînement quotidien à partir du dernier instantané rooftop validé ; promotion uniquement si la validation progresse.',
        'play': 'Lecture', 'aggregate': 'Total :', 'low-uncertainty': 'Faible incertitude', 'medium-uncertainty': 'Moyenne', 'high-uncertainty': 'Élevée',
        'refresh-alerts': 'Actualiser les alertes', 'uncertainty-threshold': 'Seuil d’incertitude (MW)', 'ramp-threshold': 'Seuil de baisse (%)',
        'all-directions': 'Toutes les Directions', 'commercial-district': 'District commercial', 'governorate': 'Gouvernorat',
        'installed-capacity': 'Puissance installée (MWc)', 'pending-dossiers-label': 'Dossiers en instance', 'execution-rate': 'Taux de réalisation', 'district-label': 'District', 'month-label': 'Mois', 'ytd-label': 'Cumul annuel', 'since-start-label': 'Depuis le début', 'share-label': 'Part', 'official-month-label': 'Mois officiel', 'added-live-label': 'Ajout en direct', 'current-ytd-label': 'Cumul actuel',
    },
    ar: {
        'brand-sub':          'توقعات الطاقة الشمسية — الستاغ',
        'nav-national':       'نظرة عامة وطنية',
        'nav-regional':       'تحليل جهوي',
        'nav-map':            'خريطة التوزيع الزمني',
        'nav-perf':           'صحة النموذج',
        'nav-alerts':         'التنبيهات',
        'nav-registry':       'سجل المنظومات',
        'nav-prosol-report':  'تقرير بروسول الرسمي',
        'nav-prosol-history': 'سجل تقارير بروسول',
        'home-title':         'نظرة عامة وطنية',
        'home-sub':           'توقعات الإنتاج الوطني المربوط بالشبكة (من اليوم إلى 3 أيام قادمة) عبر 50 إقليماً تجارياً للستاغ.',
        'kpi-current':        'الإنتاج التقديري الحالي',
        'kpi-today':          'الذروة المتوقعة (اليوم)',
        'kpi-tmrw':           'الذروة المتوقعة (غداً)',
        'kpi-capacity':       'القدرة الجملية المركبة',
        'chart-national-title': 'توقعات الإنتاج الوطني للطاقة الشمسية',
        'chart-intraday-title': 'التوقعات خلال اليوم (دقة 15 دقيقة)',
        'districts-title':    'التحليل الجهوي بالأقاليم',
        'districts-sub':      'توقعات مفصلة P10/P50/P90 للأقاليم التجارية الخمسين للستاغ.',
        'map-title':          'الخريطة التفاعلية للأقاليم',
        'map-sub':            'توزيع جغرافي مباشر لإنتاج وأحوال الطقس لـ 50 إقليماً تجارياً للستاغ.',
        'perf-title':         'صحة النموذج والتشخيص',
        'perf-sub':           'نتائج الاختبار التاريخي وسجل إعادة التدريب التلقائي.',
        'perf-hist-title':    'الدقة التاريخية (آخر 30 يوماً)',
        'perf-metrics-title': 'مؤشرات دقة النموذج حسب الأفق',
        'perf-retrain-title': 'التعلم المستمر — سجل إعادة التدريب',
        'alerts-title':       'تنبيهات مركز التحكم الوطني',
        'alerts-sub':         'تحذيرات فورية لتشغيل الشبكة الكهربائية وخطر تدفق الطاقة العكسي.',
        'alerts-thresholds':  'عتبات التنبيه',
        'alerts-active':      'التنبيهات النشطة',
        'alerts-info':        'شرح التنبيهات',
        'registry-title':     'سجل الأقاليم ومخطط التوسعة',
        'registry-sub':       'بيانات رسمية لـ 50 إقليماً تجارياً ومخطط ربط الملفات العالقة.',
        'registry-table-title': 'قائمة الأقاليم',
        'registry-cards-title': 'القدرة حسب إدارة التوزيع',
        'districts-label':    'الأقاليم التجارية',
        'filter-all':         'الكل',
        'district-count':     'إقليم',
        'api-offline':        'الواجهة غير متصلة',
        'updated-minutes':    'تم التحديث منذ {{minutes}} دقيقة',
        'capacity-status':    'القدرة: {{value}} ميغاواط',
        'source-status':      'المصدر: {{source}}',
        'district-title':     'إقليم الستاغ: {{name}}',
        'direction-label':    'الإدارة: {{name}}',
        'table-district':     'الإقليم',
        'table-direction':    'الإدارة',
        'table-capacity':     'القدرة (ميغاواط)',
        'table-peak':         'الذروة غ+1',
        'search-district-placeholder': '🔍 ابحث عن إقليم تابع للستاغ…',
        'select-district':    'اختر إقليماً',
        'model-detail':       '🔬 تفاصيل توقعات النموذج (P10 / P50 / P90 والطقس)',
        'next-48-hours':      'الساعات الـ48 القادمة',
        'peak-pessimistic':   'P10 (متشائم)',
        'peak-median':        'P50 (متوسط)',
        'peak-optimistic':    'P90 (متفائل)',
        'peak-hour':          'ساعة الذروة غ+1',
        'status-connecting':  'جار الاتصال…',
        'status-cap':         'القدرة: -- ميغاواط',
        'prosol-history-title': 'سجل تقارير بروسول',
        'prosol-history-sub': 'لقطات شهرية غير قابلة للتغيير للطاقة الشمسية وفق الهيكل الرسمي لتقارير الستاغ.',
        'report-snapshot':     'لقطة التقرير',
        'loading':             'جار التحميل…',
        'national-metrics':    'المؤشرات الوطنية',
        'installations-direction': 'المنظومات حسب إدارة التوزيع',
        'district-snapshot':   'ملخص الإقليم',
        'pending-dossiers':    'الملفات العالقة',
        'add-installations':   'إضافة منظومات شمسية جديدة',
        'select-district-option': 'اختر إقليماً…',
        'new-pvs':             'المنظومات الجديدة',
        'capacity-optional':   'القدرة (kWc، اختياري)',
        'add-installations-button': 'إضافة المنظومات',
        'new-installed-pvs':   'المنظومات الشمسية الجديدة حسب الإقليم',
        'download-csv':        'تنزيل CSV',
        'official-prosol-note': 'أعداد المنظومات الرسمية من بروسول للّقطة المختارة؛ بيانات مجمعة حسب الإقليم وليست منظومات فردية.',
        'installation-sizes': 'أحجام المنظومات (kWc)',
        'saved-evaluations':   'تقييمات التوقعات المحفوظة',
        'synthetic-validation': 'تحقق اصطناعي فقط',
                'pvgis-modeled':      'بيانات نمذجة PVGIS',
        'observations':        'القياسات',
        'forecast-refresh':    'تحديث التوقعات',
        'candidate-training':  'تدريب النموذج المرشح',
        'daily':               'يومياً',
        'every-15-minutes':    'كل 15 دقيقة',
        'current-source':      'المصدر الحالي',
        'continuous-status':   'تعلم مستمر: تدريب يومي اعتماداً على أحدث لقطة قياسات شمسية مصادق عليها؛ لا تتم الترقية إلا عند تحسن التحقق.',
        'play': 'تشغيل', 'aggregate': 'الإجمالي:', 'low-uncertainty': 'عدم يقين منخفض', 'medium-uncertainty': 'متوسط', 'high-uncertainty': 'مرتفع',
        'refresh-alerts': 'تحديث التنبيهات', 'uncertainty-threshold': 'عتبة عدم اليقين (ميغاواط)', 'ramp-threshold': 'عتبة الانخفاض (%)',
        'all-directions': 'كل إدارات التوزيع', 'commercial-district': 'الإقليم التجاري', 'governorate': 'الولاية',
        'installed-capacity': 'القدرة المركبة (ميغاواط)', 'pending-dossiers-label': 'الملفات العالقة', 'execution-rate': 'نسبة الإنجاز', 'district-label': 'الإقليم', 'month-label': 'الشهر', 'ytd-label': 'التراكمي السنوي', 'since-start-label': 'منذ البداية', 'share-label': 'الحصة', 'official-month-label': 'الشهر الرسمي', 'added-live-label': 'الإضافة المباشرة', 'current-ytd-label': 'التراكمي الحالي',
    }
};

const SUPPORTED_LANGS = Object.freeze(Object.keys(I18N));
const i18nResources = Object.fromEntries(
    Object.entries(I18N).map(([language, translations]) => [language, { translation: translations }])
);
const i18nextReady = window.i18next
    ? window.i18next.init({
        lng: 'en',
        fallbackLng: 'en',
        resources: i18nResources,
        interpolation: { escapeValue: false },
    })
    : Promise.resolve();

const savedLang = localStorage.getItem('presol-lang');
const browserLang = (navigator.language || '').slice(0, 2);
let currentLang = SUPPORTED_LANGS.includes(savedLang)
    ? savedLang
    : SUPPORTED_LANGS.includes(browserLang)
        ? browserLang
        : 'en';

function translate(key, options = {}) {
    if (window.i18next?.isInitialized) return window.i18next.t(key, options);
    let value = I18N[currentLang][key] || I18N.en[key] || key;
    return Object.entries(options).reduce(
        (text, [name, replacement]) => text.replace(`{{${name}}}`, replacement),
        value
    );
}

function validateTranslations() {
    const sourceKeys = Object.keys(I18N.en);
    SUPPORTED_LANGS.filter(language => language !== 'en').forEach(language => {
        const missing = sourceKeys.filter(key => !(key in I18N[language]));
        if (missing.length) console.warn(`[i18n] ${language} missing keys:`, missing);
    });
}

async function applyI18n(lang) {
    const safeLang = SUPPORTED_LANGS.includes(lang) ? lang : 'en';
    await i18nextReady;
    if (window.i18next?.isInitialized) await window.i18next.changeLanguage(safeLang);

    currentLang = safeLang;
    localStorage.setItem('presol-lang', safeLang);
    document.documentElement.lang = safeLang;
    document.documentElement.dir  = safeLang === 'ar' ? 'rtl' : 'ltr';

    document.querySelectorAll('.lang-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.lang === safeLang);
    });

    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        let value = translate(key);
        if (!value || value === key) return;
        if (key === 'filter-all' && el.dataset.count) value = `${value} (${el.dataset.count})`;

        // Preserve badges, icons, and other nested markup inside translated headings.
        if (el.children.length) {
            const textNode = [...el.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
            if (textNode) textNode.textContent = value;
        } else {
            el.textContent = value;
        }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const value = translate(el.getAttribute('data-i18n-placeholder'));
        if (value && value !== el.dataset.i18nPlaceholder) el.placeholder = value;
    });
}

// ── Chart Helper ────────────────────────────────────────────────────────────
if (typeof zoomPlugin !== 'undefined' && typeof Chart !== 'undefined') Chart.register(zoomPlugin);
const _chartZoom = {
    pan: { enabled: true, mode: 'x' },
    zoom: { wheel: { enabled: true }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x' },
};
const _chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
        legend: { display: false },
        zoom: _chartZoom,
        tooltip: {
            backgroundColor: C.bg,
            titleColor: C.text,
            bodyColor: C.muted,
            borderColor: C.border,
            borderWidth: 1,
            padding: 10,
            boxPadding: 4,
            usePointStyle: true,
        },
    },
    scales: {
        x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 8, maxRotation: 0 },
        },
        y: {
            grid: { color: 'rgba(230, 228, 221, 0.6)' },
            border: { display: false },
            beginAtZero: true,
            ticks: { callback: v => `${v} MW` },
        },
    },
};

function makeChart(ctx, extraConfig = {}) {
    return new Chart(ctx, {
        type: 'line',
        options: {
            ..._chartDefaults,
            ...extraConfig,
            scales: {
                x: { ..._chartDefaults.scales.x, ...(extraConfig.scales?.x || {}) },
                y: { ..._chartDefaults.scales.y, ...(extraConfig.scales?.y || {}) },
            },
        },
    });
}

function p10p50p90Datasets(labels, p10, p50, p90, customColor = C.primary, customFill = C.fill) {
    return [
        {
            label: 'P90 (Upper bound)',
            data: p90,
            borderColor: 'rgba(217, 160, 91, 0.9)',
            backgroundColor: customFill,
            borderWidth: 1.2,
            borderDash: [4, 3],
            fill: false,
            pointRadius: 0,
            tension: 0.25,
        },
        {
            label: 'P10 (Lower bound)',
            data: p10,
            borderColor: 'rgba(217, 160, 91, 0.9)',
            backgroundColor: customFill,
            borderWidth: 1.2,
            borderDash: [4, 3],
            fill: '-1',
            pointRadius: 0,
            tension: 0.25,
        },
        {
            label: 'P50 (Median)',
            data: p50,
            borderColor: customColor,
            backgroundColor: 'transparent',
            borderWidth: 2.2,
            pointRadius: 0,
            tension: 0.35,
        },
    ];
}

function nowAnnotation() {
    return {
        nowLine: {
            type: 'line',
            xMin: 'Now',
            xMax: 'Now',
            borderColor: '#DA7756',
            borderWidth: 1.5,
            borderDash: [4, 4],
            label: {
                display: true,
                content: 'Now',
                position: 'start',
                backgroundColor: 'rgba(218, 119, 86, 0.9)',
                color: '#fff',
                font: { size: 10, weight: '600' },
                padding: { top: 2, bottom: 2, left: 5, right: 5 },
                borderRadius: 3,
            },
        },
    };
}

function formatTs(tsStr) {
    const d = new Date(tsStr);
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const h = d.getHours().toString().padStart(2, '0');
    return `${days[d.getDay()]} ${h}:00`;
}

// ── Global Status Poller ───────────────────────────────────────────────────
async function fetchStatus() {
    try {
        const [statusRes, cacheRes] = await Promise.all([
            fetch(`${API_BASE}/status`),
            fetch(`${API_BASE}/cache/status`),
        ]);
        const data  = await statusRes.json();
        const cache = await cacheRes.json();

        const dot = document.getElementById('status-dot');
        const stText = document.getElementById('status-text');
        if (stText) stText.innerText = `API: ${data.data_source} (${data.districts_count || 50} dist)`;
        const stCap = document.getElementById('status-cap');
        if (stCap) stCap.innerText = translate('capacity-status', { value: data.total_capacity_mwc });
        if (cache.is_stale && dot) dot.classList.add('warn');

        const ageEl = document.getElementById('cache-age-display');
        if (ageEl && cache.cache_age_min !== null) {
            ageEl.innerText = translate('updated-minutes', { minutes: cache.cache_age_min });
        }

        const dsSrc = document.getElementById('kpi-datasource');
        if (dsSrc) dsSrc.innerText = translate('source-status', { source: data.data_source });
    } catch (e) {
        const txt = document.getElementById('status-text');
        if (txt) txt.innerText = translate('api-offline');
        const dot = document.getElementById('status-dot');
        if (dot) { dot.style.background = C.bad; dot.classList.add('warn'); }
    }
}

async function fetchAlertBadge() {
    try {
        const res  = await fetch(`${API_BASE}/alerts`);
        const data = await res.json();
        const count = data.count || 0;
        document.querySelectorAll('#nav-alert-badge').forEach(el => {
            el.textContent = count;
            el.classList.toggle('visible', count > 0);
        });
    } catch (_) {}
}

// ── ROUTER ──────────────────────────────────────────────────────────────────
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
    if (page === 'home')        initHome();
    if (page === 'districts')   initDistricts();
    if (page === 'map')         initTimelapseMap();
    if (page === 'performance') initPerformance();
    if (page === 'alerts')      initAlerts();
    if (page === 'registry')    initRegistry();
    if (page === 'prosol-history') initProsolHistory();
});

// ═══════════════════════════════════════════════════════════════════════════
// PROSOL REPORT STUDIO MODAL (Global)
// ═══════════════════════════════════════════════════════════════════════════
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
