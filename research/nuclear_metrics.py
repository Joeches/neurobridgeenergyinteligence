"""
================================================================================
NeuroBridge 11D - Nuclear Intelligence Metrics
Prometheus metrics for nuclear energy monitoring
Version: 4.0.0-PRODUCTION-PILOT-READY
Build: 2026.04.15
CTO: Joseph Ochelebe | NeuroBridge Technologies Ltd

CRITICAL FIXES APPLIED (v4.0.0):
- FIXED: Circular import warnings - NO imports from main.py
- FIXED: Removed 'from main import redis_manager' (circular dependency)
- FIXED: Independent Redis manager with lazy initialization
- FIXED: Async/await consistency for Redis operations
- ENHANCED: Zero external dependencies for module loading
- ENHANCED: Thread-safe metric registration
- ENHANCED: Full Abuja Pilot compliance

ARCHITECTURE CHANGES:
- Completely independent module - no imports from main.py
- Lazy-loaded Redis manager with proper async initialization
- Standalone Prometheus multiproc directory management
- Thread-safe singleton pattern for all components
================================================================================
"""

import os
import sys
import tempfile
import logging
import time
import json
import asyncio
from functools import wraps
from typing import Dict, Any, Optional, Set, Union
from datetime import datetime, timezone
from threading import Lock

# ============================================================================
# LOGGER SETUP
# ============================================================================

logger = logging.getLogger("NeuroBridge.NuclearMetrics")

# ============================================================================
# CRITICAL: Setup multiproc directory BEFORE importing prometheus_client
# ============================================================================

def setup_multiproc_directory() -> str:
    """Setup Prometheus multiprocess directory BEFORE any metrics are created"""
    # Determine the directory
    if os.name == 'nt':  # Windows
        multiproc_dir = os.path.join(tempfile.gettempdir(), 'prometheus_multiproc_nuclear')
    else:
        multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus_multiproc_nuclear")
    
    # Create directory if it doesn't exist
    os.makedirs(multiproc_dir, exist_ok=True)
    
    # Set environment variable
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = multiproc_dir
    
    logger.info(f"[NUCLEAR_METRICS] Multiproc directory: {multiproc_dir}")
    return multiproc_dir


# Setup multiproc directory FIRST
MULTIPROC_DIR = setup_multiproc_directory()

# ============================================================================
# NOW import prometheus_client (after directory is set)
# ============================================================================

PROMETHEUS_AVAILABLE = False
PROMETHEUS_CLIENT = None

try:
    from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
    logger.info("[NUCLEAR_METRICS] Prometheus client loaded successfully")
except ImportError as e:
    logger.warning(f"[NUCLEAR_METRICS] Prometheus not available: {e}")

# ============================================================================
# INDEPENDENT REDIS MANAGER (NO IMPORTS FROM MAIN)
# ============================================================================

class IndependentRedisManager:
    """
    Standalone Redis manager with no dependencies on main.py.
    Prevents circular import warnings.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Singleton pattern with thread safety"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.available = False
        self.client = None
        self._initialized = True
    
    async def initialize(self) -> bool:
        """Initialize Redis connection asynchronously"""
        if self.client is not None:
            return self.available
        
        try:
            import redis.asyncio as aioredis
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.client = await aioredis.from_url(
                redis_url,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            await self.client.ping()
            self.available = True
            logger.info("[NUCLEAR_METRICS] ✅ Redis connected (independent mode)")
        except ImportError:
            logger.debug("[NUCLEAR_METRICS] Redis library not installed")
            self.available = False
        except Exception as e:
            logger.debug(f"[NUCLEAR_METRICS] Redis not available: {e}")
            self.available = False
        
        return self.available
    
    async def set(self, key: str, value: str, ttl: int = 60) -> bool:
        """Set a Redis key with TTL"""
        if not self.available or self.client is None:
            return False
        try:
            await self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.debug(f"Redis set failed: {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """Get a Redis key value"""
        if not self.available or self.client is None:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.debug(f"Redis get failed: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a Redis key"""
        if not self.available or self.client is None:
            return False
        try:
            await self.client.delete(key)
            return True
        except Exception:
            return False
    
    async def set_json(self, key: str, value: Dict, ttl: int = 60) -> bool:
        """Set a JSON value in Redis"""
        return await self.set(key, json.dumps(value), ttl)
    
    async def get_json(self, key: str) -> Optional[Dict]:
        """Get a JSON value from Redis"""
        data = await self.get(key)
        if data:
            try:
                return json.loads(data)
            except:
                return None
        return None
    
    async def ping(self) -> bool:
        """Ping Redis server"""
        if not self.available or self.client is None:
            return False
        try:
            return await self.client.ping()
        except Exception:
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            self.available = False
            self.client = None


