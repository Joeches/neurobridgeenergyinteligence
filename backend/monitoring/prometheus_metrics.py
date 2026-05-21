"""
NeuroBridge 11D - Prometheus Metrics Integration (Phase 1 Production)
Complete Production Metrics Collection for Monitoring and Alerting

Includes:
- ADFI Observability Metrics
- AECE Autonomous Control Metrics
- External API Metrics
- NeuroBridge 11D Overview Metrics
- All existing Phase 1 metrics (energy, weather, system, etc.)

Version: 14.8.1 | Production Ready | Path Sanitizer Fixed
"""

import os
import sys
import time
import logging
import tempfile
import platform
import re
import threading
from typing import Dict, Any, Optional, Callable, List, Tuple
from functools import wraps
from datetime import datetime, timezone
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ============================================================================
# THREAD SAFETY FOR METRIC REGISTRATION
# ============================================================================

_metric_registration_lock = threading.RLock()
_registered_metrics_cache = set()

# ============================================================================
# PATH SANITIZATION - SAFE HEX ID PATTERNS
# ============================================================================

# Only matches hex strings 12+ characters long, with word boundaries
# This prevents matching short words like 'api', 'auth', 'v1', 'health', etc.
_HEX_ID_RE = re.compile(r"\b[0-9a-fA-F]{12,64}\b")

# Standard UUID pattern (8-4-4-4-12 with hyphens)
_UUID_RE = re.compile(
    r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
)

# Pure numeric path segments (for integer IDs)
_NUMERIC_ID_RE = re.compile(r'/\d+')


def sanitize_endpoint(path: str) -> str:
    """
    Sanitize endpoint path for Prometheus labels.
    
    Only replaces:
    - UUIDs (standard 8-4-4-4-12 format with hyphens)
    - Long hex IDs (12+ consecutive hex chars with word boundaries)
    - Pure numeric path segments
    
    Does NOT match short words like 'api', 'auth', 'v1', 'health', etc.
    
    Examples:
        /api/v1/health                    -> /api/v1/health (unchanged)
        /api/v1/auth/validate             -> /api/v1/auth/validate (unchanged)
        /api/v1/external/clients/abc123def456 -> /api/v1/external/clients/{hex}
        /api/v1/users/42                  -> /api/v1/users/{id}
    """
    if not path:
        return "unknown"
    
    # Replace UUIDs first (standard 8-4-4-4-12 format with hyphens)
    path = _UUID_RE.sub('{uuid}', path)
    
    # Replace long hex IDs (12+ consecutive hex chars with word boundaries)
    # The word boundary \b ensures we don't match inside words like 'api', 'auth'
    path = _HEX_ID_RE.sub('{hex}', path)
    
    # Replace pure numeric path segments
    path = _NUMERIC_ID_RE.sub('/{id}', path)
    
    return path


# ============================================================================
# PHASE 1 METRIC FILTER CONFIGURATION
# ============================================================================

PHASE1_ALLOWED_METRIC_PREFIXES = [
    'neurobridge_energy_',
    'neurobridge_weather_',
    'neurobridge_aece_',
    'neurobridge_system_',
    'neurobridge_process_',
    'neurobridge_celery_',
    'neurobridge_api_',
    'neurobridge_database_',
    'neurobridge_redis_',
    'neurobridge_websocket_',
    'neurobridge_inverter_',
    'neurobridge_battery_',
    'neurobridge_gc_',
    'neurobridge_partner_',
    'neurobridge_user_',
    'neurobridge_rate_limit_',
    'neurobridge_app_',
    # Phase 1 Production Observability
    'neurobridge_adfi_',
    'neurobridge_grid_',
    'neurobridge_solar_',
    'neurobridge_investor_',
    'neurobridge_auth_',
    'neurobridge_onboarding_',
    'neurobridge_active_',
    'neurobridge_hardware_',
    'neurobridge_prediction_',
    'neurobridge_phase1_',
    'neurobridge_emergency_',
    'neurobridge_ingestion_',
    'neurobridge_pipeline_',
    'neurobridge_deterministic_',
    'neurobridge_telemetry_',
    'neurobridge_source_',
    'neurobridge_control_',
    'neurobridge_queue_',
]

PHASE1_BLOCKED_METRIC_PREFIXES = [
    'neurobridge_nuclear_',
    'neurobridge_fusion_',
    'neurobridge_quantum_',
    'neurobridge_defense_',
    'nuclear_',
    'fusion_',
    'quantum_',
    'defense_',
]

_phase1_blocked_metrics_log: List[Dict[str, Any]] = []


def is_phase1_allowed_metric(metric_name: str) -> bool:
    """Check if metric is allowed in Phase 1 Production."""
    if not metric_name:
        return True
    metric_lower = metric_name.lower()
    for blocked_prefix in PHASE1_BLOCKED_METRIC_PREFIXES:
        if metric_lower.startswith(blocked_prefix.lower()):
            return False
    for allowed_prefix in PHASE1_ALLOWED_METRIC_PREFIXES:
        if metric_lower.startswith(allowed_prefix.lower()):
            return True
    return True


def log_blocked_metric(metric_name: str, reason: str = "phase1_blocked"):
    _phase1_blocked_metrics_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metric_name": metric_name,
        "reason": reason,
        "phase": "PHASE_1_BLOCKED"
    })
    if len(_phase1_blocked_metrics_log) > 1000:
        _phase1_blocked_metrics_log.pop(0)


def get_phase1_metric_stats() -> Dict[str, Any]:
    return {
        "total_blocked": len(_phase1_blocked_metrics_log),
        "recent_blocked": _phase1_blocked_metrics_log[-10:] if _phase1_blocked_metrics_log else [],
        "phase": "PHASE_1_PRODUCTION"
    }

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

_is_celery_worker = os.environ.get("CELERY_WORKER", "false").lower() == "true"
_is_reload_mode = os.environ.get("UVICORN_RELOAD", "false").lower() == "true"
_is_windows = platform.system() == "Windows"
_is_multiprocess = os.environ.get("PROMETHEUS_MULTIPROC_DIR") is not None

if _is_celery_worker:
    logger.debug("[METRICS] Celery worker mode - metrics disabled")

# ============================================================================
# PROMETHEUS IMPORTS WITH GRACEFUL FALLBACK
# ============================================================================

PROMETHEUS_AVAILABLE = False
REGISTRY = None
generate_latest = None
CONTENT_TYPE_LATEST = None
Counter = None
Histogram = None
Gauge = None
Info = None
Summary = None
CollectorRegistry = None

if not _is_celery_worker:
    try:
        from prometheus_client import (
            Counter, Histogram, Gauge, Info, Summary,
            generate_latest, CONTENT_TYPE_LATEST,
            REGISTRY, CollectorRegistry
        )
        PROMETHEUS_AVAILABLE = True
        logger.info("[PROMETHEUS] client library loaded")
    except ImportError:
        logger.debug("[PROMETHEUS] client library not available")
    except Exception as e:
        logger.debug(f"[PROMETHEUS] import error: {e}")

