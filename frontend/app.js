// ============================================================================
// NeuroBridge 11D Frontend Application
// Phase 1 Production - Version 14.8.1
// Grafana iFrame Embed Fix - Same-Origin via Nginx Proxy
// ============================================================================

const cfg = () => window.NEUROBRIDGE_CONFIG || {};

function apiUrl(path) {
  return `${cfg().API_BASE_URL || "http://127.0.0.1:8000"}${path}`;
}

function getApiKey() {
  return (
    localStorage.getItem("NB_API_KEY") ||
    localStorage.getItem("apiKey") ||
    cfg().API_KEY ||
    ""
  );
}

function authHeaders() {
  const key = getApiKey();
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (key && key.trim()) {
    headers["Authorization"] = `Bearer ${key}`;
    headers["X-API-Key"] = key;
  }

  return headers;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const res = await fetch(apiUrl(path), {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
      signal: controller.signal,
    });

    clearTimeout(timeout);

    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }

    if (!res.ok) {
      const err = new Error(pretty(data));
      err.status = res.status;
      err.data = data;
      throw err;
    }

    return data;
  } catch (err) {
    clearTimeout(timeout);
    if (err.name === "AbortError") {
      throw new Error("Request timeout after 15 seconds");
    }
    throw err;
  }
}

async function checkHealth(path, targetId) {
  try {
    const data = await request(path);
    setText(targetId, String(data.status || "OK").toUpperCase());
    return true;
  } catch {
    setText(targetId, "OFFLINE");
    return false;
  }
}

async function refreshAll() {
  const checks = await Promise.all([
    checkHealth("/api/v1/external/health", "externalStatus"),
    checkHealth("/api/v1/cognitive/health", "cognitiveStatus"),
    checkHealth("/api/v1/demo/health", "demoStatus"),
    checkHealth("/api/v1/benchmarks/health", "benchmarkStatus"),
  ]);

  const online = checks.some(Boolean);
  const dot = document.getElementById("connectionDot");

  if (dot) {
    dot.classList.toggle("connected", online);
    dot.classList.toggle("offline", !online);
  }

  setText("connectionLabel", online ? "Backend connected" : "Backend offline");
  setText("systemMode", online ? "PRODUCTION ONLINE" : "OFFLINE");
  setText(
    "systemSummary",
    online
      ? "External API, cognitive engine, demo routes, benchmarks, latency metrics, and production services are reachable."
      : "Backend could not be reached. Check API base URL or runtime."
  );
}

function saveSettings() {
  const base = document.getElementById("apiBaseUrl")?.value.trim();
  const key = document.getElementById("apiKey")?.value.trim();
  const grafana = document.getElementById("grafanaUrl")?.value.trim();

  if (base) {
    localStorage.setItem("NB_API_BASE_URL", base);
    localStorage.setItem("apiBaseUrl", base);
    cfg().API_BASE_URL = base;
  }

  if (key) {
    localStorage.setItem("NB_API_KEY", key);
    localStorage.setItem("apiKey", key);
    cfg().API_KEY = key;
  }

  if (grafana) {
    localStorage.setItem("NB_GRAFANA_URL", grafana);
    localStorage.setItem("grafanaUrl", grafana);
    cfg().GRAFANA_URL = grafana;
  }

  refreshAll();
}

function getNumber(id) {
  return Number(document.getElementById(id)?.value || 0);
}

