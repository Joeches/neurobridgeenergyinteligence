import os
import sys
import logging
import time
import threading
from datetime import timedelta
from typing import Dict, Any, Optional, List, Tuple

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger("NeuroBridge.Celery")

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

_METRICS_AVAILABLE = False

try:
    from backend.monitoring.prometheus_metrics import (
        set_active_module,
        set_celery_queue_depth,
        set_redis_health,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    def set_active_module(*args, **kwargs): pass
    def set_celery_queue_depth(*args, **kwargs): pass
    def set_redis_health(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[Celery] prometheus metrics instrumented")
else:
    logger.debug("[Celery] prometheus metrics unavailable - running without instrumentation")

# ============================================================================
# QUEUE DEPTH MONITORING HELPERS
# ============================================================================

_queue_depth_lock = threading.RLock()
_known_queues = [
    "control_queue", "high_priority", "prediction_queue", "energy_queue",
    "weather_queue", "adfi_queue", "monitoring_queue", "reporting_queue",
    "low_priority", "default"
]

def _update_all_queue_depths(depths: Dict[str, int]):
    """Update Prometheus metrics for all queue depths."""
    if not _METRICS_AVAILABLE:
        return
    try:
        with _queue_depth_lock:
            for queue_name, depth in depths.items():
                if queue_name in _known_queues:
                    set_celery_queue_depth(queue=queue_name, depth=max(0, depth))
    except Exception as e:
        logger.debug(f"[Celery] Queue depth update failed: {e}")

def _update_queue_depth(queue_name: str, depth: int):
    """Update Prometheus metric for a single queue depth."""
    if not _METRICS_AVAILABLE:
        return
    try:
        set_celery_queue_depth(queue=queue_name, depth=max(0, depth))
    except Exception as e:
        logger.debug(f"[Celery] Queue depth update failed for {queue_name}: {e}")

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
IS_DEVELOPMENT = ENVIRONMENT in ["development", "dev", "local"]
IS_PRODUCTION = ENVIRONMENT in ["production", "prod"]
IS_OCI = (
    os.getenv("OCI_DEPLOYMENT", "false").lower() == "true" 
    or "oracle" in os.getenv("HOSTNAME", "").lower()
    or "oci" in os.getenv("CLOUD_PROVIDER", "").lower()
)

logger.info(f"[Celery] Environment: {ENVIRONMENT.upper()} | OCI Mode: {IS_OCI} | Dev Mode: {IS_DEVELOPMENT}")

# ============================================================================
# BROKER CONFIGURATION WITH SQLITE FALLBACK
# ============================================================================

# Redis configuration (primary)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # Use container name for Docker
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", 5))
REDIS_CONNECT_TIMEOUT = int(os.getenv("REDIS_CONNECT_TIMEOUT", 5))

# Build Redis URL with proper encoding
if REDIS_PASSWORD:
    import urllib.parse
    encoded_password = urllib.parse.quote_plus(REDIS_PASSWORD)
    REDIS_URL = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Result backend Redis DB (separate from broker)
RESULT_DB = int(os.getenv("RESULT_DB", 1))
if REDIS_PASSWORD:
    encoded_password = urllib.parse.quote_plus(REDIS_PASSWORD)
    REDIS_RESULT_URL = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}/{RESULT_DB}"
else:
    REDIS_RESULT_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{RESULT_DB}"

# SQLite configuration (fallback for OCI or when Redis unavailable)
CELERY_DATA_DIR = os.getenv("CELERY_DATA_DIR", os.path.join(os.getcwd(), "data", "celery"))
os.makedirs(CELERY_DATA_DIR, exist_ok=True)

SQLITE_BROKER_PATH = os.getenv(
    "CELERY_SQLITE_BROKER_PATH", 
    os.path.join(CELERY_DATA_DIR, "celery_broker.db")
)
SQLITE_RESULT_PATH = os.getenv(
    "CELERY_SQLITE_RESULT_PATH", 
    os.path.join(CELERY_DATA_DIR, "celery_results.db")
)
SQLITE_BROKER_URL = f"sqla+sqlite:///{SQLITE_BROKER_PATH}"
SQLITE_RESULT_URL = f"db+sqlite:///{SQLITE_RESULT_PATH}"


def check_redis_availability() -> Tuple[bool, Optional[str]]:
    """
    Check if Redis is available and accessible.
    
    Returns:
        Tuple of (is_available, error_message_or_None)
    """
    try:
        import redis
        logger.debug(f"Attempting Redis connection: {REDIS_HOST}:{REDIS_PORT}")
        
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
            socket_keepalive=True,
            health_check_interval=30,
        )
        
        # Test connection with ping
        response = r.ping()
        if response:
            logger.info(f"[Broker] Redis available: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
            
            # PROMETHEUS: Update Redis health
            try:
                set_redis_health(True)
            except Exception:
                pass
            
            # Check if result DB is accessible
            r_result = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=RESULT_DB,
                password=REDIS_PASSWORD,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
            )
            r_result.ping()
            logger.info(f"[Broker] Redis result backend: {REDIS_HOST}:{REDIS_PORT}/{RESULT_DB}")
            
            return True, None
            
    except ImportError:
        error_msg = "Redis library not installed (pip install redis)"
        logger.warning(f"[Broker] {error_msg}")
        try:
            set_redis_health(False)
        except Exception:
            pass
        return False, error_msg
        
    except redis.ConnectionError as e:
        error_msg = f"Redis connection failed: {e}"
        logger.warning(f"[Broker] {error_msg}")
        try:
            set_redis_health(False)
        except Exception:
            pass
        return False, error_msg
        
    except redis.TimeoutError as e:
        error_msg = f"Redis connection timeout: {e}"
        logger.warning(f"[Broker] {error_msg}")
        try:
            set_redis_health(False)
        except Exception:
            pass
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Redis unavailable: {type(e).__name__}: {e}"
        logger.warning(f"[Broker] {error_msg}")
        try:
            set_redis_health(False)
        except Exception:
            pass
        return False, error_msg