# ============================================================================
# METRIC REGISTRATION HELPER
# ============================================================================

def metric_exists_in_registry(metric_name: str, registry=None) -> bool:
    if registry is None:
        registry = REGISTRY
    if not PROMETHEUS_AVAILABLE or registry is None:
        return False
    try:
        if hasattr(registry, '_names_to_collectors'):
            return metric_name in registry._names_to_collectors
        elif hasattr(registry, '_collector_to_names'):
            for collector in registry._collector_to_names:
                if hasattr(collector, '_name') and collector._name == metric_name:
                    return True
                if hasattr(collector, 'name') and collector.name == metric_name:
                    return True
    except Exception:
        pass
    return False


def register_metric_safe(metric_class, name: str, documentation: str, 
                         labelnames: List[str] = None, registry=None,
                         **kwargs) -> Optional[Any]:
    if not PROMETHEUS_AVAILABLE:
        return NullMetric()
    
    if registry is None:
        registry = REGISTRY
    
    if not is_phase1_allowed_metric(name):
        log_blocked_metric(name, "phase1_blocked_prefix")
        return NullMetric()
    
    with _metric_registration_lock:
        if name in _registered_metrics_cache:
            return NullMetric()
        
        if metric_exists_in_registry(name, registry):
            _registered_metrics_cache.add(name)
            return NullMetric()
        
        try:
            if labelnames:
                metric = metric_class(name, documentation, labelnames, registry=registry, **kwargs)
            else:
                metric = metric_class(name, documentation, registry=registry, **kwargs)
            _registered_metrics_cache.add(name)
            return metric
        except ValueError as e:
            if "Duplicated" in str(e) or "already exists" in str(e):
                _registered_metrics_cache.add(name)
            return NullMetric()
        except Exception:
            return NullMetric()


def clear_metric_registration_cache():
    global _registered_metrics_cache
    with _metric_registration_lock:
        _registered_metrics_cache.clear()

# ============================================================================
# MULTI-PROCESS CONFIGURATION
# ============================================================================

_multiprocess_setup_done = False

