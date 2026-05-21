// ============================================================================
// NeuroBridge 11D Frontend Configuration
// Phase 1 Production - Version 14.8.1
// Grafana iFrame Embed Fix - Same-Origin via Nginx Proxy
// ============================================================================

window.NEUROBRIDGE_CONFIG = {
    // ==========================================================================
    // API CONFIGURATION
    // ==========================================================================
    
    API_BASE_URL:
        localStorage.getItem("NB_API_BASE_URL") ||
        localStorage.getItem("apiBaseUrl") ||
        "http://127.0.0.1:8000",

    API_KEY:
        localStorage.getItem("NB_API_KEY") ||
        localStorage.getItem("apiKey") ||
        "",

    // ==========================================================================
    // GRAFANA CONFIGURATION - NGINX SAME-ORIGIN EMBED (FIXED)
    // ==========================================================================
    // CRITICAL: GRAFANA_URL must use the nginx reverse proxy path (/grafana/)
    // for same-origin iframe embedding to work. Direct URLs (localhost:3000)
    // will be blocked by X-Frame-Options and CORS policies.
    //
    // With nginx proxy:
    //   - Browser sees same origin (localhost:80)
    //   - X-Frame-Options: SAMEORIGIN works correctly
    //   - Cookies and auth flow properly
    //   - No CORS issues
    // ==========================================================================
    
    GRAFANA_URL:
        localStorage.getItem("NB_GRAFANA_URL") ||
        localStorage.getItem("grafanaUrl") ||
        "/grafana/",  // Nginx reverse proxy path - SAME ORIGIN (REQUIRED)
    
    // Direct Grafana access (fallback for development/debugging only)
    // DO NOT use for iframe embedding - will fail with X-Frame-Options DENY
    GRAFANA_DIRECT_URL: "http://127.0.0.1:3000",
    
    // Default Dashboard Path (relative to GRAFANA_URL)
    // This path gets appended to GRAFANA_URL when building iframe src
    GRAFANA_DASHBOARD: "d/neurobridge-overview/neurobridge-11d-overview?orgId=1&from=now-6h&to=now&timezone=browser&refresh=30s&kiosk=tv",
    
    // Available Dashboards for Quick Navigation
    // All paths are relative to GRAFANA_URL (/grafana/)
    GRAFANA_DASHBOARDS: {
        overview: {
            name: "Overview",
            path: "d/neurobridge-overview/neurobridge-11d-overview?orgId=1&from=now-6h&to=now&timezone=browser&refresh=30s&kiosk=tv",
            icon: "📊",
            description: "Main NeuroBridge 11D Overview Dashboard"
        },
        adfi: {
            name: "ADFI Observability",
            path: "d/neurobridge-adfi/adfi-observability?orgId=1&refresh=30s&kiosk=tv",
            icon: "🔧",
            description: "ADFI Deterministic Physics Data Fabric Metrics"
        },
        aece: {
            name: "AECE Control",
            path: "d/neurobridge-aece/aece-autonomous-control?orgId=1&refresh=30s&kiosk=tv",
            icon: "⚡",
            description: "AECE Autonomous Energy Control Metrics"
        },
        external: {
            name: "External API",
            path: "d/neurobridge-external/external-api-metrics?orgId=1&refresh=30s&kiosk=tv",
            icon: "🌐",
            description: "External API / Investor Demo Metrics"
        },
        infrastructure: {
            name: "Infrastructure",
            path: "d/neurobridge-infra/infrastructure-metrics?orgId=1&from=now-6h&to=now&timezone=browser&refresh=30s&kiosk=tv",
            icon: "🏗️",
            description: "Infrastructure & System Metrics"
        },
        latency: {
            name: "Latency Metrics",
            path: "d/neurobridge-latency/latency-metrics?orgId=1&refresh=30s&kiosk=tv",
            icon: "📈",
            description: "p95/p99 Latency Performance Metrics"
        },
        energy: {
            name: "Energy Metrics",
            path: "d/neurobridge-energy/energy-metrics?orgId=1&refresh=30s&kiosk=tv",
            icon: "🔋",
            description: "Grid Stability & Solar Efficiency Metrics"
        }
    },

    // ==========================================================================
    // APPLICATION METADATA
    // ==========================================================================
    
    APP_NAME: "NeuroBridge 11D",
    APP_VERSION: "14.8.1",
    COMPANY: "NeuroBridge Technologies Ltd",
    PHASE: "PHASE_1_PRODUCTION",
    MODE: "production",

    // ==========================================================================
    // FEATURE FLAGS
    // ==========================================================================
    
    FEATURES: {
        demo: true,
        cognitive: true,
        external_api: true,
        benchmarks: true,
        connectors: true,
        grafana_embed: true  // CRITICAL: Must be true for iframe rendering
    },

    // ==========================================================================
    // API ENDPOINTS (UNCHANGED)
    // ==========================================================================
    
    ENDPOINTS: {
        // Core
        HEALTH: "/api/v1/health",
        CONNECTORS_STATUS: "/api/v1/connectors/status",
        
        // Authentication
        AUTH_VALIDATE: "/api/v1/auth/validate",
        EXTERNAL_VALIDATE: "/api/v1/external/validate",
        EXTERNAL_ONBOARD: "/api/v1/external/onboard",
        
        // Cognitive
        COGNITIVE_QUERY: "/api/v1/cognitive/query",
        COGNITIVE_EXPLAIN: "/api/v1/cognitive/explain",
        
        // Demo
        DEMO_STATUS: "/api/v1/demo/status",
        DEMO_SHOWCASE: "/api/v1/demo/showcase",
        DEMO_START: "/api/v1/demo/start",
        DEMO_STOP: "/api/v1/demo/stop",
        DEMO_REPORT: "/api/v1/demo/report",
        DEMO_SCENARIOS: "/api/v1/demo/scenarios",
        
        // Benchmark
        BENCHMARK_HEALTH: "/api/v1/benchmarks/health",
        BENCHMARK_REPORTS: "/api/v1/benchmarks/reports",
        
        // External
        EXTERNAL_HEALTH: "/api/v1/external/health",
        EXTERNAL_ME: "/api/v1/external/me",
        EXTERNAL_LATENCY: "/api/v1/external/latency",
        EXTERNAL_PRODUCTS: "/api/v1/external/products",
        
        // Energy
        ENERGY_STATUS: "/api/v1/energy/status",
        ENERGY_METRICS: "/api/v1/energy/metrics",
        GRID_STABILITY: "/api/v1/energy/grid-stability",
        SOLAR_EFFICIENCY: "/api/v1/energy/solar-efficiency",
        
        // AECE
        AECE_STATUS: "/api/v1/aece/status",
        AECE_PROTECTION_STATUS: "/api/v1/aece/protection-mode/status",
        
        // Infrastructure
        SYSTEM_METRICS: "/api/v1/system/metrics"
    },

    // ==========================================================================
    // AUTHENTICATION HELPERS (UNCHANGED)
    // ==========================================================================
    
    AUTH_HEADERS: function (apiKey) {
        const key = apiKey || this.API_KEY || "";
        if (!key.trim()) return {};

        return {
            "Authorization": `Bearer ${key}`,
            "X-API-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        };
    },

    // ==========================================================================
    // STORAGE HELPERS
    // ==========================================================================
    
    save: function ({ apiBaseUrl, apiKey, grafanaUrl, grafanaDashboard }) {
        if (apiBaseUrl) {
            localStorage.setItem("NB_API_BASE_URL", apiBaseUrl);
            localStorage.setItem("apiBaseUrl", apiBaseUrl);
            this.API_BASE_URL = apiBaseUrl;
        }

        if (apiKey) {
            localStorage.setItem("NB_API_KEY", apiKey);
            localStorage.setItem("apiKey", apiKey);
            this.API_KEY = apiKey;
        }

        if (grafanaUrl) {
            localStorage.setItem("NB_GRAFANA_URL", grafanaUrl);
            localStorage.setItem("grafanaUrl", grafanaUrl);
            this.GRAFANA_URL = grafanaUrl;
        }
        
        if (grafanaDashboard) {
            localStorage.setItem("NB_GRAFANA_DASHBOARD", grafanaDashboard);
            this.GRAFANA_DASHBOARD = grafanaDashboard;
        }
    },
    
    // ==========================================================================
    // GET FULL GRAFANA URL WITH DASHBOARD (FIXED)
    // ==========================================================================
    // Builds the complete iframe src URL:
    //   GRAFANA_URL + dashboard_path
    // Example: /grafana/ + d/overview/... = /grafana/d/overview/...
    // ==========================================================================
    
    getGrafanaUrl: function (dashboardPath) {
        // Ensure GRAFANA_URL ends with /
        let baseUrl = this.GRAFANA_URL;
        if (!baseUrl.endsWith("/")) {
            baseUrl += "/";
        }
        
        // Remove leading / from dashboard path if present
        let path = dashboardPath || this.GRAFANA_DASHBOARD;
        if (path.startsWith("/")) {
            path = path.substring(1);
        }
        
        // Build full URL: /grafana/d/dashboard-uid/name?params
        return baseUrl + path;
    },
    
    // ==========================================================================
    // GET FULL IFRAME URL (with kiosk mode for embedding)
    // ==========================================================================
    
    getGrafanaIframeUrl: function (dashboardKey) {
        const dashboard = this.getDashboard(dashboardKey);
        return this.getGrafanaUrl(dashboard.path);
    },
    
    // ==========================================================================
    // GET DASHBOARD BY KEY
    // ==========================================================================
    
    getDashboard: function (key) {
        return this.GRAFANA_DASHBOARDS[key] || this.GRAFANA_DASHBOARDS.overview;
    },
    
    // ==========================================================================
    // LIST ALL AVAILABLE DASHBOARDS
    // ==========================================================================
    
    listDashboards: function () {
        return Object.entries(this.GRAFANA_DASHBOARDS).map(([key, value]) => ({
            key: key,
            name: value.name,
            icon: value.icon,
            description: value.description,
            path: value.path,
            fullUrl: this.getGrafanaIframeUrl(key)
        }));
    },

    // ==========================================================================
    // GRAFANA HEALTH CHECK (for auto-detection)
    // ==========================================================================
    
    checkGrafanaHealth: async function () {
        try {
            const response = await fetch("/grafana/api/health");
            if (response.ok) {
                const data = await response.json();
                console.log(`[CONFIG] Grafana health: ${data.database} v${data.version}`);
                return true;
            }
            return false;
        } catch (error) {
            console.warn("[CONFIG] Grafana health check failed:", error.message);
            return false;
        }
    },

    // ==========================================================================
    // INITIALIZATION LOG
    // ==========================================================================
    
    _initialized: false,
    
    init: function () {
        if (this._initialized) return;
        
        console.log(`[CONFIG] ${this.APP_NAME} v${this.APP_VERSION} initialized`);
        console.log(`[CONFIG] Phase: ${this.PHASE}`);
        console.log(`[CONFIG] API Base URL: ${this.API_BASE_URL}`);
        console.log(`[CONFIG] Grafana Proxy URL: ${this.GRAFANA_URL}`);
        console.log(`[CONFIG] Grafana Dashboard: ${this.GRAFANA_DASHBOARD}`);
        console.log(`[CONFIG] Grafana Embed: ${this.FEATURES.grafana_embed ? "ENABLED" : "DISABLED"}`);
        console.log(`[CONFIG] API Key present: ${!!this.API_KEY}`);
        
        // Auto-check Grafana health on init
        if (this.FEATURES.grafana_embed) {
            this.checkGrafanaHealth();
        }
        
        this._initialized = true;
    }
};

// Auto-initialize on load
if (typeof window !== 'undefined') {
    window.NEUROBRIDGE_CONFIG.init();
}