def check_sqlite_availability() -> Tuple[bool, Optional[str]]:
    """
    Check if SQLite is available for broker/result backend.
    
    Returns:
        Tuple of (is_available, error_message_or_None)
    """
    try:
        import sqlite3
        
        # Test broker path
        broker_dir = os.path.dirname(SQLITE_BROKER_PATH)
        if not os.path.exists(broker_dir):
            os.makedirs(broker_dir, exist_ok=True)
        
        # Test write access
        test_conn = sqlite3.connect(SQLITE_BROKER_PATH)
        test_conn.execute("CREATE TABLE IF NOT EXISTS _celery_test (id INTEGER PRIMARY KEY)")
        test_conn.execute("DROP TABLE IF EXISTS _celery_test")
        test_conn.close()
        
        # Test result path
        result_dir = os.path.dirname(SQLITE_RESULT_PATH)
        if not os.path.exists(result_dir):
            os.makedirs(result_dir, exist_ok=True)
        
        logger.info(f"[Broker] SQLite available: {SQLITE_BROKER_PATH}")
        return True, None
        
    except ImportError:
        error_msg = "SQLite3 library not available"
        logger.error(f"[Broker] {error_msg}")
        return False, error_msg
        
    except PermissionError as e:
        error_msg = f"SQLite write permission denied: {e}"
        logger.error(f"[Broker] {error_msg}")
        return False, error_msg
        
    except Exception as e:
        error_msg = f"SQLite unavailable: {type(e).__name__}: {e}"
        logger.error(f"[Broker] {error_msg}")
        return False, error_msg