def setup_multiprocess_metrics():
    global _multiprocess_setup_done
    if not PROMETHEUS_AVAILABLE:
        return False
    if _multiprocess_setup_done:
        return True
    try:
        if _is_windows:
            multiproc_dir = os.path.join(tempfile.gettempdir(), 'prometheus_multiproc')
        else:
            multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus_multiproc")
        os.makedirs(multiproc_dir, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = multiproc_dir
        if not _is_reload_mode:
            from prometheus_client import multiprocess
            if hasattr(REGISTRY, '_collector_to_names'):
                collectors = list(REGISTRY._collector_to_names.keys())
                for collector in collectors:
                    try:
                        REGISTRY.unregister(collector)
                    except:
                        pass
            multiprocess.MultiProcessCollector(REGISTRY)
            _multiprocess_setup_done = True
            logger.info("[METRICS] multiprocess=true")
        else:
            _multiprocess_setup_done = True
        return True
    except Exception as e:
        logger.debug(f"[METRICS] multiprocess setup skipped: {e}")
        return False


if PROMETHEUS_AVAILABLE and not _is_celery_worker and not _is_reload_mode:
    setup_multiprocess_metrics()

# ============================================================================
# NULL METRIC CLASS FOR FALLBACK
# ============================================================================

class NullMetric:
    def __init__(self, *args, **kwargs):
        pass
    def labels(self, *args, **kwargs):
        return self
    def inc(self, amount=1):
        pass
    def dec(self, amount=1):
        pass
    def set(self, value):
        pass
    def observe(self, value):
        pass
    def time(self):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def track_inprogress(self):
        return self


class NullHistogram(NullMetric):
    def observe(self, value):
        pass

# ============================================================================
# METRICS CLASS
# ============================================================================

class NeuroBridgeMetrics:
    _instance = None
    _initialized = False
    _registered_metrics = set()
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._available = PROMETHEUS_AVAILABLE and not _is_celery_worker
            
            logger.info("[METRICS] initialized")
            
            if not self._available:
                self._init_null_metrics()
            else:
                self._init_prometheus_metrics()
    
    def _is_metric_registered(self, name: str) -> bool:
        with self._lock:
            return name in self._registered_metrics
    
    def _register_metric(self, name: str):
        with self._lock:
            self._registered_metrics.add(name)
    
    def _validate_metric_phase1(self, name: str) -> bool:
        return is_phase1_allowed_metric(name)
    
    def _safe_create_metric(self, metric_class, name: str, documentation: str, **kwargs):
        return register_metric_safe(metric_class, name, documentation, **kwargs)
    
    def _init_null_metrics(self):
        """Initialize all metrics as NullMetric when Prometheus is unavailable."""
        self.api_requests_total = NullMetric()
        self.api_request_duration_seconds = NullMetric()
        self.api_requests_active = NullMetric()
        self.celery_tasks_total = NullMetric()
        self.celery_task_duration_seconds = NullMetric()
        self.celery_queue_size = NullMetric()
        self.celery_active_workers = NullMetric()
        self.celery_task_retries = NullMetric()
        self.energy_power_kw = NullMetric()
        self.energy_frequency_hz = NullMetric()
        self.energy_efficiency_percent = NullMetric()
        self.energy_daily_production_kwh = NullMetric()
        self.energy_co2_savings_kg = NullMetric()
        self.energy_voltage_v = NullMetric()
        self.energy_current_a = NullMetric()
        self.weather_solar_irradiance_wm2 = NullMetric()
        self.weather_temperature_celsius = NullMetric()
        self.weather_cloud_cover_percent = NullMetric()
        self.weather_wind_speed_ms = NullMetric()
        self.weather_humidity_percent = NullMetric()
        self.weather_pressure_hpa = NullMetric()
        self.kernel_native = NullMetric()
        self.redis_available = NullMetric()
        self.db_pool_size = NullMetric()
        self.websocket_connections = NullMetric()
        self.database_connections_active = NullMetric()
        self.database_query_duration_seconds = NullMetric()
        self.system_cpu_percent = NullMetric()
        self.system_memory_percent = NullMetric()
        self.system_disk_usage_percent = NullMetric()
        self.process_cpu_percent = NullMetric()
        self.process_memory_mb = NullMetric()
        self.process_threads = NullMetric()
        self.app_uptime_seconds = NullMetric()
        self.gc_collections_total = NullMetric()
        self.gc_collection_duration_seconds = NullMetric()
        self.partner_energy_usage_kwh = NullMetric()
        self.partner_system_uptime_percent = NullMetric()
        self.partner_request_count = NullMetric()
        self.active_sessions = NullMetric()
        self.api_key_usage_total = NullMetric()
        self.rate_limit_exceeded_total = NullMetric()
        self.user_login_total = NullMetric()
        self.user_login_failures_total = NullMetric()
        self.inverter_temperature_celsius = NullMetric()
        self.inverter_efficiency_percent = NullMetric()
        self.battery_soc_percent = NullMetric()
        self.battery_health_percent = NullMetric()
        self.aece_actions_total = NullMetric()
        self.aece_decision_latency_ms = NullMetric()
        self.aece_risk_score = NullMetric()
        self.grid_risk_events = NullMetric()
        self.auto_control_latency = NullMetric()
        
        # ADFI Observability Metrics
        self.adfi_ingestion_rate_total = NullMetric()
        self.adfi_pipeline_latency_seconds = NullMetric()
        self.adfi_deterministic_cycles_total = NullMetric()
        self.adfi_source_health = NullMetric()
        self.adfi_telemetry_packets_total = NullMetric()
        
        # AECE Autonomous Control Metrics (extended)
        self.aece_control_actions_total = NullMetric()
        self.aece_emergency_stop_state = NullMetric()
        self.grid_stability_index = NullMetric()
        self.solar_efficiency_score = NullMetric()
        
        # External API Metrics
        self.api_latency_seconds = NullMetric()
        self.investor_clients_active = NullMetric()
        self.auth_failures_total = NullMetric()
        self.onboarding_events_total = NullMetric()
        
        # NeuroBridge 11D Overview Metrics
        self.active_modules = NullMetric()
        self.celery_queue_depth = NullMetric()
        self.redis_health = NullMetric()
        self.hardware_bridge_status = NullMetric()
        self.prediction_accuracy = NullMetric()
        self.phase1_compliance_status = NullMetric()
    
    def _init_prometheus_metrics(self):
        try:
            # ==================================================================
            # EXISTING METRICS (preserved)
            # ==================================================================
            
            self.api_requests_total = self._safe_create_metric(
                Counter, 'neurobridge_api_requests_total',
                'Total number of API requests',
                labelnames=['method', 'endpoint', 'status_code', 'user_type']
            )
            
            self.api_request_duration_seconds = self._safe_create_metric(
                Histogram, 'neurobridge_api_request_duration_seconds',
                'API request duration in seconds',
                labelnames=['method', 'endpoint'],
                buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30]
            )
            
            self.api_requests_active = self._safe_create_metric(
                Gauge, 'neurobridge_api_requests_active',
                'Number of active API requests'
            )
            
            self.celery_tasks_total = self._safe_create_metric(
                Counter, 'neurobridge_celery_tasks_total',
                'Total number of Celery tasks executed',
                labelnames=['task_name', 'status', 'queue']
            )
            
            self.celery_task_duration_seconds = self._safe_create_metric(
                Histogram, 'neurobridge_celery_task_duration_seconds',
                'Celery task duration in seconds',
                labelnames=['task_name', 'queue'],
                buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]
            )
            
            self.celery_queue_size = self._safe_create_metric(
                Gauge, 'neurobridge_celery_queue_size',
                'Number of tasks in Celery queue',
                labelnames=['queue_name']
            )
            
            self.celery_active_workers = self._safe_create_metric(
                Gauge, 'neurobridge_celery_active_workers',
                'Number of active Celery workers'
            )
            
            self.celery_task_retries = self._safe_create_metric(
                Counter, 'neurobridge_celery_task_retries',
                'Number of Celery task retries',
                labelnames=['task_name']
            )
            
            self.energy_power_kw = self._safe_create_metric(
                Gauge, 'neurobridge_energy_power_kw',
                'Current power output in kilowatts',
                labelnames=['sector', 'source']
            )
            
            self.energy_frequency_hz = self._safe_create_metric(
                Gauge, 'neurobridge_energy_frequency_hz',
                'Grid frequency in hertz',
                labelnames=['grid_zone']
            )
            
            self.energy_efficiency_percent = self._safe_create_metric(
                Gauge, 'neurobridge_energy_efficiency_percent',
                'System efficiency percentage',
                labelnames=['component']
            )
            
            self.energy_daily_production_kwh = self._safe_create_metric(
                Gauge, 'neurobridge_energy_daily_production_kwh',
                'Daily energy production',
                labelnames=['sector']
            )
            
            self.energy_co2_savings_kg = self._safe_create_metric(
                Gauge, 'neurobridge_energy_co2_savings_kg',
                'CO2 savings in kilograms',
                labelnames=['period']
            )
            
            self.energy_voltage_v = self._safe_create_metric(
                Gauge, 'neurobridge_energy_voltage_v',
                'Grid voltage in volts',
                labelnames=['phase']
            )
            
            self.energy_current_a = self._safe_create_metric(
                Gauge, 'neurobridge_energy_current_a',
                'Grid current in amperes',
                labelnames=['phase']
            )
            
            self.weather_solar_irradiance_wm2 = self._safe_create_metric(
                Gauge, 'neurobridge_weather_solar_irradiance_wm2',
                'Solar irradiance in watts per square meter'
            )
            
            self.weather_temperature_celsius = self._safe_create_metric(
                Gauge, 'neurobridge_weather_temperature_celsius',
                'Ambient temperature in celsius'
            )
            
            self.weather_cloud_cover_percent = self._safe_create_metric(
                Gauge, 'neurobridge_weather_cloud_cover_percent',
                'Cloud cover percentage'
            )
            
            self.weather_wind_speed_ms = self._safe_create_metric(
                Gauge, 'neurobridge_weather_wind_speed_ms',
                'Wind speed in meters per second'
            )
            
            self.weather_humidity_percent = self._safe_create_metric(
                Gauge, 'neurobridge_weather_humidity_percent',
                'Relative humidity percentage'
            )
            
            self.weather_pressure_hpa = self._safe_create_metric(
                Gauge, 'neurobridge_weather_pressure_hpa',
                'Atmospheric pressure in hectopascals'
            )
            
            self.kernel_native = self._safe_create_metric(
                Gauge, 'neurobridge_kernel_native',
                'Native C++ kernel status'
            )
            
            self.redis_available = self._safe_create_metric(
                Gauge, 'neurobridge_redis_available',
                'Redis availability status'
            )
            
            self.db_pool_size = self._safe_create_metric(
                Gauge, 'neurobridge_db_pool_size',
                'Database connection pool size',
                labelnames=['status']
            )
            
            self.websocket_connections = self._safe_create_metric(
                Gauge, 'neurobridge_websocket_connections',
                'Number of active WebSocket connections'
            )
            
            self.database_connections_active = self._safe_create_metric(
                Gauge, 'neurobridge_database_connections_active',
                'Number of active database connections'
            )
            
            self.database_query_duration_seconds = self._safe_create_metric(
                Histogram, 'neurobridge_database_query_duration_seconds',
                'Database query duration in seconds',
                labelnames=['operation', 'table'],
                buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1]
            )
            
            self.system_cpu_percent = self._safe_create_metric(
                Gauge, 'neurobridge_system_cpu_percent',
                'System CPU usage percentage'
            )
            
            self.system_memory_percent = self._safe_create_metric(
                Gauge, 'neurobridge_system_memory_percent',
                'System memory usage percentage'
            )
            
            self.system_disk_usage_percent = self._safe_create_metric(
                Gauge, 'neurobridge_system_disk_usage_percent',
                'System disk usage percentage',
                labelnames=['mountpoint']
            )
            
            self.process_cpu_percent = self._safe_create_metric(
                Gauge, 'neurobridge_process_cpu_percent',
                'Process CPU usage percentage'
            )
            
            self.process_memory_mb = self._safe_create_metric(
                Gauge, 'neurobridge_process_memory_mb',
                'Process memory usage in MB'
            )
            
            self.process_threads = self._safe_create_metric(
                Gauge, 'neurobridge_process_threads',
                'Number of process threads'
            )
            
            self.app_uptime_seconds = self._safe_create_metric(
                Gauge, 'neurobridge_app_uptime_seconds',
                'Application uptime in seconds'
            )
            
            self.gc_collections_total = self._safe_create_metric(
                Counter, 'neurobridge_gc_collections_total',
                'Total garbage collections',
                labelnames=['generation']
            )
            
            self.gc_collection_duration_seconds = self._safe_create_metric(
                Histogram, 'neurobridge_gc_collection_duration_seconds',
                'Garbage collection duration',
                labelnames=['generation'],
                buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1]
            )
            
            self.partner_energy_usage_kwh = self._safe_create_metric(
                Gauge, 'neurobridge_partner_energy_usage_kwh',
                'Energy usage per partner',
                labelnames=['partner_id', 'partner_name']
            )
            
            self.partner_system_uptime_percent = self._safe_create_metric(
                Gauge, 'neurobridge_partner_system_uptime_percent',
                'System uptime percentage per partner',
                labelnames=['partner_id']
            )
            
            self.partner_request_count = self._safe_create_metric(
                Counter, 'neurobridge_partner_request_count',
                'Number of requests per partner',
                labelnames=['partner_id', 'endpoint']
            )
            
            self.active_sessions = self._safe_create_metric(
                Gauge, 'neurobridge_active_sessions',
                'Number of active user sessions',
                labelnames=['user_type']
            )
            
            self.api_key_usage_total = self._safe_create_metric(
                Counter, 'neurobridge_api_key_usage_total',
                'Total API key usage',
                labelnames=['api_key_id', 'endpoint']
            )
            
            self.rate_limit_exceeded_total = self._safe_create_metric(
                Counter, 'neurobridge_rate_limit_exceeded_total',
                'Rate limit exceeded events',
                labelnames=['client_id', 'endpoint']
            )
            
            self.user_login_total = self._safe_create_metric(
                Counter, 'neurobridge_user_login_total',
                'User login attempts',
                labelnames=['user_type', 'status']
            )
            
            self.user_login_failures_total = self._safe_create_metric(
                Counter, 'neurobridge_user_login_failures_total',
                'Failed login attempts',
                labelnames=['user_type', 'reason']
            )
            
            self.inverter_temperature_celsius = self._safe_create_metric(
                Gauge, 'neurobridge_inverter_temperature_celsius',
                'Inverter temperature in celsius',
                labelnames=['inverter_id']
            )
            
            self.inverter_efficiency_percent = self._safe_create_metric(
                Gauge, 'neurobridge_inverter_efficiency_percent',
                'Inverter efficiency percentage',
                labelnames=['inverter_id']
            )
            
            self.battery_soc_percent = self._safe_create_metric(
                Gauge, 'neurobridge_battery_soc_percent',
                'Battery state of charge',
                labelnames=['battery_id']
            )
            
            self.battery_health_percent = self._safe_create_metric(
                Gauge, 'neurobridge_battery_health_percent',
                'Battery health percentage',
                labelnames=['battery_id']
            )
            
            self.aece_actions_total = self._safe_create_metric(
                Counter, 'neurobridge_aece_actions_total',
                'Total AECE control actions',
                labelnames=['action', 'priority']
            )
            
            self.aece_decision_latency_ms = self._safe_create_metric(
                Histogram, 'neurobridge_aece_decision_latency_ms',
                'AECE decision latency in milliseconds',
                buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000]
            )
            
            self.aece_risk_score = self._safe_create_metric(
                Gauge, 'neurobridge_aece_risk_score',
                'Current composite risk score'
            )
            
            self.grid_risk_events = self._safe_create_metric(
                Counter, 'neurobridge_grid_risk_events_total',
                'Grid risk events detected',
                labelnames=['risk_level']
            )
            
            self.auto_control_latency = self._safe_create_metric(
                Histogram, 'neurobridge_auto_control_latency_ms',
                'Auto control latency in milliseconds',
                buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
            )
            
            # ==================================================================
            # ADFI OBSERVABILITY METRICS
            # ==================================================================
            
            self.adfi_ingestion_rate_total = self._safe_create_metric(
                Counter, 'neurobridge_adfi_ingestion_rate_total',
                'Total number of ADFI data ingestion events',
                labelnames=['source', 'module']
            )
            
            self.adfi_pipeline_latency_seconds = self._safe_create_metric(
                Histogram, 'neurobridge_adfi_pipeline_latency_seconds',
                'ADFI data pipeline processing latency in seconds',
                labelnames=['source', 'module'],
                buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]
            )
            
            self.adfi_deterministic_cycles_total = self._safe_create_metric(
                Counter, 'neurobridge_adfi_deterministic_cycles_total',
                'Total number of deterministic physics cycles executed',
                labelnames=['source', 'module']
            )
            
            self.adfi_source_health = self._safe_create_metric(
                Gauge, 'neurobridge_adfi_source_health',
                'Health status of ADFI data sources (1=healthy, 0=unhealthy)',
                labelnames=['source']
            )
            
            self.adfi_telemetry_packets_total = self._safe_create_metric(
                Counter, 'neurobridge_adfi_telemetry_packets_total',
                'Total number of telemetry packets processed',
                labelnames=['source', 'component']
            )
            
            # ==================================================================
            # AECE AUTONOMOUS CONTROL METRICS
            # ==================================================================
            
            self.aece_control_actions_total = self._safe_create_metric(
                Counter, 'neurobridge_aece_control_actions_total',
                'Total number of AECE autonomous control actions executed',
                labelnames=['action', 'module']
            )
            
            self.aece_emergency_stop_state = self._safe_create_metric(
                Gauge, 'neurobridge_aece_emergency_stop_state',
                'AECE emergency stop state (1=active, 0=inactive)',
                labelnames=['component']
            )
            
            self.grid_stability_index = self._safe_create_metric(
                Gauge, 'neurobridge_grid_stability_index',
                'Grid Stability Index (0-100)',
                labelnames=['phase']
            )
            
            self.solar_efficiency_score = self._safe_create_metric(
                Gauge, 'neurobridge_solar_efficiency_score',
                'Solar Efficiency Score (0-100)',
                labelnames=['phase']
            )
            
            # ==================================================================
            # EXTERNAL API METRICS
            # ==================================================================
            
            self.api_latency_seconds = self._safe_create_metric(
                Histogram, 'neurobridge_api_latency_seconds',
                'External API endpoint latency in seconds',
                labelnames=['route', 'method', 'status'],
                buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
            )
            
            self.investor_clients_active = self._safe_create_metric(
                Gauge, 'neurobridge_investor_clients_active',
                'Number of active investor/demo clients'
            )
            
            self.auth_failures_total = self._safe_create_metric(
                Counter, 'neurobridge_auth_failures_total',
                'Total number of authentication failures',
                labelnames=['route', 'method']
            )
            
            self.onboarding_events_total = self._safe_create_metric(
                Counter, 'neurobridge_onboarding_events_total',
                'Total number of client onboarding events',
                labelnames=['plan']
            )
            
            # ==================================================================
            # NEUROBRIDGE 11D OVERVIEW METRICS
            # ==================================================================
            
            self.active_modules = self._safe_create_metric(
                Gauge, 'neurobridge_active_modules',
                'Number of active NeuroBridge 11D modules',
                labelnames=['module']
            )
            
            self.celery_queue_depth = self._safe_create_metric(
                Gauge, 'neurobridge_celery_queue_depth',
                'Depth of Celery task queues',
                labelnames=['queue']
            )
            
            self.redis_health = self._safe_create_metric(
                Gauge, 'neurobridge_redis_health',
                'Redis connection health (1=healthy, 0=unhealthy)'
            )
            
            self.hardware_bridge_status = self._safe_create_metric(
                Gauge, 'neurobridge_hardware_bridge_status',
                'Hardware bridge component status (1=connected, 0=disconnected)',
                labelnames=['component']
            )
            
            self.prediction_accuracy = self._safe_create_metric(
                Gauge, 'neurobridge_prediction_accuracy',
                'Prediction accuracy score (0-1)',
                labelnames=['component']
            )
            
            self.phase1_compliance_status = self._safe_create_metric(
                Gauge, 'neurobridge_phase1_compliance_status',
                'Phase 1 Production compliance status (1=compliant, 0=non-compliant)'
            )
            
            # ==================================================================
            # INITIALIZE DEFAULT VALUES
            # ==================================================================
            
            self._init_default_values()
            
            count = len(self._registered_metrics)
            logger.info(f"[METRICS] prometheus initialized total_metrics={count}")
            
        except Exception as e:
            logger.error(f"[METRICS] initialization failed: {e}")
            self._available = False
            self._init_null_metrics()
    
    def _init_default_values(self):
        """Set initial default values for gauge metrics."""
        if not self._available:
            return
        try:
            self.kernel_native.set(0)
            self.redis_available.set(0)
            self.websocket_connections.set(0)
            self.celery_active_workers.set(0)
            self.aece_risk_score.set(0.0)
            
            if isinstance(self.aece_emergency_stop_state, Gauge):
                self.aece_emergency_stop_state.labels(component='system').set(0)
            if isinstance(self.grid_stability_index, Gauge):
                self.grid_stability_index.labels(phase='production').set(0)
            if isinstance(self.solar_efficiency_score, Gauge):
                self.solar_efficiency_score.labels(phase='production').set(0)
            
            if isinstance(self.investor_clients_active, Gauge):
                self.investor_clients_active.set(0)
            
            if isinstance(self.redis_health, Gauge):
                self.redis_health.set(0)
            if isinstance(self.phase1_compliance_status, Gauge):
                self.phase1_compliance_status.set(0)
            
        except Exception as e:
            logger.debug(f"[METRICS] Default values init error: {e}")
    
    @property
    def available(self) -> bool:
        return self._available
    
    def get_registered_metrics(self) -> List[str]:
        with self._lock:
            return list(self._registered_metrics)