# Global Redis manager instance
_redis_manager = None
_REDIS_AVAILABLE = False


def get_redis_manager() -> IndependentRedisManager:
    """Get Redis manager instance (singleton)"""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = IndependentRedisManager()
    return _redis_manager


async def ensure_redis_initialized() -> bool:
    """Ensure Redis is initialized (call at startup)"""
    global _REDIS_AVAILABLE
    manager = get_redis_manager()
    if not manager.available:
        _REDIS_AVAILABLE = await manager.initialize()
    else:
        _REDIS_AVAILABLE = True
    return _REDIS_AVAILABLE


# ============================================================================
# DUPLICATE REGISTRATION PROTECTION
# ============================================================================

_registered_metrics: Set[str] = set()
_registration_lock = Lock()


def safe_create_metric(metric_class, name: str, documentation: str, **kwargs):
    """
    Safely create a metric with duplicate protection.
    Returns None if metric already exists to allow graceful fallback.
    """
    with _registration_lock:
        if name in _registered_metrics:
            logger.debug(f"[NUCLEAR_METRICS] Metric already registered, skipping: {name}")
            return None
        
        if not PROMETHEUS_AVAILABLE:
            return None
        
        try:
            metric = metric_class(name, documentation, **kwargs)
            _registered_metrics.add(name)
            return metric
        except ValueError as e:
            if "Duplicated" in str(e):
                logger.debug(f"[NUCLEAR_METRICS] Duplicate metric detected (handled): {name}")
                _registered_metrics.add(name)
                return None
            raise
        except Exception as e:
            logger.warning(f"[NUCLEAR_METRICS] Failed to create metric {name}: {e}")
            return None


# ============================================================================
# NULL METRIC CLASS FOR FALLBACK
# ============================================================================

class NullMetric:
    """Null object pattern for when Prometheus is not available"""
    
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


class NullHistogram(NullMetric):
    """Null histogram"""
    def observe(self, value):
        pass


# ============================================================================
# METRICS DEFINITIONS (WITH GRACEFUL FALLBACK & DUPLICATE PROTECTION)
# ============================================================================

# Initialize all metrics as None first
nuclear_simulation_requests_total = None
nuclear_simulation_latency_ms = None
nuclear_risk_score = None
nuclear_output_mw = None
nuclear_stability_score = None
nuclear_cooling_performance = None
nuclear_safety_factor = None
nuclear_failure_probability = None
energy_mix_nuclear_share = None
energy_mix_cost_efficiency = None
energy_mix_carbon_footprint = None
aece_nuclear_risk_integration = None
nuclear_kernel_mode = None