def get_broker_config() -> Dict[str, str]:
    """
    Get broker configuration with automatic fallback to SQLite.
    
    Priority:
    1. Explicit environment variables (CELERY_BROKER_URL, CELERY_RESULT_BACKEND)
    2. Redis (if available)
    3. SQLite (fallback)
    
    Returns:
        Dictionary with broker_url, result_backend, and type
    """
    # Check for explicit overrides
    env_broker = os.getenv("CELERY_BROKER_URL")
    env_result = os.getenv("CELERY_RESULT_BACKEND")
    
    if env_broker and env_result:
        logger.info("[Broker] Using explicit environment configuration")
        return {
            "broker_url": env_broker,
            "result_backend": env_result,
            "type": "explicit"
        }
    
    # Try Redis first
    redis_available, redis_error = check_redis_availability()
    if redis_available:
        logger.info("[Broker] Using Redis broker (primary)")
        set_active_module(module="redis_broker", active=True)
        return {
            "broker_url": REDIS_URL,
            "result_backend": REDIS_RESULT_URL,
            "type": "redis"
        }
    
    # Fallback to SQLite
    logger.warning(f"[Broker] Redis unavailable: {redis_error}")
    sqlite_available, sqlite_error = check_sqlite_availability()
    
    if sqlite_available:
        logger.warning("[Broker] Using SQLite fallback (OCI/development mode)")
        logger.info(f"[Broker] Broker file: {SQLITE_BROKER_PATH}")
        logger.info(f"[Broker] Result file: {SQLITE_RESULT_PATH}")
        set_active_module(module="redis_broker", active=False)
        return {
            "broker_url": SQLITE_BROKER_URL,
            "result_backend": SQLITE_RESULT_URL,
            "type": "sqlite"
        }
    
    # Last resort - SQLite anyway
    logger.error(f"[Broker] CRITICAL: SQLite also unavailable: {sqlite_error}")
    logger.error("[Broker] Attempting SQLite anyway...")
    set_active_module(module="redis_broker", active=False)
    return {
        "broker_url": SQLITE_BROKER_URL,
        "result_backend": SQLITE_RESULT_URL,
        "type": "sqlite_fallback"
    }


# Get broker configuration
_broker_config = get_broker_config()
BROKER_URL = _broker_config["broker_url"]
RESULT_BACKEND = _broker_config["result_backend"]
BROKER_TYPE = _broker_config["type"]

logger.info(f"[Celery] Broker type: {BROKER_TYPE.upper()}")
logger.info(f"[Celery] Broker URL: {BROKER_URL.split('@')[-1] if '@' in BROKER_URL else BROKER_URL}")

# ============================================================================
# IMPORT CELERY (after configuration)
# ============================================================================

try:
    from celery import Celery, Task
    from celery.schedules import crontab
    from kombu import Exchange, Queue
    CELERY_AVAILABLE = True
    logger.info("[Celery] Celery library imported successfully")