metrics = NeuroBridgeMetrics()

# ============================================================================
# CONTEXT MANAGERS
# ============================================================================

@contextmanager
def track_duration(metric: Any, labels: Optional[Dict[str, str]] = None):
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        if metric is not None and not isinstance(metric, NullMetric):
            try:
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
            except Exception:
                pass


@contextmanager
def track_request(method: str, endpoint: str):
    if not metrics.available:
        yield
        return
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        try:
            if not isinstance(metrics.api_requests_total, NullMetric):
                metrics.api_requests_total.labels(
                    method=method, endpoint=endpoint, 
                    status_code='200', user_type='unknown'
                ).inc()
            if not isinstance(metrics.api_request_duration_seconds, NullMetric):
                metrics.api_request_duration_seconds.labels(
                    method=method, endpoint=endpoint
                ).observe(duration)
        except Exception:
            pass


@contextmanager
def track_celery_task(task_name: str, queue: str = "default"):
    if not metrics.available:
        yield
        return
    start_time = time.time()
    status = "success"
    try:
        yield
    except Exception:
        status = "failure"
        raise
    finally:
        duration = time.time() - start_time
        try:
            if not isinstance(metrics.celery_tasks_total, NullMetric):
                metrics.celery_tasks_total.labels(
                    task_name=task_name, status=status, queue=queue
                ).inc()
            if not isinstance(metrics.celery_task_duration_seconds, NullMetric):
                metrics.celery_task_duration_seconds.labels(
                    task_name=task_name, queue=queue
                ).observe(duration)
        except Exception:
            pass