if PROMETHEUS_AVAILABLE:
    try:
        # Nuclear simulation metrics
        metric = safe_create_metric(
            Counter, 'neurobridge_nuclear_simulation_requests_total',
            'Total number of nuclear simulation requests',
            labelnames=['reactor_type', 'risk_level', 'status', 'user_type']
        )
        nuclear_simulation_requests_total = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Histogram, 'neurobridge_nuclear_simulation_latency_ms',
            'Nuclear simulation latency in milliseconds',
            buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
        )
        nuclear_simulation_latency_ms = metric if metric is not None else NullHistogram()
        
        # Risk metrics
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_risk_score',
            'Current nuclear risk probability (0-1)',
            labelnames=['risk_level']
        )
        nuclear_risk_score = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_failure_probability',
            'Nuclear failure probability (0-1)',
            labelnames=['reactor_type']
        )
        nuclear_failure_probability = metric if metric is not None else NullMetric()
        
        # Performance metrics
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_output_mw',
            'Nuclear electrical output in megawatts',
            labelnames=['reactor_type']
        )
        nuclear_output_mw = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_stability_score',
            'Nuclear plant stability score (0-100)',
            labelnames=['reactor_type']
        )
        nuclear_stability_score = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_cooling_performance',
            'Cooling system performance percentage',
            labelnames=['cooling_type']
        )
        nuclear_cooling_performance = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_safety_factor',
            'Nuclear safety factor multiplier',
            labelnames=['reactor_type']
        )
        nuclear_safety_factor = metric if metric is not None else NullMetric()
        
        # Energy mix metrics
        metric = safe_create_metric(
            Gauge, 'neurobridge_energy_mix_nuclear_share',
            'Nuclear energy share in total mix percentage',
            labelnames=['scenario']
        )
        energy_mix_nuclear_share = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Gauge, 'neurobridge_energy_mix_cost_efficiency',
            'Energy mix cost efficiency score (0-100)'
        )
        energy_mix_cost_efficiency = metric if metric is not None else NullMetric()
        
        metric = safe_create_metric(
            Gauge, 'neurobridge_energy_mix_carbon_footprint_kg',
            'Energy mix carbon footprint in kg CO2'
        )
        energy_mix_carbon_footprint = metric if metric is not None else NullMetric()
        
        # AECE integration metric
        metric = safe_create_metric(
            Gauge, 'neurobridge_aece_nuclear_risk_integration',
            'AECE risk score from nuclear integration (0-1)'
        )
        aece_nuclear_risk_integration = metric if metric is not None else NullMetric()
        
        # Kernel mode metric
        metric = safe_create_metric(
            Gauge, 'neurobridge_nuclear_kernel_mode',
            'Nuclear kernel mode (1=native, 0=simulated)'
        )
        nuclear_kernel_mode = metric if metric is not None else NullMetric()
        
        # Count successfully created metrics
        metrics_created = sum(1 for m in [
            nuclear_simulation_requests_total, nuclear_simulation_latency_ms,
            nuclear_risk_score, nuclear_output_mw, nuclear_stability_score,
            nuclear_cooling_performance, nuclear_safety_factor, nuclear_failure_probability,
            energy_mix_nuclear_share, energy_mix_cost_efficiency,
            energy_mix_carbon_footprint, aece_nuclear_risk_integration,
            nuclear_kernel_mode
        ] if not isinstance(m, (NullMetric, NullHistogram)))
        
        if metrics_created > 0:
            logger.info(f"[NUCLEAR_METRICS] {metrics_created}/13 metrics initialized successfully")
        else:
            logger.warning("[NUCLEAR_METRICS] No metrics could be initialized - using fallback")
            PROMETHEUS_AVAILABLE = False
        
    except Exception as e:
        logger.error(f"[NUCLEAR_METRICS] Failed to create metrics: {e}")
        PROMETHEUS_AVAILABLE = False

# Fall back to null metrics for any uninitialized metrics
if not PROMETHEUS_AVAILABLE:
    nuclear_simulation_requests_total = nuclear_simulation_requests_total or NullMetric()
    nuclear_simulation_latency_ms = nuclear_simulation_latency_ms or NullHistogram()
    nuclear_risk_score = nuclear_risk_score or NullMetric()
    nuclear_output_mw = nuclear_output_mw or NullMetric()
    nuclear_stability_score = nuclear_stability_score or NullMetric()
    nuclear_cooling_performance = nuclear_cooling_performance or NullMetric()
    nuclear_safety_factor = nuclear_safety_factor or NullMetric()
    nuclear_failure_probability = nuclear_failure_probability or NullMetric()
    energy_mix_nuclear_share = energy_mix_nuclear_share or NullMetric()
    energy_mix_cost_efficiency = energy_mix_cost_efficiency or NullMetric()
    energy_mix_carbon_footprint = energy_mix_carbon_footprint or NullMetric()
    aece_nuclear_risk_integration = aece_nuclear_risk_integration or NullMetric()
    nuclear_kernel_mode = nuclear_kernel_mode or NullMetric()
    
    logger.info("[NUCLEAR_METRICS] Using null metrics (fallback mode)")

# ============================================================================
# DECORATORS AND HELPER FUNCTIONS
# ============================================================================