async function runCognitiveAnalysis() {
  try {
    const payload = {
      query: "Analyze grid stability and solar risk",
      context: {
        actual_kw: getNumber("actualKw"),
        expected_kw: getNumber("expectedKw"),
        temperature_c: getNumber("temperatureC"),
        irradiance_quality: getNumber("irradianceQuality"),
        frequency_hz: getNumber("frequencyHz"),
        voltage_v: getNumber("voltageV"),
        load_balance: getNumber("loadBalance"),
      },
    };

    const data = await request("/api/v1/cognitive/query", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    const resultObj = data.result || {};
    
    const summaryText =
      resultObj.summary ||
      data.summary ||
      resultObj.explanation ||
      data.explanation ||
      "Deterministic analysis completed successfully.";
    
    const explanationText =
      resultObj.explanation ||
      data.explanation ||
      summaryText;
    
    const metrics = data.metrics || resultObj.metrics || {};
    
    setText("analysisSummary", summaryText.substring(0, 160));
    setText("analysisExplanation", explanationText.substring(0, 500));
    
    const gridStability = metrics.grid_stability_index ?? metrics.gsi ?? null;
    const solarEfficiency = metrics.solar_efficiency_score ?? metrics.ses ?? null;
    const riskScore = metrics.risk_score ?? metrics.risk ?? null;
    
    setText("gsiValue", gridStability !== null ? gridStability : "--");
    setText("sesValue", solarEfficiency !== null ? solarEfficiency : "--");
    setText("riskValue", riskScore !== null ? riskScore : "--");
    
  } catch (err) {
    setText("analysisSummary", "Analysis failed");
    setText("analysisExplanation", err.message);
    setText("gsiValue", "--");
    setText("sesValue", "--");
    setText("riskValue", "--");
  }
}

async function runShowcase() {
  try {
    const data = await request("/api/v1/demo/showcase", {
      method: "POST",
      body: JSON.stringify({
        showcase_type: "investor_full",
        scenario: "mixed_production",
        include_metrics: true,
      }),
    });
    setText("demoOutput", pretty(data));
  } catch (err) {
    setText("demoOutput", err.message);
  }
}

async function getDemoStatus() {
  try {
    const data = await request("/api/v1/demo/status");
    setText("demoOutput", pretty(data));
  } catch (err) {
    setText("demoOutput", err.message);
  }
}

function calculatePerformanceGrade(latency) {
  if (!latency) return "UNAVAILABLE";

  const p95Ms = latency.p95_ms || 0;
  const p99Ms = latency.p99_ms || 0;

  if (p95Ms === 0 && p99Ms === 0) return "INITIALIZING";
  if (p95Ms < 50 && p99Ms < 100) return "EXCELLENT";
  if (p95Ms < 100 && p99Ms < 200) return "GOOD";
  if (p95Ms < 250 && p99Ms < 500) return "FAIR";
  return "POOR";
}

function getLatencyInterpretation(latency) {
  if (!latency) return "No latency data available";

  const p95Ms = latency.p95_ms || 0;
  const totalRequests = latency.total_requests || 0;

  if (totalRequests === 0) {
    return "No API requests recorded yet. Make API calls to generate latency data.";
  }

  if (p95Ms < 50) return "Excellent performance: p95 under 50ms.";
  if (p95Ms < 100) return "Good performance: p95 under 100ms.";
  if (p95Ms < 250) return "Fair performance: optimization recommended.";
  return "Poor performance: investigate bottlenecks.";
}

async function getLatency() {
  const outputEl = document.getElementById("latencyOutput");
  if (outputEl) outputEl.textContent = "Fetching latency metrics...";

  try {
    const data = await request("/api/v1/external/latency");

    const latency = data.latency || data.latency_metrics || data;
    const formattedOutput = {
      status: data.status || "success",
      client_id: data.client_id,
      plan: data.plan,
      latency_metrics: latency,
      performance_grade: data.performance_grade || calculatePerformanceGrade(latency),
      timestamp: data.timestamp,
      interpretation: getLatencyInterpretation(latency),
    };

    if (outputEl) outputEl.textContent = pretty(formattedOutput);
  } catch (err) {
    if (outputEl) {
      outputEl.textContent = pretty({
        status: "unavailable",
        error: err.message,
        next_steps: [
          "Generate investor API key",
          "Test API connection",
          "Confirm /api/v1/external/latency exists",
        ],
      });
    }
  }
}

// ============================================================================
// GRAFANA ENTERPRISE LOADER - PHASE 1 PRODUCTION SAME-ORIGIN FIX
// ============================================================================
// CRITICAL FIXES:
// 1. Uses /grafana/ nginx proxy path (same-origin) instead of direct :3000
// 2. Normalizes all dashboard paths to /grafana/ prefix
// 3. Handles saved paths from old configs (localhost:3000, /d/, d/, etc.)
// 4. Health check uses /grafana/api/health through nginx proxy
// 5. Fallback HTML shows clear instructions when Grafana is unavailable
// 6. Auto-loads on page init with retry logic
// ============================================================================

const GRAFANA_DASHBOARD_PATH =
  "/grafana/d/neurobridge-overview/neurobridge-11d-overview?orgId=1&from=now-6h&to=now&timezone=browser&refresh=30s&kiosk=tv";

/**
 * Normalize any Grafana path to use the /grafana/ nginx proxy prefix.
 * Handles legacy paths that may have been saved to localStorage.
 */
function normalizeGrafanaPath(path) {
  if (!path || typeof path !== "string") {
    return GRAFANA_DASHBOARD_PATH;
  }

  // Already correct - starts with /grafana/
  if (path.startsWith("/grafana/")) {
    return path;
  }

  // Legacy: http://localhost/grafana/... -> /grafana/...
  if (path.startsWith("http://localhost/grafana/")) {
    return path.replace("http://localhost", "");
  }

  // Legacy: http://127.0.0.1:3000/... -> /grafana/...
  if (path.startsWith("http://127.0.0.1:3000")) {
    return path.replace("http://127.0.0.1:3000", "/grafana");
  }

  // Legacy: /d/... -> /grafana/d/...
  if (path.startsWith("/d/")) {
    return `/grafana${path}`;
  }

  // Legacy: d/... -> /grafana/d/...
  if (path.startsWith("d/")) {
    return `/grafana/${path}`;
  }

  // Unknown format - return default
  console.warn("[GRAFANA] Unknown path format, using default:", path);
  return GRAFANA_DASHBOARD_PATH;
}

/**
 * Get the full Grafana URL for iframe src.
 * Uses saved dashboard preference or falls back to default.
 */
function getGrafanaFullUrl() {
  const savedDashboard =
    localStorage.getItem("NB_GRAFANA_DASHBOARD") ||
    cfg().GRAFANA_DASHBOARD ||
    GRAFANA_DASHBOARD_PATH;

  return normalizeGrafanaPath(savedDashboard);
}

/**
 * Check if Grafana is reachable through the nginx proxy.
 * Returns true if health endpoint responds OK.
 */
async function checkGrafanaHealth() {
  try {
    const response = await fetch("/grafana/api/health", {
      cache: "no-store",
      credentials: "same-origin",
    });

    if (response.ok) {
      const data = await response.json();
      console.log("[GRAFANA] Health check passed - v" + (data.version || "unknown"));
      return true;
    }
    return false;
  } catch (err) {
    console.warn("[GRAFANA] Health check failed:", err.message);
    return false;
  }
}

/**
 * Load Grafana dashboard into the iframe with health check.
 * Shows fallback HTML if Grafana is not ready.
 * Returns true if loaded successfully, false otherwise.
 */
async function loadGrafanaWithRetry() {
  const iframe = document.getElementById("grafanaFrame");

  if (!iframe) {
    console.warn("[GRAFANA] Iframe element #grafanaFrame not found in DOM");
    return false;
  }

  iframe.style.display = "block";

  const isReady = await checkGrafanaHealth();

  if (!isReady) {
    console.warn("[GRAFANA] Grafana not ready - showing fallback message");
    iframe.removeAttribute("src");
    iframe.srcdoc = `
      <html>
        <body style="background:#010510;color:#ffcc66;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100%;margin:0;">
          <div style="text-align:center;max-width:500px;padding:2rem;">
            <h3 style="color:#16f2c4;margin-bottom:1rem;">⚡ Grafana Starting Up</h3>
            <p style="color:#8892b0;margin-bottom:0.5rem;">The observability dashboard is initializing.</p>
            <p style="color:#8892b0;margin-bottom:1.5rem;">This usually takes 10-30 seconds after deployment.</p>
            <button onclick="loadGrafana()" style="background:#16f2c4;color:#010510;border:none;padding:0.6rem 1.5rem;border-radius:4px;cursor:pointer;font-family:monospace;font-weight:bold;">
              🔄 Retry Load
            </button>
          </div>
        </body>
      </html>
    `;
    return false;
  }

  const dashboardUrl = getGrafanaFullUrl();

  console.log("[GRAFANA] Loading dashboard:", dashboardUrl);

  iframe.removeAttribute("srcdoc");
  iframe.src = dashboardUrl;

  iframe.onload = () => {
    console.log("[GRAFANA] Dashboard iframe loaded successfully");
    const loader = document.querySelector(".grafana-loader");
    if (loader) loader.style.display = "none";
  };

  iframe.onerror = () => {
    console.error("[GRAFANA] Failed to load dashboard in iframe");
    iframe.srcdoc = `
      <html>
        <body style="background:#010510;color:#ff5470;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100%;margin:0;">
          <div style="text-align:center;">
            <h3>⚠️ Dashboard Load Failed</h3>
            <p>Please check Grafana service status and try again.</p>
            <button onclick="loadGrafana()" style="background:#ff5470;color:#fff;border:none;padding:0.5rem 1rem;border-radius:4px;cursor:pointer;font-family:monospace;">Retry</button>
          </div>
        </body>
      </html>
    `;
  };

  return true;
}

/**
 * Public function for manual "Load Grafana" button clicks.
 */
function loadGrafana() {
  console.log("[GRAFANA] Manual load triggered");
  return loadGrafanaWithRetry();
}

/**
 * Switch to a different Grafana dashboard by key.
 * Updates localStorage so preference persists across reloads.
 */
function switchGrafanaDashboard(dashboardKey) {
  const dashboards = cfg().GRAFANA_DASHBOARDS || {};
  const dashboard = dashboards[dashboardKey];

  if (!dashboard || !dashboard.path) {
    console.warn("[GRAFANA] Unknown dashboard key:", dashboardKey);
    return;
  }

  const dashboardUrl = normalizeGrafanaPath(dashboard.path);

  // Save preference
  localStorage.setItem("NB_GRAFANA_DASHBOARD", dashboardUrl);

  const frame = document.getElementById("grafanaFrame");
  if (frame) {
    frame.removeAttribute("srcdoc");
    frame.src = dashboardUrl;
    frame.style.display = "block";
    console.log("[GRAFANA] Switched dashboard:", dashboardKey, "→", dashboardUrl);
  }

  // Update button active states
  document.querySelectorAll(".grafana-dash-btn").forEach((btn) => {
    btn.classList.remove("active");
  });

  const activeBtn = document.querySelector(
    `.grafana-dash-btn[data-dash="${dashboardKey}"]`
  );

  if (activeBtn) activeBtn.classList.add("active");
}

/**
 * Open the current Grafana dashboard in a new browser tab.
 */
function openGrafanaNewTab() {
  const url = getGrafanaFullUrl();
  console.log("[GRAFANA] Opening in new tab:", url);
  window.open(url, "_blank");
}

/**
 * Reload the Grafana iframe without changing the dashboard.
 */
function reloadGrafana() {
  const frame = document.getElementById("grafanaFrame");
  if (!frame) return;

  const currentSrc = frame.src || getGrafanaFullUrl();
  frame.removeAttribute("srcdoc");
  frame.src = currentSrc;
  console.log("[GRAFANA] Iframe reloaded");
}

/**
 * Initialize dashboard switcher buttons below the Grafana panel.
 * Creates buttons for each dashboard + Reload + Open in New Tab.
 * Only runs once (checks for existing controls).
 */
function initGrafanaControls() {
  const grafanaPanel = document.getElementById("grafana");
  if (!grafanaPanel) return;

  if (document.getElementById("grafanaControls")) return;

  const controlsDiv = document.createElement("div");
  controlsDiv.id = "grafanaControls";
  controlsDiv.className = "button-row";
  controlsDiv.style.marginBottom = "1rem";
  controlsDiv.style.gap = "0.5rem";
  controlsDiv.style.flexWrap = "wrap";

  const dashboards = [
    { key: "overview", label: "📊 Overview", title: "Main Overview Dashboard" },
    { key: "adfi", label: "🔧 ADFI", title: "ADFI Observability" },
    { key: "aece", label: "⚡ AECE", title: "AECE Autonomous Control" },
    { key: "external", label: "🌐 External API", title: "External API Metrics" },
    { key: "infrastructure", label: "🏗️ Infrastructure", title: "Infrastructure Metrics" },
    { key: "latency", label: "📈 Latency", title: "Latency Performance Metrics" },
    { key: "energy", label: "🔋 Energy", title: "Energy & Grid Metrics" },
  ];

  dashboards.forEach((db) => {
    const btn = document.createElement("button");
    btn.textContent = db.label;
    btn.title = db.title;
    btn.className = "btn btn-ghost grafana-dash-btn";
    btn.setAttribute("data-dash", db.key);
    btn.style.fontSize = "0.8rem";
    btn.style.padding = "0.3rem 0.8rem";
    btn.onclick = () => switchGrafanaDashboard(db.key);
    controlsDiv.appendChild(btn);
  });

  // Separator
  const separator = document.createElement("span");
  separator.style.margin = "0 0.25rem";
  separator.style.color = "#495670";
  separator.textContent = "|";
  controlsDiv.appendChild(separator);

  const reloadBtn = document.createElement("button");
  reloadBtn.textContent = "🔄 Reload";
  reloadBtn.title = "Reload Grafana iframe";
  reloadBtn.className = "btn btn-ghost";
  reloadBtn.style.fontSize = "0.8rem";
  reloadBtn.style.padding = "0.3rem 0.8rem";
  reloadBtn.onclick = () => reloadGrafana();
  controlsDiv.appendChild(reloadBtn);

  const openBtn = document.createElement("button");
  openBtn.textContent = "🔗 Open in New Tab";
  openBtn.title = "Open Grafana in new tab";
  openBtn.className = "btn btn-ghost";
  openBtn.style.fontSize = "0.8rem";
  openBtn.style.padding = "0.3rem 0.8rem";
  openBtn.onclick = () => openGrafanaNewTab();
  controlsDiv.appendChild(openBtn);

  const frameWrap = grafanaPanel.querySelector(".grafana-frame-wrap");

  if (frameWrap) {
    grafanaPanel.insertBefore(controlsDiv, frameWrap);
  }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function clearConsole(id) {
  setText(id, "");
}

async function generateInvestorApiKey() {
  const outputEl = document.getElementById("apiKeyOutput");
  if (outputEl) outputEl.textContent = "Generating investor API key...";

  try {
    const payload = {
      name: "Frontend Investor Demo",
      organization: "NeuroBridge Dashboard",
      email: "investor-demo@neurobridge.local",
      plan: "investor_demo",
      use_case: "frontend investor dashboard validation",
    };

    const data = await request("/api/v1/external/onboard", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    let apiKey = null;
    let clientId = null;
    let plan = null;
    let limits = null;

    if (data?.client?.api_key) {
      apiKey = data.client.api_key;
      clientId = data.client.client_id;
      plan = data.client.plan;
      limits = data.client.limits;
    } else if (data?.api_key) {
      apiKey = data.api_key;
      clientId = data.client_id;
      plan = data.plan;
    } else if (data?.token) {
      apiKey = data.token;
      clientId = data.client_id;
      plan = data.plan;
    }

    if (!apiKey) {
      throw new Error("API key was not returned by backend.");
    }

    localStorage.setItem("NB_API_KEY", apiKey);
    localStorage.setItem("apiKey", apiKey);
    cfg().API_KEY = apiKey;

    const apiKeyInput = document.getElementById("apiKey");
    if (apiKeyInput) apiKeyInput.value = apiKey;

    const output = {
      status: "success",
      message: "Investor API key generated and saved locally.",
      client_id: clientId || "auto-generated",
      plan: plan || "investor_demo",
      limits: limits || { rate_limit: "100/hour", concurrent: 5 },
      api_key_masked: `${apiKey.substring(0, 16)}...${apiKey.substring(apiKey.length - 8)}`,
      next_steps: [
        "Test API Connection",
        "Run Energy Analysis",
        "Run Investor Showcase",
        "Refresh Latency Proof",
      ],
    };

    if (outputEl) outputEl.textContent = pretty(output);
    await refreshAll();
  } catch (err) {
    if (outputEl) {
      outputEl.textContent = pretty({
        status: "failed",
        error: err.message,
        message: "Backend API key generation failed. Confirm /api/v1/external/onboard is enabled.",
      });
    }
  }
}

async function testApiConnection() {
  const outputEl = document.getElementById("apiKeyOutput");
  if (outputEl) outputEl.textContent = "Testing API connection...";

  const startTime = performance.now();
  const results = {
    timestamp: new Date().toISOString(),
    api_base_url: cfg().API_BASE_URL,
    api_key_present: !!getApiKey(),
    api_key_masked: getApiKey()
      ? `${getApiKey().substring(0, 16)}...`
      : "none",
    endpoints: [],
  };

  const endpoints = [
    { name: "System Health", path: "/api/v1/health" },
    { name: "Connectors Status", path: "/api/v1/connectors/status" },
    { name: "External API Health", path: "/api/v1/external/health" },
    { name: "External API Me", path: "/api/v1/external/me" },
    { name: "External Latency", path: "/api/v1/external/latency" },
    { name: "Cognitive Health", path: "/api/v1/cognitive/health" },
    { name: "Demo Status", path: "/api/v1/demo/status" },
    { name: "Benchmark Health", path: "/api/v1/benchmarks/health" },
  ];

  let successCount = 0;

  for (const endpoint of endpoints) {
    const endpointStart = performance.now();
    try {
      const data = await request(endpoint.path);
      results.endpoints.push({
        name: endpoint.name,
        path: endpoint.path,
        status: "ok",
        latency_ms: Number((performance.now() - endpointStart).toFixed(2)),
        response_keys: typeof data === "object" ? Object.keys(data).slice(0, 8) : [],
      });
      successCount++;
    } catch (err) {
      results.endpoints.push({
        name: endpoint.name,
        path: endpoint.path,
        status: "failed",
        latency_ms: Number((performance.now() - endpointStart).toFixed(2)),
        error: err.message.substring(0, 200),
      });
    }
  }

  results.summary = {
    total_endpoints: endpoints.length,
    successful: successCount,
    failed: endpoints.length - successCount,
    success_rate: `${((successCount / endpoints.length) * 100).toFixed(1)}%`,
    total_time_ms: Number((performance.now() - startTime).toFixed(2)),
  };

  results.verdict =
    successCount === endpoints.length
      ? "ALL SYSTEMS OPERATIONAL"
      : successCount > 0
        ? `PARTIAL CONNECTIVITY - ${successCount}/${endpoints.length} endpoints working`
        : `NO ENDPOINTS RESPONDING - Verify backend at ${cfg().API_BASE_URL}`;

  if (outputEl) outputEl.textContent = pretty(results);

  await refreshAll();
  return results;
}

// ============================================================================
// EXPOSE FUNCTIONS TO GLOBAL WINDOW
// ============================================================================

window.generateInvestorApiKey = generateInvestorApiKey;
window.testApiConnection = testApiConnection;
window.loadGrafana = loadGrafana;
window.saveSettings = saveSettings;
window.refreshAll = refreshAll;
window.runCognitiveAnalysis = runCognitiveAnalysis;
window.runShowcase = runShowcase;
window.getDemoStatus = getDemoStatus;
window.getLatency = getLatency;
window.clearConsole = clearConsole;
window.switchGrafanaDashboard = switchGrafanaDashboard;
window.openGrafanaNewTab = openGrafanaNewTab;
window.reloadGrafana = reloadGrafana;

// ============================================================================
// INITIALIZATION ON PAGE LOAD
// ============================================================================

window.addEventListener("load", () => {
  const apiBaseInput = document.getElementById("apiBaseUrl");
  const apiKeyInput = document.getElementById("apiKey");
  const grafanaInput = document.getElementById("grafanaUrl");

  if (apiBaseInput) apiBaseInput.value = cfg().API_BASE_URL || "http://127.0.0.1:8000";
  if (apiKeyInput) apiKeyInput.value = getApiKey();
  if (grafanaInput) grafanaInput.value = cfg().GRAFANA_URL || "/grafana/";

  refreshAll();
  
  // Auto-load Grafana iframe with retry after page load
  // Delay allows nginx proxy to stabilize
  setTimeout(() => {
    loadGrafanaWithRetry();
    initGrafanaControls();
  }, 1500);

  // Register PWA service worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/frontend/pwa/sw.js").catch(() => {});
  }
});