# ============================================================================
# EXISTING METRICS UPDATE FUNCTIONS (preserved)
# ============================================================================

def update_energy_metrics(power_kw: float, frequency_hz: float, efficiency_percent: float, sector: str = "renewables", voltage_v: float = None, current_a: float = None):
    if not metrics.available:
        return
    try:
        if metrics.energy_power_kw and not isinstance(metrics.energy_power_kw, NullMetric):
            metrics.energy_power_kw.labels(sector=sector, source="grid").set(power_kw)
        if metrics.energy_frequency_hz and not isinstance(metrics.energy_frequency_hz, NullMetric):
            metrics.energy_frequency_hz.labels(grid_zone="abuja").set(frequency_hz)
        if metrics.energy_efficiency_percent and not isinstance(metrics.energy_efficiency_percent, NullMetric):
            metrics.energy_efficiency_percent.labels(component="system").set(efficiency_percent)
        if voltage_v is not None and metrics.energy_voltage_v and not isinstance(metrics.energy_voltage_v, NullMetric):
            metrics.energy_voltage_v.labels(phase="single").set(voltage_v)
        if current_a is not None and metrics.energy_current_a and not isinstance(metrics.energy_current_a, NullMetric):
            metrics.energy_current_a.labels(phase="single").set(current_a)
    except Exception:
        pass