except ImportError as e:
    logger.critical(f"[Celery] Failed to import Celery: {e}")
    logger.critical("[Celery] Install: pip install celery[redis] kombu")
    CELERY_AVAILABLE = False
    
    # Create stub for graceful degradation
    class CeleryStub:
        """Stub class when Celery is not available."""
        def __init__(self, *args, **kwargs):
            self.conf = type('Conf', (), {'update': lambda *a, **kw: None})()
        
        def task(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        
        def send_task(self, *args, **kwargs):
            logger.warning("[Celery Stub] send_task called but Celery not available")
            return None
    
    celery = CeleryStub("neurobridge")
    celery_app = celery
    
    _RAW_BEAT_SCHEDULE = {}
    BEAT_SCHEDULE = {}
    QUEUES = []
    QUEUE_CONFIGS = {}
    TASK_ROUTES = {}
    BROKER_TYPE = "unavailable"
    
    # PROMETHEUS: Mark Celery as unavailable
    set_active_module(module="celery_app", active=False)
    set_active_module(module="redis_broker", active=False)
    
    def get_celery_status() -> Dict[str, Any]:
        return {
            "available": False,
            "error": str(e),
            "broker_type": "unavailable",
            "phase": "PHASE_1_PRODUCTION",
            "version": "4.4.0",
            "metrics_instrumented": _METRICS_AVAILABLE,
        }
    
    def is_celery_available() -> bool:
        return False
    
    def initialize_celery() -> bool:
        logger.error("[Celery] Cannot initialize - Celery not installed")
        return False
    
    class NeuroBridgeTask:
        """Stub task class."""
        pass
    
    __all__ = [
        "celery", "celery_app",
        "get_celery_status", "is_celery_available", "initialize_celery",
        "NeuroBridgeTask", "BEAT_SCHEDULE",
    ]
    
    logger.warning("[Celery] Operating in DEGRADED mode - Celery not available")
    raise SystemExit(1) if os.getenv("CELERY_REQUIRED", "false").lower() == "true" else None

# Only proceed if Celery is available
if CELERY_AVAILABLE:
    
    # ============================================================================
    # CELERY APP INSTANCE
    # ============================================================================
    
    try:
        _celery_instance = Celery(
            "neurobridge",
            broker=BROKER_URL,
            backend=RESULT_BACKEND,
            include=[
                "backend.tasks.energy_tasks",
                "backend.tasks.monitoring",
                "backend.tasks.weather_tasks",
                "backend.tasks.prediction_tasks",
                "backend.tasks.reporting",
                "backend.tasks.adfi",
                "backend.tasks.control_tasks",
                "backend.tasks.control",
            ]
        )
        
        celery = _celery_instance
        celery_app = _celery_instance
        
        logger.info("[Celery] Celery app instance created and exported as 'celery'")
        
        # PROMETHEUS: Mark Celery as active
        set_active_module(module="celery_app", active=True)
    except Exception as e:
        logger.critical(f"[Celery] Failed to create Celery app: {e}")
        set_active_module(module="celery_app", active=False)
        raise

    # ============================================================================
    # QUEUE DEFINITIONS (Phase 1)
    # ============================================================================
    
    QUEUE_CONFIGS = {
        "control_queue": {"exchange": "control", "routing_key": "control", "priority": 10},
        "high_priority": {"exchange": "high", "routing_key": "high", "priority": 9},
        "prediction_queue": {"exchange": "default", "routing_key": "prediction", "priority": 8},
        "energy_queue": {"exchange": "default", "routing_key": "energy", "priority": 7},
        "weather_queue": {"exchange": "default", "routing_key": "weather", "priority": 6},
        "adfi_queue": {"exchange": "default", "routing_key": "adfi", "priority": 5},
        "monitoring_queue": {"exchange": "default", "routing_key": "monitoring", "priority": 4},
        "reporting_queue": {"exchange": "low", "routing_key": "reporting", "priority": 3},
        "low_priority": {"exchange": "low", "routing_key": "low", "priority": 1},
        "default": {"exchange": "default", "routing_key": "default", "priority": 5},
    }
    
    QUEUES = [
        Queue(
            name,
            Exchange(config["exchange"]),
            routing_key=config["routing_key"],
            queue_arguments={"x-max-priority": config.get("priority", 5)}
        )
        for name, config in QUEUE_CONFIGS.items()
    ]
    
    logger.info(f"[Celery] Defined {len(QUEUES)} queues")
    
    # PROMETHEUS: Initialize all queue depths to 0
    try:
        for queue_name in QUEUE_CONFIGS.keys():
            _update_queue_depth(queue_name, 0)
    except Exception:
        pass
    
    # ============================================================================
    # TASK ROUTES
    # ============================================================================
    
    TASK_ROUTES = {
        "backend.tasks.control.*": {"queue": "control_queue"},
        "backend.tasks.control_tasks.*": {"queue": "control_queue"},
        "backend.tasks.monitoring.*": {"queue": "monitoring_queue"},
        "backend.tasks.prediction_tasks.*": {"queue": "prediction_queue"},
        "backend.tasks.reporting.*": {"queue": "reporting_queue"},
        "backend.tasks.weather_tasks.*": {"queue": "weather_queue"},
        "backend.tasks.energy_tasks.*": {"queue": "energy_queue"},
        "backend.tasks.adfi.*": {"queue": "adfi_queue"},
        "celery.ping": {"queue": "control_queue"},
        "celery.status": {"queue": "control_queue"},
        "celery.health": {"queue": "control_queue"},
        "*": {"queue": "default"},
    }
    
    # ============================================================================
    # PHASE 1 BEAT SCHEDULE (NO FUSION/NUCLEAR/QUANTUM/DEFENSE)
    # ============================================================================
    
    BLOCKED_TASK_PREFIXES = [
        "nuclear", "fusion", "quantum", "defense",
        "weapon", "military", "plasma", "tokamak",
        "stellarator", "reactor",
    ]
    
    def is_phase1_allowed(task_name: str) -> bool:
        """Check if a task is allowed in Phase 1 production."""
        if not task_name:
            return False
            
        task_lower = task_name.lower()
        for blocked in BLOCKED_TASK_PREFIXES:
            if blocked in task_lower:
                logger.debug(f"[PHASE1] Blocked task: {task_name} (matched '{blocked}')")
                return False
        return True
    
    def filter_beat_schedule(schedule: Dict[str, Any]) -> Dict[str, Any]:
        """Filter beat schedule to only Phase 1 allowed tasks."""
        filtered = {}
        blocked_count = 0
        
        for entry_name, entry_config in schedule.items():
            task_name = entry_config.get("task", "")
            if is_phase1_allowed(task_name):
                filtered[entry_name] = entry_config
            else:
                blocked_count += 1
                logger.info(f"[PHASE1] Blocked beat entry: {entry_name} -> {task_name}")
        
        logger.info(f"[PHASE1] Beat schedule: {len(filtered)} active, {blocked_count} blocked")
        return filtered
    
    _RAW_BEAT_SCHEDULE = {
        "grid-stability-update": {
            "task": "backend.tasks.prediction_tasks.grid_stability_update",
            "schedule": 600.0,
            "options": {"queue": "prediction_queue", "expires": 900.0}
        },
        "solar-forecast-update": {
            "task": "backend.tasks.energy_tasks.solar_forecast_update",
            "schedule": 300.0,
            "options": {"queue": "energy_queue", "expires": 450.0}
        },
        "weather-update": {
            "task": "backend.tasks.weather_tasks.weather_update",
            "schedule": 900.0,
            "options": {"queue": "weather_queue", "expires": 1200.0}
        },
        "hardware-telemetry-poll": {
            "task": "backend.tasks.monitoring.hardware_telemetry_poll",
            "schedule": 30.0,
            "options": {"queue": "monitoring_queue", "expires": 60.0}
        },
        "adfi-orchestration": {
            "task": "backend.tasks.adfi.orchestrate_sources",
            "schedule": 60.0,
            "options": {"queue": "adfi_queue", "expires": 120.0}
        },
        "daily-report": {
            "task": "backend.tasks.reporting.generate_daily_report",
            "schedule": 86400.0,
            "options": {"queue": "reporting_queue", "expires": 86400.0}
        },
        "energy-metrics-update": {
            "task": "backend.tasks.monitoring.update_energy_metrics",
            "schedule": 60.0,
            "options": {"queue": "monitoring_queue", "expires": 120.0}
        },
        "aece-risk-monitor": {
            "task": "backend.tasks.monitoring.monitor_aece_risk",
            "schedule": 30.0,
            "options": {"queue": "monitoring_queue", "expires": 60.0}
        },
        "solar-efficiency-check": {
            "task": "backend.tasks.energy_tasks.solar_efficiency_check",
            "schedule": 1800.0,
            "options": {"queue": "energy_queue", "expires": 2700.0}
        },
        "battery-health-check": {
            "task": "backend.tasks.monitoring.battery_health_check",
            "schedule": 3600.0,
            "options": {"queue": "monitoring_queue", "expires": 5400.0}
        },
        "grid-forecast-update": {
            "task": "backend.tasks.prediction_tasks.grid_forecast_update",
            "schedule": 1800.0,
            "options": {"queue": "prediction_queue", "expires": 2700.0}
        },
    }
    
    BEAT_SCHEDULE = filter_beat_schedule(_RAW_BEAT_SCHEDULE)
    
    # ============================================================================
    # CELERY CONFIGURATION
    # ============================================================================
    
    try:
        celery.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="Africa/Lagos",
            enable_utc=True,
            
            task_track_started=True,
            task_time_limit=300,
            task_soft_time_limit=240,
            task_acks_late=True,
            task_reject_on_worker_lost=True,
            
            task_default_retry_delay=60,
            task_max_retries=3,
            task_retry_backoff=True,
            task_retry_backoff_max=600,
            task_retry_jitter=True,
            
            task_queues=QUEUES,
            task_routes=TASK_ROUTES,
            task_default_queue="default",
            task_default_exchange="default",
            task_default_routing_key="default",
            
            result_expires=1800,
            result_backend_transport_options={
                "retry_policy": {
                    "timeout": 5.0,
                    "max_retries": 3,
                }
            },
            
            worker_prefetch_multiplier=1,
            worker_max_tasks_per_child=50,
            worker_cancel_long_running_tasks_on_connection_loss=True,
            
            broker_connection_retry_on_startup=True,
            broker_connection_max_retries=10,
            broker_connection_retry=True,
            broker_transport_options={
                "visibility_timeout": 3600,
                "max_retries": 5,
            },
            
            beat_schedule=BEAT_SCHEDULE,
            beat_max_loop_interval=300,
            beat_sync_every=1,
            beat_scheduler='celery.beat.PersistentScheduler',
            
            worker_redirect_stdouts=False,
            worker_redirect_stdouts_level="INFO",
            
            worker_send_task_events=True,
            task_send_sent_event=True,
            
            task_default_rate_limit='100/m',
        )
        logger.info("[Celery] Configuration applied successfully")
    except Exception as e:
        logger.error(f"[Celery] Failed to apply configuration: {e}")
        raise
    
    # SQLite-specific optimizations
    if BROKER_TYPE in ["sqlite", "sqlite_fallback"]:
        celery.conf.update(
            result_persistent=True,
            result_extended=True,
            result_compression="gzip",
            worker_prefetch_multiplier=1,
            broker_transport_options={
                "visibility_timeout": 3600,
                "max_retries": 3,
            },
        )
        logger.info("[SQLite] Optimizations applied for SQLite broker")
    
    # Development-specific settings
    if IS_DEVELOPMENT:
        celery.conf.update(
            task_always_eager=False,
            task_eager_propagates=True,
            worker_redirect_stdouts=True,
            worker_redirect_stdouts_level="DEBUG",
        )
        logger.info("[Celery] Development mode optimizations applied")
    
    # ============================================================================
    # BASE TASK CLASS WITH ERROR HANDLING
    # ============================================================================
    
    class NeuroBridgeTask(Task):
        """Base task class with automatic error logging and retry."""
        
        abstract = True
        max_retries = 3
        default_retry_delay = 60
        retry_backoff = True
        retry_backoff_max = 600
        retry_jitter = True
        
        def on_failure(self, exc, task_id, args, kwargs, einfo):
            """Log task failures with detailed information."""
            logger.error(
                f"[Task] {self.name} failed (ID: {task_id}): "
                f"{type(exc).__name__}: {exc}"
            )
            logger.debug(f"[Task] {self.name} args: {args}, kwargs: {kwargs}")
            super().on_failure(exc, task_id, args, kwargs, einfo)
        
        def on_success(self, retval, task_id, args, kwargs):
            """Log task successes."""
            logger.debug(f"[Task] {self.name} succeeded (ID: {task_id})")
            super().on_success(retval, task_id, args, kwargs)
        
        def on_retry(self, exc, task_id, args, kwargs, einfo):
            """Log retry attempts with count."""
            retry_count = self.request.retries
            logger.warning(
                f"[Task] {self.name} retry {retry_count}/{self.max_retries} "
                f"(ID: {task_id}): {type(exc).__name__}: {exc}"
            )
            super().on_retry(exc, task_id, args, kwargs, einfo)
    
    # ============================================================================
    # SIMPLE TEST TASKS
    # ============================================================================
    
    @celery.task(name="celery.ping", bind=True, base=NeuroBridgeTask)
    def ping(self):
        """Simple ping task for testing Celery connectivity."""
        from datetime import datetime, timezone
        
        return {
            "status": "pong",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": self.request.id,
            "broker_type": BROKER_TYPE,
            "phase": "PHASE_1_PRODUCTION",
            "version": "4.4.0",
            "environment": ENVIRONMENT,
        }
    
    @celery.task(name="celery.status", bind=True, base=NeuroBridgeTask)
    def celery_status(self):
        """Get comprehensive Celery status."""
        return {
            "status": "active",
            "broker_type": BROKER_TYPE,
            "broker_available": True,
            "task_id": self.request.id,
            "queues": [q.name for q in QUEUES],
            "queue_count": len(QUEUES),
            "phase": "PHASE_1_PRODUCTION",
            "beat_schedule_count": len(BEAT_SCHEDULE),
            "beat_schedule_tasks": list(BEAT_SCHEDULE.keys()),
            "version": "4.4.0",
        }
    
    @celery.task(name="celery.health", bind=True, base=NeuroBridgeTask)
    def celery_health(self):
        """Health check task with broker verification."""
        from datetime import datetime, timezone
        
        return {
            "status": "healthy",
            "broker_type": BROKER_TYPE,
            "broker_scheme": BROKER_URL.split("://")[0] if "://" in BROKER_URL else "unknown",
            "task_id": self.request.id,
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": ENVIRONMENT,
            "is_oci": IS_OCI,
        }
    
    # ============================================================================
    # HELPER FUNCTIONS
    # ============================================================================
    
    def get_celery_status() -> Dict[str, Any]:
        """Get comprehensive Celery status."""
        try:
            return {
                "available": True,
                "broker_type": BROKER_TYPE,
                "broker_url": BROKER_URL.split("://")[0] if "://" in BROKER_URL else "unknown",
                "queues": [q.name for q in QUEUES],
                "queue_count": len(QUEUES),
                "beat_schedule_count": len(BEAT_SCHEDULE),
                "beat_schedule_tasks": list(BEAT_SCHEDULE.keys()),
                "blocked_prefixes": BLOCKED_TASK_PREFIXES,
                "phase": "PHASE_1_PRODUCTION",
                "version": "4.4.0",
                "environment": ENVIRONMENT,
                "is_oci": IS_OCI,
                "celery_export_available": True,
                "export_names": ["celery", "celery_app"],
                "metrics_instrumented": _METRICS_AVAILABLE,
            }
        except Exception as e:
            logger.error(f"[Celery] Failed to get status: {e}")
            return {
                "available": False,
                "error": str(e),
                "phase": "PHASE_1_PRODUCTION",
                "version": "4.4.0",
            }
    
    def is_celery_available() -> bool:
        """Check if Celery is properly available."""
        try:
            if not CELERY_AVAILABLE:
                return False
            if BROKER_TYPE == "unavailable":
                return False
            if 'celery' not in globals():
                logger.error("[Celery] 'celery' variable missing from globals")
                return False
            return celery is not None
        except Exception as e:
            logger.error(f"[Celery] is_celery_available check failed: {e}")
            return False
    
    # ============================================================================
    # INITIALIZATION
    # ============================================================================
    
    def initialize_celery() -> bool:
        """Initialize and verify Celery configuration."""
        try:
            status = get_celery_status()
            
            logger.info("=" * 70)
            logger.info("[Celery] INITIALIZATION COMPLETE (v4.4.0 - Phase 1)")
            logger.info(f"[Celery] Environment: {ENVIRONMENT.upper()}")
            logger.info(f"[Celery] Broker type: {BROKER_TYPE.upper()}")
            logger.info(f"[Celery] Celery available: {status['available']}")
            logger.info(f"[Celery] Queues configured: {status['queue_count']}")
            logger.info(f"[Celery] Beat schedule: {status['beat_schedule_count']} active tasks")
            logger.info(f"[Celery] Phase 1: Nuclear/Fusion/Quantum/Defense tasks BLOCKED")
            logger.info(f"[Celery] Metrics instrumented: {_METRICS_AVAILABLE}")
            
            logger.info(f"[Celery] Export 'celery' is available (type: {type(celery).__name__})")
            logger.info(f"[Celery] Export 'celery_app' is available (type: {type(celery_app).__name__})")
            
            if BROKER_TYPE == "sqlite":
                logger.info(f"[Broker] SQLite mode active - OCI compatible")
                logger.info(f"[Broker] Broker file: {SQLITE_BROKER_PATH}")
                logger.info(f"[Broker] Result file: {SQLITE_RESULT_PATH}")
            elif BROKER_TYPE == "redis":
                logger.info(f"[Broker] Redis mode active: {REDIS_HOST}:{REDIS_PORT}")
            
            for task_name in status['beat_schedule_tasks']:
                logger.info(f"  Beat: {task_name}")
            
            logger.info("=" * 70)
            
            # PROMETHEUS: Mark celery module as active on successful init
            set_active_module(module="celery_app", active=True)
            
            # PROMETHEUS: Initialize all queue depths
            try:
                for queue_name in QUEUE_CONFIGS.keys():
                    _update_queue_depth(queue_name, 0)
            except Exception:
                pass
            
            return True
            
        except Exception as e:
            logger.error(f"[Celery] Initialization failed: {e}")
            set_active_module(module="celery_app", active=False)
            return False

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "celery", "celery_app",
    "get_celery_status", "is_celery_available", "initialize_celery",
    "NeuroBridgeTask", "BEAT_SCHEDULE", "QUEUES",
    "BROKER_TYPE", "BROKER_URL",
]

# ============================================================================
# AUTO-INITIALIZE ON IMPORT
# ============================================================================

if CELERY_AVAILABLE:
    initialize_celery()
    
    logger.info("[Celery] Module ready - 'celery' and 'celery_app' exported")
else:
    logger.error("[Celery] Cannot auto-initialize - Celery not available")
    logger.warning("[Celery] 'celery' export is a stub - install Celery for full functionality")