# backend/tasks/adfi.py - PRODUCTION CLEAN v4.1.0
# ADFI Celery Tasks - Phase 1 Compliant
# Prometheus Metrics Instrumented - ADFI Observability & Source Health

import asyncio
import logging
import time
import json
import secrets
import uuid
import random
import threading
import traceback
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

# CRITICAL FIX: Use shared_task instead of celery_app
from celery import shared_task, Task, chain, group, chord

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

try:
    from backend.monitoring.prometheus_metrics import (
        record_adfi_ingestion,
        record_adfi_cycle,
        set_adfi_source_health,
        record_adfi_pipeline_latency,
        record_aece_decision,
        set_emergency_stop_state,
        set_grid_stability_index,
        set_solar_efficiency_score,
        record_grid_risk_event,
        set_active_module,
        set_celery_queue_depth,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    # Null fallbacks for graceful degradation
    def record_adfi_ingestion(*args, **kwargs): pass
    def record_adfi_cycle(*args, **kwargs): pass
    def set_adfi_source_health(*args, **kwargs): pass
    def record_adfi_pipeline_latency(*args, **kwargs): pass
    def record_aece_decision(*args, **kwargs): pass
    def set_emergency_stop_state(*args, **kwargs): pass
    def set_grid_stability_index(*args, **kwargs): pass
    def set_solar_efficiency_score(*args, **kwargs): pass
    def record_grid_risk_event(*args, **kwargs): pass
    def set_active_module(*args, **kwargs): pass
    def set_celery_queue_depth(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[ADFI_TASKS] prometheus metrics instrumented")
else:
    logger.debug("[ADFI_TASKS] prometheus metrics unavailable - running without instrumentation")

# ============================================================================
# INDEPENDENT KERNEL LOADER (NO IMPORTS FROM BACKEND.MAIN)
# ============================================================================

_kernel_loader = None
_physics_engine = None
_aece_engine = None
_services_available = False
_metrics_available = False
_aece_available = False

_kernel_lock = threading.RLock()


def _get_kernel_loader():
    """Lazy load kernel loader to avoid circular imports"""
    global _kernel_loader, _services_available
    
    if _kernel_loader is not None:
        return _kernel_loader
    
    with _kernel_lock:
        if _kernel_loader is not None:
            return _kernel_loader
        
        try:
            # Try multiple possible import paths for kernel loader
            try:
                from backend.kernel_loader import kernel_loader as _kl
                _kernel_loader = _kl
                _services_available = True
                logger.debug("[ADFI] Kernel loader loaded from backend.kernel_loader")
            except ImportError:
                try:
                    from backend.main import kernel_loader as _kl
                    _kernel_loader = _kl
                    _services_available = True
                    logger.debug("[ADFI] Kernel loader loaded from backend.main (fallback)")
                except ImportError:
                    # Create a minimal fallback kernel loader
                    class _MinimalKernel:
                        def is_native(self):
                            return False
                        def calculate_yield_ergotropy(self, input_energy, entropy_loss):
                            return input_energy * 1.08
                        def get_kernel_info(self):
                            return {"performance_mode": "SIMULATED"}
                    _kernel_loader = _MinimalKernel()
                    _services_available = False
                    logger.debug("[ADFI] Using minimal fallback kernel loader")
        except ImportError as e:
            logger.debug(f"[ADFI] Kernel loader not available: {e}")
            _services_available = False
        except Exception as e:
            logger.warning(f"[ADFI] Failed to load kernel: {e}")
            _services_available = False
        
        return _kernel_loader


def _get_physics_engine():
    """
    Lazy load physics engine to avoid circular imports.
    
    FIXED: Removed direct import from backend.main
    """
    global _physics_engine
    
    if _physics_engine is not None:
        return _physics_engine
    
    with _kernel_lock:
        if _physics_engine is not None:
            return _physics_engine
        
        try:
            # Try multiple possible import paths for physics engine
            try:
                from backend.physics_engine import physics_engine as _pe
                _physics_engine = _pe
                logger.debug("[ADFI] Physics engine loaded from backend.physics_engine")
            except ImportError:
                try:
                    from backend.main import physics_engine as _pe
                    _physics_engine = _pe
                    logger.debug("[ADFI] Physics engine loaded from backend.main (fallback)")
                except ImportError:
                    # Create a minimal fallback physics engine
                    class _MinimalPhysics:
                        def calculate_structural_stability(self, sector, yield_value, hardware_data=None):
                            return 95.0
                        def calculate_manifold_integrity(self, sector, entropy=0.05):
                            return 0.92
                    _physics_engine = _MinimalPhysics()
                    logger.debug("[ADFI] Using minimal fallback physics engine")
        except ImportError as e:
            logger.debug(f"[ADFI] Physics engine not available: {e}")
        except Exception as e:
            logger.warning(f"[ADFI] Failed to load physics engine: {e}")
        
        return _physics_engine


def _get_aece_engine():
    """Lazy load AECE engine to avoid circular imports"""
    global _aece_engine, _aece_available
    
    if _aece_engine is not None:
        return _aece_engine
    
    with _kernel_lock:
        if _aece_engine is not None:
            return _aece_engine
        
        try:
            from backend.control.aece_engine import aece as _ae
            _aece_engine = _ae
            _aece_available = True
            logger.debug("[ADFI] AECE engine loaded")
        except ImportError as e:
            logger.debug(f"[ADFI] AECE engine not available: {e}")
            _aece_available = False
        except Exception as e:
            logger.warning(f"[ADFI] Failed to load AECE engine: {e}")
            _aece_available = False
        
        return _aece_engine


def _get_metrics():
    """Lazy load metrics to avoid circular imports"""
    global _metrics_available
    
    if _metrics_available:
        try:
            from backend.monitoring.prometheus_metrics import (
                metrics, record_aece_action, update_aece_risk_score,
                record_grid_risk_event
            )
            return {
                "metrics": metrics,
                "record_aece_action": record_aece_action,
                "update_aece_risk_score": update_aece_risk_score,
                "record_grid_risk_event": record_grid_risk_event
            }
        except ImportError:
            _metrics_available = False
            return None
        except Exception:
            return None
    
    return None


def _get_cache_service():
    """Lazy load cache service to avoid circular imports"""
    try:
        from backend.services.cache_service import cache_service
        return cache_service
    except ImportError:
        return None
    except Exception:
        return None


# ============================================================================
# ENUMS AND DATA MODELS
# ============================================================================

class InjectionStatus(str, Enum):
    """Injection task status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AnomalyType(str, Enum):
    """Anomaly detection types"""
    HIGH_YIELD = "high_yield_anomaly"
    LOW_YIELD = "low_yield_anomaly"
    EFFICIENCY_SPIKE = "efficiency_spike"
    PATTERN_DEVIATION = "pattern_deviation"
    FREQUENCY_ANOMALY = "frequency_anomaly"


@dataclass
class InjectionResult:
    """Single injection result"""
    injection_id: str
    input_energy: float
    quantum_yield: float
    gain_percent: float
    success: bool
    aece_risk_score: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "injection_id": self.injection_id,
            "input_energy": round(self.input_energy, 2),
            "quantum_yield": round(self.quantum_yield, 2),
            "gain_percent": round(self.gain_percent, 2),
            "success": self.success,
            "aece_risk_score": round(self.aece_risk_score, 3),
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "timestamp": self.timestamp
        }


@dataclass
class PatternAnalysis:
    """Pattern analysis results"""
    daily_peak: Optional[Dict[str, Any]]
    efficiency_trend: float
    anomalies: List[Dict[str, Any]]
    trend_direction: str  # increasing, decreasing, stable
    confidence_score: float
    aece_recommendation: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "daily_peak": self.daily_peak,
            "efficiency_trend": round(self.efficiency_trend, 2),
            "anomalies": self.anomalies,
            "trend_direction": self.trend_direction,
            "confidence_score": round(self.confidence_score, 2),
            "aece_recommendation": self.aece_recommendation
        }


# ============================================================================
# CIRCUIT BREAKER FOR ADFI TASKS
# ============================================================================

class ADFICircuitBreaker:
    """Circuit breaker pattern for ADFI tasks"""
    
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.RLock()
        self.total_failures = 0
        self.total_successes = 0
    
    def can_execute(self) -> bool:
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info(f"[ACB] {self.name} -> HALF_OPEN")
                    return True
                return False
            return True
    
    def record_success(self):
        with self._lock:
            self.total_successes += 1
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"[ACB] {self.name} -> CLOSED (recovered)")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"[ACB] {self.name} -> OPEN after {self.failure_count} failures")
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.total_successes + self.total_failures
            success_rate = round(self.total_successes / total * 100, 1) if total > 0 else 100.0
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "success_rate": success_rate
            }


# Circuit breakers for ADFI tasks
_adfi_circuit_breakers = {
    "injection": ADFICircuitBreaker("injection_batch", failure_threshold=5, recovery_timeout=60),
    "pattern": ADFICircuitBreaker("pattern_analysis", failure_threshold=3, recovery_timeout=90),
    "scenario": ADFICircuitBreaker("scenario_generation", failure_threshold=3, recovery_timeout=60),
}


# ============================================================================
# DEAD LETTER QUEUE FOR ADFI
# ============================================================================

class ADFIDeadLetterQueue:
    """Persistent storage for failed ADFI tasks"""
    
    def __init__(self, max_size: int = 5000):
        self._queue = []
        self._max_size = max_size
        self._lock = threading.RLock()
    
    def add(self, task_name: str, args: Dict, error: str, trace: str):
        with self._lock:
            entry = {
                "task_name": task_name,
                "args": args,
                "error": error[:500] if error else "",
                "traceback": trace[:500] if trace else "",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self._queue.append(entry)
            if len(self._queue) > self._max_size:
                self._queue.pop(0)
            logger.error(f"[ADLQ] Added {task_name}: {error[:100] if error else 'Unknown error'}")
    
    def get_all(self) -> List[Dict]:
        with self._lock:
            return self._queue.copy()
    
    def clear(self):
        with self._lock:
            self._queue.clear()
    
    def size(self) -> int:
        with self._lock:
            return len(self._queue)
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._queue),
                "max_size": self._max_size,
                "utilization_percent": round(len(self._queue) / self._max_size * 100, 1) if self._max_size > 0 else 0
            }


_adfi_dlq = ADFIDeadLetterQueue()


# ============================================================================
# TASK BASE CLASS
# ============================================================================

class ADFITaskBase(Task):
    """Base class for ADFI tasks with enhanced error handling"""
    abstract = True
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure with DLQ and metrics."""
        logger.error(f"ADFI task {self.name} failed: {exc}")
        
        # Add to dead letter queue
        _adfi_dlq.add(
            task_name=self.name,
            args={"args": str(args)[:200], "kwargs": str(kwargs)[:200]},
            error=str(exc),
            trace=einfo.traceback if einfo else ""
        )
        
        # PROMETHEUS: Mark source unhealthy on task failure
        set_adfi_source_health(source=f"celery_{self.name}", healthy=False)
        
        # Track failure in celery metrics
        try:
            if _METRICS_AVAILABLE and hasattr(metrics, 'celery_tasks_total'):
                metrics.celery_tasks_total.labels(
                    task_name=self.name,
                    status="failed",
                    queue="adfi_queue"
                ).inc()
        except Exception:
            pass
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success with metrics."""
        # PROMETHEUS: Mark source healthy on task success
        set_adfi_source_health(source=f"celery_{self.name}", healthy=True)
        
        # Track success in celery metrics
        try:
            if _METRICS_AVAILABLE and hasattr(metrics, 'celery_tasks_total'):
                metrics.celery_tasks_total.labels(
                    task_name=self.name,
                    status="success",
                    queue="adfi_queue"
                ).inc()
        except Exception:
            pass


# ============================================================================
# PROCESS INJECTION BATCH TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ADFITaskBase,
    name="backend.tasks.adfi.process_injection_batch",
    queue="adfi_queue",
    rate_limit="60/m",
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120
)
def process_injection_batch(
    self,
    injection_data: List[Dict[str, Any]],
    adjust_for_aece_risk: bool = True,
    sector: str = "renewables"
) -> Dict[str, Any]:
    """
    Process a batch of ADFI data injections with quantum yield calculation.
    
    Args:
        injection_data: List of injection data dictionaries
        adjust_for_aece_risk: Adjust injection based on AECE risk score
        sector: Energy sector for context
    
    Returns:
        Batch processing results with success/failure counts
    """
    start_time = time.time()
    batch_id = str(uuid.uuid4())
    total_injections = len(injection_data)
    
    logger.info(f"[ADFI] Processing injection batch {batch_id} | Count: {total_injections} | Sector: {sector}")
    
    # PROMETHEUS: Record ADFI cycle start
    record_adfi_cycle(source=f"celery_batch_{sector}", module="adfi_tasks")
    
    # Check circuit breaker
    cb = _adfi_circuit_breakers["injection"]
    if not cb.can_execute():
        set_adfi_source_health(source="celery_injection_batch", healthy=False)
        return {
            "success": False,
            "batch_id": batch_id,
            "error": "Circuit breaker OPEN",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    # Get AECE risk for adjustment
    aece_risk = 0.15
    if adjust_for_aece_risk:
        aece_engine = _get_aece_engine()
        if aece_engine:
            try:
                aece_status = aece_engine.get_status() if hasattr(aece_engine, 'get_status') else {}
                aece_risk = aece_status.get("metrics", {}).get("avg_risk_score", 0.15)
            except Exception as e:
                logger.debug(f"Failed to get AECE risk: {e}")
    
    # Get kernel for quantum calculations
    kernel = _get_kernel_loader()
    
    results = []
    successful = 0
    failed = 0
    total_gain = 0.0
    total_yield = 0.0
    
    for idx, data in enumerate(injection_data):
        injection_start = time.time()
        
        try:
            # Extract data with defaults
            energy_input = data.get("energy_kw", 100.0)
            entropy = data.get("entropy_loss", 0.05)
            
            # Apply AECE risk adjustment
            if adjust_for_aece_risk and aece_risk > 0.3:
                adjustment = 1 - (aece_risk * 0.1)
                energy_input = energy_input * adjustment
            
            # Calculate quantum yield using lazy-loaded kernel
            if kernel:
                try:
                    quantum_yield = kernel.calculate_yield_ergotropy(energy_input, entropy)
                except Exception:
                    quantum_yield = energy_input * (1 + (1 - entropy) * 0.3)
            else:
                quantum_yield = energy_input * (1 + (1 - entropy) * 0.3)
            
            gain_percent = ((quantum_yield - energy_input) / energy_input) * 100 if energy_input > 0 else 0
            
            injection_latency = time.time() - injection_start
            
            result = InjectionResult(
                injection_id=str(uuid.uuid4()),
                input_energy=energy_input,
                quantum_yield=quantum_yield,
                gain_percent=gain_percent,
                success=True,
                aece_risk_score=aece_risk,
                duration_ms=injection_latency * 1000
            )
            results.append(result.to_dict())
            successful += 1
            total_gain += gain_percent
            total_yield += quantum_yield
            
            # PROMETHEUS: Record individual injection
            record_adfi_ingestion(
                source=f"celery_{sector}",
                packets=1,
                latency_seconds=injection_latency,
                module="adfi_injection_batch"
            )
            
        except Exception as e:
            failed += 1
            results.append({
                "injection_id": str(uuid.uuid4()),
                "input_energy": data.get("energy_kw", 100.0),
                "error": str(e),
                "success": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.error(f"[ADFI] Injection {idx} failed: {e}")
    
    avg_gain = total_gain / successful if successful > 0 else 0
    failure_rate = (failed / total_injections) * 100 if total_injections > 0 else 0
    
    # PROMETHEUS: Record batch completion
    record_adfi_ingestion(
        source=f"celery_batch_{sector}",
        packets=successful,
        latency_seconds=time.time() - start_time,
        module="adfi_injection_batch"
    )
    
    # PROMETHEUS: Update source health based on success rate
    set_adfi_source_health(
        source=f"celery_{sector}",
        healthy=(failure_rate < 30)
    )
    
    # PROMETHEUS: Record AECE decision if high risk
    if aece_risk > 0.5:
        record_aece_decision(
            action="adfi_injection_adjust",
            risk_score=aece_risk,
            gsi=None,
            ses=None,
            module="adfi_tasks"
        )
    
    # Cache batch results
    cache_service = _get_cache_service()
    if cache_service:
        try:
            batch_result = {
                "batch_id": batch_id,
                "sector": sector,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_injections": total_injections,
                "successful": successful,
                "failed": failed,
                "avg_gain_percent": round(avg_gain, 2),
                "total_yield_mwh": round(total_yield, 2),
                "aece_risk_score": round(aece_risk, 3),
                "results": results[-20:]  # Store last 20 results
            }
            if hasattr(cache_service, 'set'):
                cache_service.set(f"adfi:batch:{batch_id}", batch_result, ttl=3600)
            elif hasattr(cache_service, 'sync_set'):
                cache_service.sync_set(f"adfi:batch:{batch_id}", batch_result, 3600)
        except Exception as e:
            logger.debug(f"Cache set failed: {e}")
    
    # Update legacy metrics
    metrics_obj = _get_metrics()
    if metrics_obj and aece_risk > 0.6:
        try:
            metrics_obj.get("record_aece_action", lambda **k: None)(action="adfi_injection", priority="high")
        except Exception:
            pass
    
    # Trigger AECE alert if failure rate is high
    if failure_rate > 30:
        try:
            record_grid_risk_event("high")
        except Exception:
            pass
    
    cb.record_success()
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(f"[ADFI] Batch {batch_id} completed | Success: {successful}/{total_injections} | Avg Gain: {avg_gain:.1f}% | Duration: {duration_ms:.0f}ms")
    
    return {
        "success": True,
        "batch_id": batch_id,
        "sector": sector,
        "total_injections": total_injections,
        "successful": successful,
        "failed": failed,
        "success_rate": round((successful / total_injections) * 100, 1) if total_injections > 0 else 0,
        "avg_gain_percent": round(avg_gain, 2),
        "total_yield_mwh": round(total_yield, 2),
        "aece_risk_score": round(aece_risk, 3),
        "results": results,
        "duration_ms": round(duration_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# ANALYZE PATTERNS TASK - FIXED: Uses lazy loader for physics_engine
# ============================================================================

@shared_task(
    bind=True,
    base=ADFITaskBase,
    name="backend.tasks.adfi.analyze_patterns",
    queue="adfi_queue",
    rate_limit="30/h",
    max_retries=2,
    default_retry_delay=30
)
def analyze_patterns(
    self,
    historical_data: List[Dict[str, Any]],
    lookback_hours: int = 24,
    detect_anomalies: bool = True
) -> Dict[str, Any]:
    """
    Analyze patterns in historical ADFI data with advanced statistics.
    
    FIXED: Uses lazy loader for physics_engine to avoid circular imports.
    
    Args:
        historical_data: List of historical injection data
        lookback_hours: Hours of data to analyze
        detect_anomalies: Enable anomaly detection
    
    Returns:
        Pattern analysis with trends, peaks, and anomalies
    """
    start_time = time.time()
    analysis_id = str(uuid.uuid4())
    
    logger.info(f"[ADFI] Analyzing patterns | Data points: {len(historical_data)} | Lookback: {lookback_hours}h")
    
    cb = _adfi_circuit_breakers["pattern"]
    if not cb.can_execute():
        set_adfi_source_health(source="celery_pattern_analysis", healthy=False)
        return {
            "success": False,
            "analysis_id": analysis_id,
            "error": "Circuit breaker OPEN",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    try:
        if not historical_data:
            set_adfi_source_health(source="celery_pattern_analysis", healthy=True)
            return {
                "success": True,
                "analysis_id": analysis_id,
                "patterns": {
                    "daily_peak": None,
                    "efficiency_trend": 0,
                    "anomalies": [],
                    "trend_direction": "stable",
                    "confidence_score": 0.5
                },
                "data_points_analyzed": 0,
                "message": "No historical data provided",
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
        
        patterns = {}
        anomalies = []
        
        # Extract yields and gains
        yields = [y.get("quantum_yield", 0) for y in historical_data if y.get("quantum_yield")]
        gains = [g.get("gain_percent", 0) for g in historical_data if g.get("gain_percent")]
        
        if yields:
            # Find peak yield
            peak_idx = yields.index(max(yields))
            peak_entry = historical_data[peak_idx] if peak_idx < len(historical_data) else {}
            patterns["daily_peak"] = {
                "timestamp": peak_entry.get("timestamp"),
                "value": round(max(yields), 2),
                "gain_percent": peak_entry.get("gain_percent", 0)
            }
            
            # Calculate statistics
            mean_yield = sum(yields) / len(yields)
            variance = sum((y - mean_yield) ** 2 for y in yields) / len(yields)
            std_dev = variance ** 0.5
            
            # Detect anomalies
            if detect_anomalies:
                for i, entry in enumerate(historical_data):
                    yield_val = entry.get("quantum_yield", 0)
                    gain_val = entry.get("gain_percent", 0)
                    
                    # High yield anomaly ( > 2 std dev)
                    if yield_val > mean_yield + 2 * std_dev:
                        anomalies.append({
                            "index": i,
                            "timestamp": entry.get("timestamp"),
                            "value": round(yield_val, 2),
                            "type": AnomalyType.HIGH_YIELD.value,
                            "severity": "high"
                        })
                    # Low yield anomaly ( < 2 std dev below mean)
                    elif yield_val < mean_yield - 2 * std_dev:
                        anomalies.append({
                            "index": i,
                            "timestamp": entry.get("timestamp"),
                            "value": round(yield_val, 2),
                            "type": AnomalyType.LOW_YIELD.value,
                            "severity": "medium"
                        })
                    
                    # Efficiency spike anomaly
                    if gain_val > 15:
                        anomalies.append({
                            "index": i,
                            "timestamp": entry.get("timestamp"),
                            "value": round(gain_val, 2),
                            "type": AnomalyType.EFFICIENCY_SPIKE.value,
                            "severity": "high"
                        })
        
        # Calculate efficiency trend
        efficiency_trend = 0
        trend_direction = "stable"
        
        if len(gains) >= 2:
            # Simple linear regression for trend
            x = list(range(len(gains)))
            slope = np.polyfit(x, gains, 1)[0] if len(gains) > 1 else 0
            efficiency_trend = round(slope, 2)
            
            if slope > 0.1:
                trend_direction = "increasing"
            elif slope < -0.1:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"
        
        avg_efficiency = sum(gains) / len(gains) if gains else 0
        
        # Generate AECE recommendation based on patterns
        aece_recommendation = None
        if len(anomalies) > 3:
            aece_recommendation = "Multiple anomalies detected. Review injection parameters."
            record_grid_risk_event("medium")
        elif efficiency_trend < -0.5:
            aece_recommendation = "Efficiency trend decreasing. Optimize quantum parameters."
        elif avg_efficiency < 5:
            aece_recommendation = "Low average efficiency. Consider recalibration."
        
        # PROMETHEUS: Record pipeline latency for analysis
        analysis_latency = time.time() - start_time
        record_adfi_pipeline_latency(
            source="celery_pattern_analysis",
            latency_seconds=analysis_latency,
            module="adfi_tasks"
        )
        
        # Cache analysis results
        cache_service = _get_cache_service()
        if cache_service:
            try:
                analysis_result = {
                    "analysis_id": analysis_id,
                    "patterns": patterns,
                    "anomalies": anomalies,
                    "trend_direction": trend_direction,
                    "efficiency_trend": efficiency_trend,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                if hasattr(cache_service, 'set'):
                    cache_service.set(f"adfi:analysis:{analysis_id}", analysis_result, ttl=3600)
                elif hasattr(cache_service, 'sync_set'):
                    cache_service.sync_set(f"adfi:analysis:{analysis_id}", analysis_result, 3600)
            except Exception as e:
                logger.debug(f"Cache set failed: {e}")
        
        cb.record_success()
        set_adfi_source_health(source="celery_pattern_analysis", healthy=True)
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"[ADFI] Pattern analysis complete | Peak: {patterns.get('daily_peak', {}).get('value', 0)} | Anomalies: {len(anomalies)} | Trend: {trend_direction}")
        
        return {
            "success": True,
            "analysis_id": analysis_id,
            "patterns": {
                "daily_peak": patterns.get("daily_peak"),
                "efficiency_trend": round(efficiency_trend, 2),
                "anomalies": anomalies,
                "trend_direction": trend_direction,
                "confidence_score": round(0.9 - (len(anomalies) * 0.05), 2),
                "aece_recommendation": aece_recommendation
            },
            "statistics": {
                "data_points_analyzed": len(historical_data),
                "avg_yield": round(sum(yields) / len(yields), 2) if yields else 0,
                "avg_gain_percent": round(avg_efficiency, 2),
                "max_yield": round(max(yields), 2) if yields else 0,
                "min_yield": round(min(yields), 2) if yields else 0,
                "std_dev_yield": round(std_dev, 2) if yields else 0,
                "anomaly_count": len(anomalies)
            },
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[ADFI] Pattern analysis failed: {e}")
        cb.record_failure()
        set_adfi_source_health(source="celery_pattern_analysis", healthy=False)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return {
            "success": False,
            "analysis_id": analysis_id,
            "error": str(e),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# GENERATE TEST SCENARIOS TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ADFITaskBase,
    name="backend.tasks.adfi.generate_test_scenarios",
    queue="adfi_queue",
    rate_limit="60/h",
    max_retries=2
)
def generate_test_scenarios(
    self,
    sector: str = "renewables",
    count: int = 10,
    include_edge_cases: bool = True,
    include_quantum_patterns: bool = True
) -> Dict[str, Any]:
    """
    Generate test scenarios for ADFI testing with realistic patterns.
    
    Args:
        sector: Energy sector for scenarios
        count: Number of scenarios to generate
        include_edge_cases: Include edge case scenarios
        include_quantum_patterns: Include quantum-enhanced patterns
    
    Returns:
        List of generated test scenarios
    """
    start_time = time.time()
    generation_id = str(uuid.uuid4())
    
    logger.info(f"[ADFI] Generating {count} test scenarios | Sector: {sector} | Edge cases: {include_edge_cases}")
    
    cb = _adfi_circuit_breakers["scenario"]
    if not cb.can_execute():
        set_adfi_source_health(source="celery_scenario_gen", healthy=False)
        return {
            "success": False,
            "generation_id": generation_id,
            "error": "Circuit breaker OPEN",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    try:
        scenarios = []
        
        # Sector-specific base values
        sector_base = {
            "renewables": {"energy_range": (80, 180), "entropy_range": (0.02, 0.08)},
            "oil_gas": {"energy_range": (100, 200), "entropy_range": (0.04, 0.12)},
            "grid_storage": {"energy_range": (60, 160), "entropy_range": (0.01, 0.06)},
            "quantum_optimization": {"energy_range": (120, 250), "entropy_range": (0.01, 0.05)},
            "defense": {"energy_range": (90, 190), "entropy_range": (0.03, 0.10)},
            "nuclear": {"energy_range": (150, 300), "entropy_range": (0.01, 0.04)}
        }.get(sector, {"energy_range": (80, 180), "entropy_range": (0.02, 0.08)})
        
        energy_min, energy_max = sector_base["energy_range"]
        entropy_min, entropy_max = sector_base["entropy_range"]
        
        for i in range(count):
            # Base scenario
            energy = random.uniform(energy_min, energy_max)
            entropy = random.uniform(entropy_min, entropy_max)
            
            scenario = {
                "id": str(uuid.uuid4()),
                "sector": sector,
                "energy_kw": round(energy, 1),
                "entropy_loss": round(entropy, 3),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "test_index": i + 1,
                "scenario_type": "normal"
            }
            
            # Add edge cases
            if include_edge_cases:
                if i == count // 3:  # Low energy edge case
                    scenario["energy_kw"] = round(energy_min * 0.5, 1)
                    scenario["scenario_type"] = "edge_low_energy"
                elif i == count // 2:  # High entropy edge case
                    scenario["entropy_loss"] = round(entropy_max * 1.2, 3)
                    scenario["scenario_type"] = "edge_high_entropy"
                elif i == count * 2 // 3:  # Zero entropy edge case
                    scenario["entropy_loss"] = 0.0
                    scenario["scenario_type"] = "edge_zero_entropy"
            
            # Add quantum patterns
            if include_quantum_patterns and i % 3 == 0:
                scenario["quantum_enhanced"] = True
                scenario["pattern_type"] = random.choice(["sine", "spike", "drift", "oscillation"])
            
            scenarios.append(scenario)
        
        # PROMETHEUS: Record scenario generation
        generation_latency = time.time() - start_time
        record_adfi_ingestion(
            source=f"celery_scenario_{sector}",
            packets=count,
            latency_seconds=generation_latency,
            module="adfi_scenario_gen"
        )
        
        # Cache generated scenarios
        cache_service = _get_cache_service()
        if cache_service:
            try:
                scenarios_data = {
                    "generation_id": generation_id,
                    "sector": sector,
                    "count": count,
                    "scenarios": scenarios,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                if hasattr(cache_service, 'set'):
                    cache_service.set(f"adfi:scenarios:{generation_id}", scenarios_data, ttl=3600)
                elif hasattr(cache_service, 'sync_set'):
                    cache_service.sync_set(f"adfi:scenarios:{generation_id}", scenarios_data, 3600)
            except Exception as e:
                logger.debug(f"Cache set failed: {e}")
        
        cb.record_success()
        set_adfi_source_health(source="celery_scenario_gen", healthy=True)
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"[ADFI] Generated {count} scenarios for {sector} in {duration_ms:.0f}ms")
        
        return {
            "success": True,
            "generation_id": generation_id,
            "sector": sector,
            "scenarios_generated": count,
            "edge_cases_included": include_edge_cases,
            "quantum_patterns_included": include_quantum_patterns,
            "scenarios": scenarios,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[ADFI] Scenario generation failed: {e}")
        cb.record_failure()
        set_adfi_source_health(source="celery_scenario_gen", healthy=False)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return {
            "success": False,
            "generation_id": generation_id,
            "error": str(e),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# REAL-TIME PATTERN MONITORING TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ADFITaskBase,
    name="backend.tasks.adfi.monitor_real_time_patterns",
    queue="adfi_queue",
    rate_limit="120/h",
    max_retries=2
)
def monitor_real_time_patterns(
    self,
    sector: str = "renewables",
    window_minutes: int = 60
) -> Dict[str, Any]:
    """
    Real-time pattern monitoring for live injection data.
    
    Args:
        sector: Energy sector to monitor
        window_minutes: Monitoring window in minutes
    
    Returns:
        Real-time pattern insights and alerts
    """
    start_time = time.time()
    monitor_id = str(uuid.uuid4())
    
    logger.info(f"[ADFI] Real-time monitoring for {sector} | Window: {window_minutes}min")
    
    try:
        # Get recent injection history
        recent_injections = []
        cache_service = _get_cache_service()
        if cache_service:
            try:
                # Get recent batches
                if hasattr(cache_service, 'get'):
                    recent_batches = cache_service.get("adfi:recent_batches") or []
                elif hasattr(cache_service, 'sync_get'):
                    recent_batches = cache_service.sync_get("adfi:recent_batches") or []
                else:
                    recent_batches = []
                    
                for batch_id in recent_batches[-10:]:  # Last 10 batches
                    if hasattr(cache_service, 'get'):
                        batch = cache_service.get(f"adfi:batch:{batch_id}")
                    elif hasattr(cache_service, 'sync_get'):
                        batch = cache_service.sync_get(f"adfi:batch:{batch_id}")
                    else:
                        batch = None
                        
                    if batch and batch.get("sector") == sector:
                        recent_injections.extend(batch.get("results", []))
            except Exception as e:
                logger.debug(f"Cache read failed: {e}")
        
        if not recent_injections:
            set_adfi_source_health(source="celery_realtime_monitor", healthy=True)
            return {
                "success": True,
                "monitor_id": monitor_id,
                "sector": sector,
                "status": "no_data",
                "message": "No recent injection data available",
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
        
        # Calculate real-time metrics
        yields = [r.get("quantum_yield", 0) for r in recent_injections if r.get("success")]
        gains = [r.get("gain_percent", 0) for r in recent_injections if r.get("success")]
        
        avg_yield = sum(yields) / len(yields) if yields else 0
        avg_gain = sum(gains) / len(gains) if gains else 0
        success_rate = sum(1 for r in recent_injections if r.get("success")) / len(recent_injections) * 100 if recent_injections else 0
        
        # Detect anomalies in real-time
        anomalies = []
        if len(yields) >= 10:
            mean = sum(yields) / len(yields)
            std_dev = (sum((y - mean) ** 2 for y in yields) / len(yields)) ** 0.5
            
            for r in recent_injections[-5:]:  # Check last 5 injections
                if r.get("success") and r.get("quantum_yield", 0) > mean + 2 * std_dev:
                    anomalies.append({
                        "injection_id": r.get("injection_id"),
                        "value": r.get("quantum_yield"),
                        "deviation": round((r.get("quantum_yield") - mean) / std_dev, 2),
                        "type": "high_yield_anomaly"
                    })
        
        # PROMETHEUS: Record monitoring event
        monitor_latency = time.time() - start_time
        record_adfi_ingestion(
            source=f"celery_monitor_{sector}",
            packets=len(recent_injections),
            latency_seconds=monitor_latency,
            module="adfi_realtime_monitor"
        )
        
        # Generate real-time alert if anomalies detected
        if len(anomalies) > 2:
            try:
                record_grid_risk_event("medium")
            except Exception:
                pass
        
        # Update source health
        set_adfi_source_health(
            source="celery_realtime_monitor",
            healthy=(success_rate > 70)
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"[ADFI] Real-time monitoring | Success rate: {success_rate:.0f}% | Anomalies: {len(anomalies)}")
        
        return {
            "success": True,
            "monitor_id": monitor_id,
            "sector": sector,
            "status": "active",
            "metrics": {
                "avg_yield": round(avg_yield, 2),
                "avg_gain_percent": round(avg_gain, 2),
                "success_rate_percent": round(success_rate, 1),
                "samples_analyzed": len(recent_injections),
                "anomalies_detected": len(anomalies)
            },
            "anomalies": anomalies,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[ADFI] Real-time monitoring failed: {e}")
        set_adfi_source_health(source="celery_realtime_monitor", healthy=False)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return {
            "success": False,
            "monitor_id": monitor_id,
            "error": str(e),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# DEAD LETTER QUEUE MANAGEMENT
# ============================================================================

@shared_task(name="backend.tasks.adfi.get_adfi_dlq")
def get_adfi_dlq() -> Dict[str, Any]:
    """Get the current ADFI dead letter queue contents"""
    return {
        "success": True,
        "queue_stats": _adfi_dlq.get_stats(),
        "entries": _adfi_dlq.get_all()[-50:],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.adfi.clear_adfi_dlq")
def clear_adfi_dlq() -> Dict[str, Any]:
    """Clear the ADFI dead letter queue"""
    _adfi_dlq.clear()
    return {
        "success": True,
        "message": "ADFI dead letter queue cleared",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.adfi.get_adfi_metrics")
def get_adfi_metrics() -> Dict[str, Any]:
    """Get metrics for all ADFI tasks"""
    return {
        "success": True,
        "circuit_breakers": {
            name: cb.get_stats()
            for name, cb in _adfi_circuit_breakers.items()
        },
        "dead_letter_queue": _adfi_dlq.get_stats(),
        "prometheus_instrumented": _METRICS_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# HEALTH CHECK TASK
# ============================================================================

@shared_task(name="backend.tasks.adfi.adfi_health_check")
def adfi_health_check() -> Dict[str, Any]:
    """
    Health check for ADFI tasks system.
    """
    kernel = _get_kernel_loader()
    physics = _get_physics_engine()
    aece = _get_aece_engine()
    cache = _get_cache_service()
    
    services_healthy = all([kernel, physics, aece])
    
    # PROMETHEUS: Update source health based on service availability
    set_adfi_source_health(source="adfi_kernel", healthy=kernel is not None)
    set_adfi_source_health(source="adfi_physics", healthy=physics is not None)
    set_adfi_source_health(source="adfi_aece", healthy=aece is not None)
    set_adfi_source_health(source="adfi_cache", healthy=cache is not None)
    set_active_module(module="adfi_tasks", active=services_healthy)
    
    return {
        "success": True,
        "status": "healthy" if services_healthy else "degraded",
        "circuit_breakers_status": {
            name: cb.state for name, cb in _adfi_circuit_breakers.items()
        },
        "dead_letter_queue_size": _adfi_dlq.size(),
        "services_available": {
            "kernel": kernel is not None,
            "physics": physics is not None,
            "aece": aece is not None,
            "cache": cache is not None,
            "metrics": _METRICS_AVAILABLE
        },
        "prometheus_instrumented": _METRICS_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Main tasks
    'process_injection_batch',
    'analyze_patterns',
    'generate_test_scenarios',
    'monitor_real_time_patterns',
    
    # Dead letter queue
    'get_adfi_dlq',
    'clear_adfi_dlq',
    'get_adfi_metrics',
    
    # Health check
    'adfi_health_check',
    
    # Enums
    'InjectionStatus',
    'AnomalyType',
    'InjectionResult',
    'PatternAnalysis'
]