def update_weather_metrics(irradiance_wm2: float, temperature_c: float, cloud_cover_percent: float, wind_speed_ms: float, humidity_percent: float = None, pressure_hpa: float = None):
    if not metrics.available:
        return
    try:
        if metrics.weather_solar_irradiance_wm2 and not isinstance(metrics.weather_solar_irradiance_wm2, NullMetric):
            metrics.weather_solar_irradiance_wm2.set(irradiance_wm2)
        if metrics.weather_temperature_celsius and not isinstance(metrics.weather_temperature_celsius, NullMetric):
            metrics.weather_temperature_celsius.set(temperature_c)
        if metrics.weather_cloud_cover_percent and not isinstance(metrics.weather_cloud_cover_percent, NullMetric):
            metrics.weather_cloud_cover_percent.set(cloud_cover_percent)
        if metrics.weather_wind_speed_ms and not isinstance(metrics.weather_wind_speed_ms, NullMetric):
            metrics.weather_wind_speed_ms.set(wind_speed_ms)
        if humidity_percent is not None and metrics.weather_humidity_percent and not isinstance(metrics.weather_humidity_percent, NullMetric):
            metrics.weather_humidity_percent.set(humidity_percent)
        if pressure_hpa is not None and metrics.weather_pressure_hpa and not isinstance(metrics.weather_pressure_hpa, NullMetric):
            metrics.weather_pressure_hpa.set(pressure_hpa)
    except Exception:
        pass


def update_quantum_metrics(calculation_duration_seconds: float, gain_percent: float, cache_hit_rate: float, calculation_type: str = "yield_prediction", coherence: float = None, sector: str = "renewables"):
    pass


def update_celery_queue_metrics(queue_sizes: Dict[str, int]):
    if not metrics.available:
        return
    try:
        allowed_queues = ['control_queue', 'energy_queue', 'weather_queue', 'monitoring_queue', 'prediction_queue', 'reporting_queue', 'adfi_queue', 'high_priority', 'default', 'scheduled', 'low_priority']
        for queue_name, size in queue_sizes.items():
            if queue_name in allowed_queues:
                if metrics.celery_queue_size and not isinstance(metrics.celery_queue_size, NullMetric):
                    metrics.celery_queue_size.labels(queue_name=queue_name).set(size)
    except Exception:
        pass


def update_partner_metrics(partner_id: str, partner_name: str, energy_kwh: float, uptime_percent: float, request_count: int = None, endpoint: str = None):
    if not metrics.available:
        return
    try:
        if metrics.partner_energy_usage_kwh and not isinstance(metrics.partner_energy_usage_kwh, NullMetric):
            metrics.partner_energy_usage_kwh.labels(partner_id=partner_id, partner_name=partner_name).set(energy_kwh)
        if metrics.partner_system_uptime_percent and not isinstance(metrics.partner_system_uptime_percent, NullMetric):
            metrics.partner_system_uptime_percent.labels(partner_id=partner_id).set(uptime_percent)
        if request_count is not None and endpoint is not None:
            if metrics.partner_request_count and not isinstance(metrics.partner_request_count, NullMetric):
                metrics.partner_request_count.labels(partner_id=partner_id, endpoint=endpoint).inc(request_count)
    except Exception:
        pass


def update_system_metrics(cpu_percent: float = None, memory_percent: float = None, process_cpu: float = None, process_memory_mb: float = None, uptime_seconds: float = None):
    if not metrics.available:
        return
    try:
        if cpu_percent is not None and metrics.system_cpu_percent and not isinstance(metrics.system_cpu_percent, NullMetric):
            metrics.system_cpu_percent.set(cpu_percent)
        if memory_percent is not None and metrics.system_memory_percent and not isinstance(metrics.system_memory_percent, NullMetric):
            metrics.system_memory_percent.set(memory_percent)
        if process_cpu is not None and metrics.process_cpu_percent and not isinstance(metrics.process_cpu_percent, NullMetric):
            metrics.process_cpu_percent.set(process_cpu)
        if process_memory_mb is not None and metrics.process_memory_mb and not isinstance(metrics.process_memory_mb, NullMetric):
            metrics.process_memory_mb.set(process_memory_mb)
        if uptime_seconds is not None and metrics.app_uptime_seconds and not isinstance(metrics.app_uptime_seconds, NullMetric):
            metrics.app_uptime_seconds.set(uptime_seconds)
    except Exception:
        pass


def update_hardware_metrics(inverter_id: str, temperature_c: float = None, efficiency_percent: float = None, battery_id: str = None, battery_soc: float = None, battery_health: float = None):
    if not metrics.available:
        return
    try:
        if temperature_c is not None:
            if metrics.inverter_temperature_celsius and not isinstance(metrics.inverter_temperature_celsius, NullMetric):
                metrics.inverter_temperature_celsius.labels(inverter_id=inverter_id).set(temperature_c)
        if efficiency_percent is not None:
            if metrics.inverter_efficiency_percent and not isinstance(metrics.inverter_efficiency_percent, NullMetric):
                metrics.inverter_efficiency_percent.labels(inverter_id=inverter_id).set(efficiency_percent)
        if battery_id is not None:
            if battery_soc is not None:
                if metrics.battery_soc_percent and not isinstance(metrics.battery_soc_percent, NullMetric):
                    metrics.battery_soc_percent.labels(battery_id=battery_id).set(battery_soc)
            if battery_health is not None:
                if metrics.battery_health_percent and not isinstance(metrics.battery_health_percent, NullMetric):
                    metrics.battery_health_percent.labels(battery_id=battery_id).set(battery_health)
    except Exception:
        pass


def record_user_login(user_type: str, status: str, failure_reason: str = None):
    if not metrics.available:
        return
    try:
        if metrics.user_login_total and not isinstance(metrics.user_login_total, NullMetric):
            metrics.user_login_total.labels(user_type=user_type, status=status).inc()
        if status == "failed" and failure_reason:
            if metrics.user_login_failures_total and not isinstance(metrics.user_login_failures_total, NullMetric):
                metrics.user_login_failures_total.labels(user_type=user_type, reason=failure_reason).inc()
    except Exception:
        pass


# ============================================================================
# EXISTING AECE METRICS UPDATE FUNCTIONS (preserved)
# ============================================================================

def record_aece_action(action: str, priority: str, count: int = 1):
    if not metrics.available:
        return
    allowed_actions = ['reduce_load', 'redistribute_energy', 'preemptive_stabilization', 'trigger_alert', 'lockdown_mode']
    if action not in allowed_actions:
        return
    try:
        if metrics.aece_actions_total and not isinstance(metrics.aece_actions_total, NullMetric):
            metrics.aece_actions_total.labels(action=action, priority=priority).inc(count)
    except Exception:
        pass


@contextmanager
def track_aece_decision():
    if not metrics.available:
        yield
        return
    start_time_ms = time.time() * 1000
    try:
        yield
    finally:
        duration_ms = (time.time() * 1000) - start_time_ms
        try:
            if metrics.aece_decision_latency_ms and not isinstance(metrics.aece_decision_latency_ms, NullMetric):
                metrics.aece_decision_latency_ms.observe(duration_ms)
        except Exception:
            pass


def update_aece_risk_score(risk_score: float):
    if not metrics.available:
        return
    try:
        risk_score = max(0.0, min(1.0, risk_score))
        if metrics.aece_risk_score and not isinstance(metrics.aece_risk_score, NullMetric):
            metrics.aece_risk_score.set(risk_score)
    except Exception:
        pass