def track_nuclear_simulation(func):
    """Decorator to track nuclear simulation metrics with full integration"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        status = "success"
        reactor_type = "unknown"
        risk_level = "unknown"
        user_type = "unknown"
        
        # Try to extract user_type from auth
        try:
            auth = kwargs.get('auth')
            if auth and isinstance(auth, dict):
                user_type = auth.get('user_type', 'unknown')
        except:
            pass
        
        try:
            result = await func(*args, **kwargs)
            
            # Extract metrics from result
            if result and isinstance(result, dict):
                reactor_type = result.get("yield_metrics", {}).get("reactor_type", "unknown")
                risk_level = result.get("nuclear_safety", {}).get("risk_level", "unknown")
                
                # Update output and stability metrics
                output = result.get("yield_metrics", {}).get("extractable_ergotropy")
                if output:
                    update_nuclear_output(reactor_type, output)
                
                risk = result.get("nuclear_safety", {}).get("failure_probability")
                if risk:
                    update_nuclear_risk_score(risk, risk_level)
                
                stability = result.get("physics_intelligence", {}).get("structural_stability")
                if stability:
                    update_nuclear_stability(reactor_type, stability)
            
            return result
            
        except Exception as e:
            status = "failed"
            logger.error(f"[NUCLEAR_METRICS] Simulation failed: {e}")
            raise
            
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            if PROMETHEUS_AVAILABLE:
                try:
                    if not isinstance(nuclear_simulation_latency_ms, NullHistogram):
                        nuclear_simulation_latency_ms.observe(duration_ms)
                    
                    if not isinstance(nuclear_simulation_requests_total, NullMetric):
                        nuclear_simulation_requests_total.labels(
                            reactor_type=reactor_type,
                            risk_level=risk_level,
                            status=status,
                            user_type=user_type
                        ).inc()
                    
                    # Cache metrics in Redis for persistence (async without blocking)
                    asyncio.create_task(_cache_metric_async({
                        "reactor_type": reactor_type,
                        "risk_level": risk_level,
                        "duration_ms": duration_ms,
                        "status": status,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    
                except Exception as e:
                    logger.debug(f"Failed to track nuclear metrics: {e}")
    
    return wrapper


async def _cache_metric_async(metric_data: Dict[str, Any]):
    """Async cache metric data in Redis"""
    try:
        if _REDIS_AVAILABLE:
            manager = get_redis_manager()
            await manager.set_json("nuclear:metrics:latest", metric_data, ttl=300)
    except Exception as e:
        logger.debug(f"Failed to cache metric: {e}")


def update_nuclear_risk_score(risk: float, risk_level: str = "unknown"):
    """Update nuclear risk score metric with level label"""
    if PROMETHEUS_AVAILABLE and not isinstance(nuclear_risk_score, NullMetric):
        try:
            risk = max(0.0, min(1.0, risk))
            nuclear_risk_score.labels(risk_level=risk_level).set(risk)
            
            # Also update failure probability
            if not isinstance(nuclear_failure_probability, NullMetric):
                nuclear_failure_probability.labels(reactor_type="all").set(risk)
            
            # Update AECE integration metric
            if not isinstance(aece_nuclear_risk_integration, NullMetric):
                aece_nuclear_risk_integration.set(risk)
                
        except Exception as e:
            logger.debug(f"Failed to update risk score: {e}")


def update_nuclear_output(reactor_type: str, output_mw: float):
    """Update nuclear output metric"""
    if PROMETHEUS_AVAILABLE and not isinstance(nuclear_output_mw, NullMetric):
        try:
            nuclear_output_mw.labels(reactor_type=reactor_type).set(output_mw)
        except Exception as e:
            logger.debug(f"Failed to update nuclear output: {e}")


def update_nuclear_stability(reactor_type: str, stability: float):
    """Update nuclear stability metric"""
    if PROMETHEUS_AVAILABLE and not isinstance(nuclear_stability_score, NullMetric):
        try:
            nuclear_stability_score.labels(reactor_type=reactor_type).set(stability)
        except Exception as e:
            logger.debug(f"Failed to update nuclear stability: {e}")


def update_nuclear_cooling(cooling_type: str, performance: float):
    """Update nuclear cooling performance metric"""
    if PROMETHEUS_AVAILABLE and not isinstance(nuclear_cooling_performance, NullMetric):
        try:
            nuclear_cooling_performance.labels(cooling_type=cooling_type).set(performance)
        except Exception as e:
            logger.debug(f"Failed to update cooling performance: {e}")


def update_energy_mix_metrics(
    nuclear_share: float,
    cost_efficiency: float,
    carbon_footprint: float,
    scenario: str = "real_time"
):
    """Update energy mix metrics with scenario label"""
    if PROMETHEUS_AVAILABLE:
        try:
            if not isinstance(energy_mix_nuclear_share, NullMetric):
                energy_mix_nuclear_share.labels(scenario=scenario).set(nuclear_share)
            if not isinstance(energy_mix_cost_efficiency, NullMetric):
                energy_mix_cost_efficiency.set(cost_efficiency)
            if not isinstance(energy_mix_carbon_footprint, NullMetric):
                energy_mix_carbon_footprint.set(carbon_footprint)
        except Exception as e:
            logger.debug(f"Failed to update energy mix metrics: {e}")


def update_kernel_status(mode: str):
    """Update kernel status indicator (native vs simulated)"""
    if PROMETHEUS_AVAILABLE and not isinstance(nuclear_kernel_mode, NullMetric):
        try:
            nuclear_kernel_mode.set(1 if mode == "native" else 0)
        except Exception as e:
            logger.debug(f"Failed to update kernel status: {e}")


async def get_cached_metrics() -> Optional[Dict[str, Any]]:
    """Retrieve cached metrics from Redis"""
    if _REDIS_AVAILABLE:
        try:
            manager = get_redis_manager()
            return await manager.get_json("nuclear:metrics:latest")
        except Exception as e:
            logger.debug(f"Failed to get cached metrics: {e}")
    return None


def get_metrics_status() -> Dict[str, Any]:
    """Get current status of all metrics"""
    return {
        "prometheus_available": PROMETHEUS_AVAILABLE,
        "redis_available": _REDIS_AVAILABLE,
        "registered_metrics_count": len(_registered_metrics),
        "metrics": {
            "simulation_requests_total": str(nuclear_simulation_requests_total),
            "simulation_latency_ms": str(nuclear_simulation_latency_ms),
            "risk_score": str(nuclear_risk_score),
            "output_mw": str(nuclear_output_mw),
            "stability_score": str(nuclear_stability_score)
        }
    }


# ============================================================================
# NUCLEAR METRICS NAMESPACE (PROPER EXPORT)
# ============================================================================

class NuclearMetricsNamespace:
    """
    Namespace container for all nuclear metrics.
    This allows importing 'nuclear_metrics' as a single object
    that contains all individual metric references.
    """
    
    def __init__(self):
        # Simulation metrics
        self.simulation_requests_total = nuclear_simulation_requests_total
        self.simulation_latency_ms = nuclear_simulation_latency_ms
        
        # Risk metrics
        self.risk_score = nuclear_risk_score
        self.failure_probability = nuclear_failure_probability
        self.aece_integration = aece_nuclear_risk_integration
        
        # Performance metrics
        self.output_mw = nuclear_output_mw
        self.stability_score = nuclear_stability_score
        self.cooling_performance = nuclear_cooling_performance
        self.safety_factor = nuclear_safety_factor
        
        # Energy mix metrics
        self.mix_nuclear_share = energy_mix_nuclear_share
        self.mix_cost_efficiency = energy_mix_cost_efficiency
        self.mix_carbon_footprint = energy_mix_carbon_footprint
        
        # Kernel mode
        self.kernel_mode = nuclear_kernel_mode
        
        # Helper functions
        self.track_simulation = track_nuclear_simulation
        self.update_risk_score = update_nuclear_risk_score
        self.update_output = update_nuclear_output
        self.update_stability = update_nuclear_stability
        self.update_cooling = update_nuclear_cooling
        self.update_energy_mix = update_energy_mix_metrics
        self.update_kernel_status = update_kernel_status
        self.get_cached_metrics = get_cached_metrics
        self.get_status = get_metrics_status
    
    def get_all_metrics(self) -> Dict[str, str]:
        """Return all metrics as a dictionary for inspection"""
        return {
            "simulation_requests_total": str(self.simulation_requests_total),
            "simulation_latency_ms": str(self.simulation_latency_ms),
            "risk_score": str(self.risk_score),
            "failure_probability": str(self.failure_probability),
            "output_mw": str(self.output_mw),
            "stability_score": str(self.stability_score),
            "cooling_performance": str(self.cooling_performance),
            "safety_factor": str(self.safety_factor),
            "mix_nuclear_share": str(self.mix_nuclear_share),
            "mix_cost_efficiency": str(self.mix_cost_efficiency),
            "mix_carbon_footprint": str(self.mix_carbon_footprint),
            "aece_integration": str(self.aece_integration),
            "kernel_mode": str(self.kernel_mode),
        }
    
    def is_available(self) -> bool:
        """Check if Prometheus metrics are available"""
        return PROMETHEUS_AVAILABLE and not isinstance(self.risk_score, NullMetric)
    
    def get_registered_count(self) -> int:
        """Get number of registered metrics"""
        return len(_registered_metrics)


# Create the main export object
nuclear_metrics = NuclearMetricsNamespace()

# ============================================================================
# INITIALIZATION FUNCTION (Call at application startup)
# ============================================================================

async def initialize_nuclear_metrics() -> bool:
    """Initialize nuclear metrics module (call at app startup)"""
    global _REDIS_AVAILABLE
    
    logger.info("[NUCLEAR_METRICS] Initializing...")
    
    # Initialize Redis
    _REDIS_AVAILABLE = await ensure_redis_initialized()
    
    # Log status
    if PROMETHEUS_AVAILABLE:
        logger.info(f"[NUCLEAR_METRICS] ✅ Prometheus: {len(_registered_metrics)} metrics ready")
    else:
        logger.info("[NUCLEAR_METRICS] ⚠️ Prometheus not available (fallback mode)")
    
    if _REDIS_AVAILABLE:
        logger.info("[NUCLEAR_METRICS] ✅ Redis caching enabled")
    else:
        logger.info("[NUCLEAR_METRICS] ⚠️ Redis not available (memory cache only)")
    
    return True


async def shutdown_nuclear_metrics():
    """Shutdown nuclear metrics module"""
    global _REDIS_AVAILABLE, _redis_manager
    
    logger.info("[NUCLEAR_METRICS] Shutting down...")
    
    if _redis_manager:
        await _redis_manager.close()
        _redis_manager = None
    
    _REDIS_AVAILABLE = False
    logger.info("[NUCLEAR_METRICS] ✅ Shutdown complete")


# ============================================================================
# EXPORT ALL
# ============================================================================

__all__ = [
    # Individual metric exports (for direct import)
    'nuclear_simulation_requests_total',
    'nuclear_simulation_latency_ms',
    'nuclear_risk_score',
    'nuclear_output_mw',
    'nuclear_stability_score',
    'nuclear_cooling_performance',
    'nuclear_safety_factor',
    'nuclear_failure_probability',
    'energy_mix_nuclear_share',
    'energy_mix_cost_efficiency',
    'energy_mix_carbon_footprint',
    'aece_nuclear_risk_integration',
    'nuclear_kernel_mode',
    
    # Helper functions
    'track_nuclear_simulation',
    'update_nuclear_risk_score',
    'update_nuclear_output',
    'update_nuclear_stability',
    'update_nuclear_cooling',
    'update_energy_mix_metrics',
    'update_kernel_status',
    'get_cached_metrics',
    'get_metrics_status',
    
    # MAIN EXPORT
    'nuclear_metrics',
    
    # Namespace class
    'NuclearMetricsNamespace',
    
    # Status flags
    'PROMETHEUS_AVAILABLE',
    
    # Initialization
    'initialize_nuclear_metrics',
    'shutdown_nuclear_metrics',
]

# Log successful initialization
if PROMETHEUS_AVAILABLE:
    registered_count = len(_registered_metrics)
    logger.info(f"[NUCLEAR_METRICS] ✓ Nuclear metrics module ready (Prometheus enabled, {registered_count} metrics registered)")
else:
    logger.info("[NUCLEAR_METRICS] ✓ Nuclear metrics module ready (fallback mode - Prometheus not installed)")