def record_grid_risk_event(risk_level: str):
    if not metrics.available:
        return
    allowed_levels = ['critical', 'high', 'medium', 'low']
    if risk_level not in allowed_levels:
        risk_level = 'medium'
    try:
        if metrics.grid_risk_events and not isinstance(metrics.grid_risk_events, NullMetric):
            metrics.grid_risk_events.labels(risk_level=risk_level).inc()
    except Exception:
        pass


@contextmanager
def track_auto_control_latency():
    if not metrics.available:
        yield
        return
    start_time_ms = time.time() * 1000
    try:
        yield
    finally:
        duration_ms = (time.time() * 1000) - start_time_ms
        try:
            if metrics.auto_control_latency and not isinstance(metrics.auto_control_latency, NullMetric):
                metrics.auto_control_latency.observe(duration_ms)
        except Exception:
            pass


# ============================================================================
# ADFI OBSERVABILITY HELPER FUNCTIONS
# ============================================================================

def record_adfi_ingestion(source: str, packets: int = 1, latency_seconds: float = 0.0, module: str = "adfi_engine"):
    if not metrics.available:
        return
    try:
        if metrics.adfi_ingestion_rate_total and not isinstance(metrics.adfi_ingestion_rate_total, NullMetric):
            metrics.adfi_ingestion_rate_total.labels(source=source, module=module).inc(packets)
        if latency_seconds > 0:
            if metrics.adfi_pipeline_latency_seconds and not isinstance(metrics.adfi_pipeline_latency_seconds, NullMetric):
                metrics.adfi_pipeline_latency_seconds.labels(source=source, module=module).observe(latency_seconds)
        if metrics.adfi_telemetry_packets_total and not isinstance(metrics.adfi_telemetry_packets_total, NullMetric):
            metrics.adfi_telemetry_packets_total.labels(source=source, component="ingestion").inc(packets)
    except Exception:
        pass


def record_adfi_cycle(source: str, module: str = "adfi_engine"):
    if not metrics.available:
        return
    try:
        if metrics.adfi_deterministic_cycles_total and not isinstance(metrics.adfi_deterministic_cycles_total, NullMetric):
            metrics.adfi_deterministic_cycles_total.labels(source=source, module=module).inc()
    except Exception:
        pass


def set_adfi_source_health(source: str, healthy: bool):
    if not metrics.available:
        return
    try:
        value = 1 if healthy else 0
        if metrics.adfi_source_health and not isinstance(metrics.adfi_source_health, NullMetric):
            metrics.adfi_source_health.labels(source=source).set(value)
    except Exception:
        pass


def record_adfi_pipeline_latency(source: str, latency_seconds: float, module: str = "data_pipeline"):
    if not metrics.available:
        return
    try:
        if metrics.adfi_pipeline_latency_seconds and not isinstance(metrics.adfi_pipeline_latency_seconds, NullMetric):
            metrics.adfi_pipeline_latency_seconds.labels(source=source, module=module).observe(latency_seconds)
    except Exception:
        pass


# ============================================================================
# AECE AUTONOMOUS CONTROL HELPER FUNCTIONS
# ============================================================================

def record_aece_decision(action: str, risk_score: float, gsi: float = None, ses: float = None, module: str = "aece_engine"):
    if not metrics.available:
        return
    try:
        allowed_actions = ['reduce_load', 'redistribute_energy', 'preemptive_stabilization', 
                          'trigger_alert', 'lockdown_mode', 'throttle_output', 'engage_backup']
        if action not in allowed_actions:
            action = 'other'
        
        if metrics.aece_control_actions_total and not isinstance(metrics.aece_control_actions_total, NullMetric):
            metrics.aece_control_actions_total.labels(action=action, module=module).inc()
        
        if risk_score is not None:
            update_aece_risk_score(risk_score)
        
        if gsi is not None:
            if metrics.grid_stability_index and not isinstance(metrics.grid_stability_index, NullMetric):
                metrics.grid_stability_index.labels(phase='production').set(max(0, min(100, gsi)))
        
        if ses is not None:
            if metrics.solar_efficiency_score and not isinstance(metrics.solar_efficiency_score, NullMetric):
                metrics.solar_efficiency_score.labels(phase='production').set(max(0, min(100, ses)))
    except Exception:
        pass


def set_emergency_stop_state(active: bool, component: str = "system"):
    if not metrics.available:
        return
    try:
        value = 1 if active else 0
        if metrics.aece_emergency_stop_state and not isinstance(metrics.aece_emergency_stop_state, NullMetric):
            metrics.aece_emergency_stop_state.labels(component=component).set(value)
    except Exception:
        pass


def set_grid_stability_index(value: float):
    if not metrics.available:
        return
    try:
        value = max(0, min(100, value))
        if metrics.grid_stability_index and not isinstance(metrics.grid_stability_index, NullMetric):
            metrics.grid_stability_index.labels(phase='production').set(value)
    except Exception:
        pass


def set_solar_efficiency_score(value: float):
    if not metrics.available:
        return
    try:
        value = max(0, min(100, value))
        if metrics.solar_efficiency_score and not isinstance(metrics.solar_efficiency_score, NullMetric):
            metrics.solar_efficiency_score.labels(phase='production').set(value)
    except Exception:
        pass


# ============================================================================
# EXTERNAL API HELPER FUNCTIONS
# ============================================================================

def record_external_request(route: str, method: str, status: int, latency_seconds: float):
    if not metrics.available:
        return
    try:
        if metrics.api_latency_seconds and not isinstance(metrics.api_latency_seconds, NullMetric):
            metrics.api_latency_seconds.labels(
                route=route, method=method, status=str(status)
            ).observe(latency_seconds)
    except Exception:
        pass


def record_auth_failure(route: str, method: str = "POST"):
    if not metrics.available:
        return
    try:
        if metrics.auth_failures_total and not isinstance(metrics.auth_failures_total, NullMetric):
            metrics.auth_failures_total.labels(route=route, method=method).inc()
    except Exception:
        pass


def record_onboarding_event(plan: str = "unknown"):
    if not metrics.available:
        return
    try:
        allowed_plans = ['investor_demo', 'pilot_partner', 'production', 'trial', 'unknown']
        if plan not in allowed_plans:
            plan = 'other'
        if metrics.onboarding_events_total and not isinstance(metrics.onboarding_events_total, NullMetric):
            metrics.onboarding_events_total.labels(plan=plan).inc()
    except Exception:
        pass


def set_investor_clients_active(count: int):
    if not metrics.available:
        return
    try:
        count = max(0, count)
        if metrics.investor_clients_active and not isinstance(metrics.investor_clients_active, NullMetric):
            metrics.investor_clients_active.set(count)
    except Exception:
        pass


# ============================================================================
# NEUROBRIDGE 11D OVERVIEW HELPER FUNCTIONS
# ============================================================================

def set_active_module(module: str, active: bool):
    if not metrics.available:
        return
    try:
        value = 1 if active else 0
        if metrics.active_modules and not isinstance(metrics.active_modules, NullMetric):
            metrics.active_modules.labels(module=module).set(value)
    except Exception:
        pass


def set_celery_queue_depth(queue: str, depth: int):
    if not metrics.available:
        return
    try:
        depth = max(0, depth)
        if metrics.celery_queue_depth and not isinstance(metrics.celery_queue_depth, NullMetric):
            metrics.celery_queue_depth.labels(queue=queue).set(depth)
    except Exception:
        pass


def set_redis_health(healthy: bool):
    if not metrics.available:
        return
    try:
        value = 1 if healthy else 0
        if metrics.redis_health and not isinstance(metrics.redis_health, NullMetric):
            metrics.redis_health.set(value)
        if metrics.redis_available and not isinstance(metrics.redis_available, NullMetric):
            metrics.redis_available.set(value)
    except Exception:
        pass


def set_hardware_bridge_status(component: str, healthy: bool):
    if not metrics.available:
        return
    try:
        value = 1 if healthy else 0
        if metrics.hardware_bridge_status and not isinstance(metrics.hardware_bridge_status, NullMetric):
            metrics.hardware_bridge_status.labels(component=component).set(value)
    except Exception:
        pass


def set_prediction_accuracy(component: str, value: float):
    if not metrics.available:
        return
    try:
        value = max(0.0, min(1.0, value))
        if metrics.prediction_accuracy and not isinstance(metrics.prediction_accuracy, NullMetric):
            metrics.prediction_accuracy.labels(component=component).set(value)
    except Exception:
        pass


def set_phase1_compliance_status(active: bool):
    if not metrics.available:
        return
    try:
        value = 1 if active else 0
        if metrics.phase1_compliance_status and not isinstance(metrics.phase1_compliance_status, NullMetric):
            metrics.phase1_compliance_status.set(value)
    except Exception:
        pass


# ============================================================================
# METRICS EXPORT ENDPOINT
# ============================================================================

def get_metrics_response():
    from fastapi.responses import Response
    if not metrics.available or not PROMETHEUS_AVAILABLE:
        return Response(content="# Prometheus metrics disabled\n", media_type="text/plain")
    try:
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"[METRICS] generate failed: {e}")
        return Response(content=f"# Error: {e}\n", media_type="text/plain", status_code=500)


def is_prometheus_healthy() -> bool:
    if not metrics.available or not PROMETHEUS_AVAILABLE:
        return False
    try:
        generate_latest(REGISTRY)
        return True
    except Exception:
        return False


def get_metrics_summary() -> Dict[str, Any]:
    if not metrics.available:
        return {"available": False, "phase": "PHASE_1_PRODUCTION"}
    return {"available": True, "phase": "PHASE_1_PRODUCTION"}

# ============================================================================
# MIDDLEWARE - WITH FIXED PATH SANITIZER
# ============================================================================

class PrometheusMiddleware:
    """
    ASGI middleware for automatic Prometheus metrics collection.
    
    Tracks:
    - Total API requests (counter with method, endpoint, status, user_type)
    - Request duration (histogram with method, endpoint)
    - Active requests (gauge)
    
    Path sanitization uses safe patterns that won't match short words
    like 'api', 'auth', 'v1', 'health', etc.
    """
    
    def __init__(self, app):
        self.app = app
        self.metrics_available = metrics.available
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.metrics_available:
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        method = scope.get("method", "unknown")
        path = scope.get("path", "unknown")
        simplified_path = self._simplify_path(path)
        
        if metrics.api_requests_active and not isinstance(metrics.api_requests_active, NullMetric):
            metrics.api_requests_active.inc()
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                duration = time.time() - start_time
                try:
                    if metrics.api_requests_total and not isinstance(metrics.api_requests_total, NullMetric):
                        metrics.api_requests_total.labels(
                            method=method, endpoint=simplified_path,
                            status_code=str(status_code), user_type="unknown"
                        ).inc()
                    if metrics.api_request_duration_seconds and not isinstance(metrics.api_request_duration_seconds, NullMetric):
                        metrics.api_request_duration_seconds.labels(method=method, endpoint=simplified_path).observe(duration)
                except Exception:
                    pass
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if metrics.api_requests_active and not isinstance(metrics.api_requests_active, NullMetric):
                metrics.api_requests_active.dec()
    
    def _simplify_path(self, path: str) -> str:
        """
        Sanitize endpoint path for Prometheus labels.
        
        Uses the global sanitize_endpoint() function which:
        - Only replaces UUIDs (8-4-4-4-12 format)
        - Only replaces long hex IDs (12+ chars with word boundaries)
        - Only replaces pure numeric segments
        - Does NOT match short words like 'api', 'auth', 'v1', 'health'
        """
        return sanitize_endpoint(path)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Singleton
    'metrics',
    
    # Path sanitizer (exported for external use)
    'sanitize_endpoint',
    
    # Existing helper functions
    'update_energy_metrics',
    'update_weather_metrics',
    'update_quantum_metrics',
    'update_celery_queue_metrics',
    'update_partner_metrics',
    'update_system_metrics',
    'update_hardware_metrics',
    'record_user_login',
    'record_aece_action',
    'track_aece_decision',
    'update_aece_risk_score',
    'record_grid_risk_event',
    'track_auto_control_latency',
    
    # ADFI Observability helpers
    'record_adfi_ingestion',
    'record_adfi_cycle',
    'set_adfi_source_health',
    'record_adfi_pipeline_latency',
    
    # AECE Autonomous Control helpers
    'record_aece_decision',
    'set_emergency_stop_state',
    'set_grid_stability_index',
    'set_solar_efficiency_score',
    
    # External API helpers
    'record_external_request',
    'record_auth_failure',
    'record_onboarding_event',
    'set_investor_clients_active',
    
    # NeuroBridge 11D Overview helpers
    'set_active_module',
    'set_celery_queue_depth',
    'set_redis_health',
    'set_hardware_bridge_status',
    'set_prediction_accuracy',
    'set_phase1_compliance_status',
    
    # Context managers
    'track_request',
    'track_celery_task',
    'track_duration',
    
    # Export endpoint
    'get_metrics_response',
    'is_prometheus_healthy',
    'get_metrics_summary',
    
    # Middleware
    'PrometheusMiddleware',
    
    # Utilities
    'PROMETHEUS_AVAILABLE',
    'REGISTRY',
    'get_phase1_metric_stats',
    'is_phase1_allowed_metric',
    'register_metric_safe',
    'metric_exists_in_registry',
    'clear_metric_registration_cache',
    'NullMetric',
]

# Brief initialization log
logger.info("[METRICS] prometheus initialized")
logger.info(f"[METRICS] total_metrics={len(metrics.get_registered_metrics())}")
if _multiprocess_setup_done:
    logger.info("[METRICS] multiprocess=true")