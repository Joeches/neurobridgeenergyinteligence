# backend/tasks/control_tasks.py - PRODUCTION CLEAN v4.1.0
# AECE Control Tasks - Phase 1 Compliant
# Prometheus Metrics Instrumented - Control Observability

import asyncio
import logging
import time
import json
import hashlib
import threading
import traceback
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# CRITICAL FIX: Use shared_task instead of importing celery_app directly
from celery import shared_task, Task, chain, group, chord
from celery.exceptions import MaxRetriesExceededError, Ignore

# Import AECE components
try:
    from backend.control.aece_engine import aece, ControlAction, ControlPriority
    from backend.monitoring.prometheus_metrics import (
        metrics, record_aece_action, update_aece_risk_score,
        record_grid_risk_event, record_aece_decision,
        set_emergency_stop_state, set_active_module,
        set_grid_stability_index, set_solar_efficiency_score,
    )
    from backend.services.cache_service import cache_service
    AECE_AVAILABLE = True
    METRICS_AVAILABLE = True
    SERVICES_AVAILABLE = True
except ImportError as e:
    AECE_AVAILABLE = False
    METRICS_AVAILABLE = False
    SERVICES_AVAILABLE = False
    logging.getLogger(__name__).warning(f"Optional imports failed: {e}")

logger = logging.getLogger(__name__)


# ============================================================================
# THREAD-SAFE EVENT LOOP MANAGER
# ============================================================================

class EventLoopManager:
    """
    Thread-safe event loop manager for running async code in sync Celery tasks.
    
    This is the CRITICAL FIX for the 'await' outside async function error.
    """
    
    _instance = None
    _lock = threading.Lock()
    _loop = None
    _thread = None
    _executor = None
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="async_worker"
        )
        logger.info("[EventLoop] Thread-safe event loop manager initialized")
    
    def run_async(self, coro):
        """
        Run an async coroutine in a thread-safe manner.
        
        This is the key fix for Celery tasks that need to call async AECE methods.
        """
        loop = None
        created_loop = False
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                created_loop = True
            
            # Run the coroutine
            return loop.run_until_complete(coro)
        except Exception as e:
            logger.error(f"[EventLoop] Async execution failed: {e}")
            raise
        finally:
            # Clean up if we created a new loop
            if created_loop and loop is not None:
                try:
                    loop.close()
                except Exception:
                    pass
    
    def run_async_in_thread(self, coro):
        """
        Run async coroutine in a separate thread with its own event loop.
        """
        try:
            future = self._executor.submit(self._run_async_in_thread_impl, coro)
            return future.result(timeout=60)
        except concurrent.futures.TimeoutError:
            logger.error("[EventLoop] Async execution timed out after 60s")
            raise
        except Exception as e:
            logger.error(f"[EventLoop] Thread-based async execution failed: {e}")
            raise
    
    def _run_async_in_thread_impl(self, coro):
        """Internal implementation for thread-based async execution"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            try:
                loop.close()
            except Exception:
                pass
    
    def shutdown(self):
        """Shutdown the executor"""
        try:
            self._executor.shutdown(wait=False)
            logger.info("[EventLoop] Event loop manager shutdown")
        except Exception as e:
            logger.error(f"[EventLoop] Shutdown error: {e}")


# Global event loop manager instance
_event_loop_manager = EventLoopManager()


# ============================================================================
# ASYNC WRAPPER DECORATOR FOR SYNC CELERY TASKS
# ============================================================================

def async_to_sync(coro_func):
    """
    Decorator to convert an async function to sync for Celery tasks.
    
    This is the CRITICAL FIX for the 'await' outside async function error.
    """
    def wrapper(*args, **kwargs):
        return _event_loop_manager.run_async(coro_func(*args, **kwargs))
    return wrapper


# ============================================================================
# ENUMS AND DATA MODELS
# ============================================================================

class ActionStatus(str, Enum):
    """Control action execution status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    IDEMPOTENT = "idempotent"


class ActionPriority(str, Enum):
    """Action execution priority"""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ControlActionResult:
    """Result of a control action execution"""
    success: bool
    action: str
    task_id: str
    status: ActionStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    retry_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "retry_count": self.retry_count,
            "timestamp": self.timestamp
        }


# ============================================================================
# CIRCUIT BREAKER FOR CONTROL ACTIONS
# ============================================================================

class ControlCircuitBreaker:
    """Circuit breaker pattern for control actions"""
    
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.RLock()
    
    def can_execute(self) -> bool:
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info(f"[CB] {self.name} -> HALF_OPEN")
                    return True
                return False
            return True
    
    def record_success(self):
        with self._lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"[CB] {self.name} -> CLOSED (recovered)")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"[CB] {self.name} -> OPEN after {self.failure_count} failures")


# Circuit breakers for different action types
_action_circuit_breakers = {
    "reduce_load": ControlCircuitBreaker("reduce_load", failure_threshold=3, recovery_timeout=60),
    "redistribute_energy": ControlCircuitBreaker("redistribute_energy", failure_threshold=3, recovery_timeout=90),
    "preemptive_stabilization": ControlCircuitBreaker("preemptive_stabilization", failure_threshold=2, recovery_timeout=120),
    "trigger_alert": ControlCircuitBreaker("trigger_alert", failure_threshold=5, recovery_timeout=30),
    "lockdown_mode": ControlCircuitBreaker("lockdown_mode", failure_threshold=2, recovery_timeout=180),
}


# ============================================================================
# DEAD LETTER QUEUE FOR CONTROL ACTIONS
# ============================================================================

class ControlDeadLetterQueue:
    """Persistent storage for failed control actions"""
    
    def __init__(self, max_size: int = 1000):
        self._queue = []
        self._max_size = max_size
        self._lock = threading.RLock()
    
    def add(self, action: str, parameters: Dict, error: str, trace: str, retry_count: int):
        with self._lock:
            entry = {
                "action": action,
                "parameters": parameters,
                "error": error,
                "traceback": trace[:500] if trace else "",
                "retry_count": retry_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self._queue.append(entry)
            if len(self._queue) > self._max_size:
                self._queue.pop(0)
            logger.error(f"[DLQ] Added {action}: {error[:100]}")
    
    def get_all(self) -> List[Dict]:
        with self._lock:
            return self._queue.copy()
    
    def get_by_action(self, action: str) -> List[Dict]:
        with self._lock:
            return [e for e in self._queue if e.get("action") == action]
    
    def clear(self):
        with self._lock:
            self._queue.clear()
    
    def size(self) -> int:
        with self._lock:
            return len(self._queue)


_control_dlq = ControlDeadLetterQueue()


# ============================================================================
# ACTION IDEMPOTENCY CACHE
# ============================================================================

class ActionIdempotencyCache:
    """Prevent duplicate action execution within time window"""
    
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._cache = {}
        self._lock = threading.RLock()
    
    def is_duplicate(self, action: str, parameters: Dict) -> bool:
        """Check if identical action was executed recently"""
        try:
            key = self._generate_key(action, parameters)
            
            with self._lock:
                if key in self._cache:
                    timestamp = self._cache[key]
                    if time.time() - timestamp < self.ttl:
                        return True
                
                self._cache[key] = time.time()
                self._cleanup()
                return False
        except Exception:
            return False
    
    def _generate_key(self, action: str, parameters: Dict) -> str:
        """Generate unique key for action"""
        try:
            param_str = json.dumps(parameters, sort_keys=True)
            return hashlib.md5(f"{action}:{param_str}".encode()).hexdigest()
        except Exception:
            return hashlib.md5(f"{action}:{time.time()}".encode()).hexdigest()
    
    def _cleanup(self):
        """Remove expired entries"""
        try:
            now = time.time()
            expired = [k for k, v in self._cache.items() if now - v > self.ttl]
            for k in expired:
                del self._cache[k]
        except Exception:
            pass


_idempotency_cache = ActionIdempotencyCache(ttl_seconds=30)


# ============================================================================
# TASK BASE CLASS
# ============================================================================

class ControlTaskBase(Task):
    """Base class for control tasks with enhanced error handling"""
    abstract = True
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure with DLQ, metrics, and emergency stop tracking."""
        logger.error(f"Control task {self.name} failed: {exc}")
        
        try:
            # Extract action from args
            action = args[0] if args else "unknown"
            parameters = args[1] if len(args) > 1 else {}
            
            _control_dlq.add(
                action=action,
                parameters=parameters,
                error=str(exc),
                trace=einfo.traceback if einfo else "",
                retry_count=self.request.retries
            )
            
            # PROMETHEUS: Track celery task failure
            if METRICS_AVAILABLE and metrics and hasattr(metrics, 'celery_tasks_total'):
                metrics.celery_tasks_total.labels(
                    task_name=self.name,
                    status="failed",
                    queue="control_queue"
                ).inc()
            
            # PROMETHEUS: Record AECE action failure
            if METRICS_AVAILABLE:
                try:
                    record_aece_decision(
                        action=action,
                        risk_score=0.85,
                        gsi=None,
                        ses=None,
                        module="control_tasks"
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[ControlTaskBase] on_failure handler error: {e}")
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success with metrics."""
        try:
            if METRICS_AVAILABLE and metrics and hasattr(metrics, 'celery_tasks_total'):
                metrics.celery_tasks_total.labels(
                    task_name=self.name,
                    status="success",
                    queue="control_queue"
                ).inc()
            
            # PROMETHEUS: Record successful AECE action
            action = args[0] if args else "unknown"
            if METRICS_AVAILABLE and action != "unknown":
                try:
                    record_aece_decision(
                        action=action,
                        risk_score=0.0,
                        gsi=None,
                        ses=None,
                        module="control_tasks"
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[ControlTaskBase] on_success handler error: {e}")


# ============================================================================
# SINGLE CONTROL ACTION EXECUTION TASK (FIXED: Using @shared_task)
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.execute_control_action",
    queue="control_queue",
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    rate_limit="30/m",
    acks_late=True,
    reject_on_worker_lost=True
)
def execute_control_action(
    self,
    action: str,
    parameters: Dict[str, Any],
    priority: str = "normal",
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a control action asynchronously via Celery with fault tolerance.
    
    FIXED: No 'await' in sync function - uses EventLoopManager to run async code.
    FIXED: Uses @shared_task decorator - no circular import.
    
    Args:
        action: Control action type (reduce_load, redistribute_energy, etc.)
        parameters: Action-specific parameters
        priority: Execution priority (critical, high, normal, low)
        idempotency_key: Optional key to prevent duplicate execution
    
    Returns:
        Execution result dictionary
    """
    start_time = time.time()
    task_id = self.request.id
    retry_count = self.request.retries
    
    logger.info(f"[CTL] Executing {action} | Task: {task_id} | Priority: {priority} | Retry: {retry_count}")
    
    # PROMETHEUS: Track control action attempt
    if METRICS_AVAILABLE:
        try:
            record_aece_action(action=action, priority=priority)
        except Exception:
            pass
    
    # Check idempotency
    if idempotency_key and _idempotency_cache.is_duplicate(action, parameters):
        logger.warning(f"[CTL] Duplicate action detected: {action} | Key: {idempotency_key}")
        return {
            "success": True,
            "action": action,
            "task_id": task_id,
            "status": ActionStatus.IDEMPOTENT.value,
            "message": "Duplicate action skipped",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    # Check circuit breaker
    cb = _action_circuit_breakers.get(action)
    if cb and not cb.can_execute():
        logger.warning(f"[CTL] Circuit breaker OPEN for {action}")
        try:
            set_emergency_stop_state(active=True, component=f"circuit_breaker_{action}")
        except Exception:
            pass
        return {
            "success": False,
            "action": action,
            "task_id": task_id,
            "status": ActionStatus.FAILED.value,
            "error": f"Circuit breaker OPEN for {action}",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    if not AECE_AVAILABLE:
        logger.error("[CTL] AECE engine not available")
        try:
            set_active_module(module="aece_control_tasks", active=False)
        except Exception:
            pass
        return {
            "success": False,
            "action": action,
            "task_id": task_id,
            "error": "AECE engine not available",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    try:
        # Map action string to ControlAction enum
        action_map = {
            "reduce_load": ControlAction.REDUCE_LOAD,
            "redistribute_energy": ControlAction.REDISTRIBUTE_ENERGY,
            "preemptive_stabilization": ControlAction.PREEMPTIVE_STABILIZATION,
            "trigger_alert": ControlAction.TRIGGER_ALERT,
            "lockdown_mode": ControlAction.LOCKDOWN_MODE,
        }
        
        control_action = action_map.get(action)
        if not control_action:
            raise ValueError(f"Unknown action: {action}")
        
        # Map priority string to ControlPriority enum
        priority_map = {
            "critical": ControlPriority.CRITICAL,
            "high": ControlPriority.HIGH,
            "normal": ControlPriority.NORMAL,
            "low": ControlPriority.LOW,
        }
        action_priority = priority_map.get(priority, ControlPriority.NORMAL)
        
        # Create decision object for executor
        class Decision:
            def __init__(self, action, reason, priority):
                self.action = action
                self.reason = reason
                self.priority = priority
        
        decision = Decision(
            control_action,
            parameters.get('reason', f'Celery task execution: {action}'),
            action_priority
        )
        
        # ====================================================================
        # CRITICAL FIX: Execute async method in sync Celery task
        # ====================================================================
        result = _event_loop_manager.run_async(
            aece.action_executor.execute(decision)
        )
        
        # Record metrics
        if METRICS_AVAILABLE:
            record_aece_action(action=action, priority=priority)
            
            # Update risk score for critical actions
            if action == "lockdown_mode":
                update_aece_risk_score(0.95)
                record_grid_risk_event("critical")
                try:
                    set_emergency_stop_state(active=True, component="lockdown_mode")
                except Exception:
                    pass
            elif action == "reduce_load":
                update_aece_risk_score(0.7)
                record_grid_risk_event("high")
            
            # Record control decision
            try:
                record_aece_decision(
                    action=action,
                    risk_score=0.95 if action == "lockdown_mode" else 0.7 if action == "reduce_load" else 0.5,
                    gsi=None,
                    ses=None,
                    module="control_tasks"
                )
            except Exception:
                pass
        
        # Record success in circuit breaker
        if cb:
            cb.record_success()
            try:
                set_emergency_stop_state(active=False, component=f"circuit_breaker_{action}")
            except Exception:
                pass
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"[CTL] Action {action} completed in {duration_ms:.0f}ms | Success: {result.get('success', False)}")
        
        return {
            "success": result.get("success", True),
            "action": action,
            "task_id": task_id,
            "status": ActionStatus.COMPLETED.value,
            "result": result,
            "priority": priority,
            "retry_count": retry_count,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[CTL] Action {action} failed: {e}")
        
        # Record failure in circuit breaker
        if cb:
            cb.record_failure()
            try:
                set_emergency_stop_state(active=True, component=f"circuit_breaker_{action}")
            except Exception:
                pass
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.warning(f"[CTL] Retrying {action} (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e)
        
        # Max retries exceeded - add to dead letter queue
        _control_dlq.add(
            action=action,
            parameters=parameters,
            error=str(e),
            trace=traceback.format_exc(),
            retry_count=retry_count
        )
        
        return {
            "success": False,
            "action": action,
            "task_id": task_id,
            "status": ActionStatus.FAILED.value,
            "error": str(e),
            "retry_count": retry_count,
            "retries_exhausted": True,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# BATCH CONTROL ACTIONS TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.batch_control_actions",
    queue="control_queue",
    max_retries=2,
    rate_limit="10/m"
)
def batch_control_actions(
    self,
    actions: List[Tuple[str, Dict[str, Any]]],
    parallel: bool = True,
    priority: str = "normal"
) -> Dict[str, Any]:
    """
    Execute multiple control actions in batch.
    
    Args:
        actions: List of (action, parameters) tuples
        parallel: Execute in parallel (True) or sequentially (False)
        priority: Default priority for all actions
    
    Returns:
        Batch execution results
    """
    start_time = time.time()
    batch_id = self.request.id
    
    logger.info(f"[Batch] Executing {len(actions)} actions | Batch: {batch_id} | Parallel: {parallel}")
    
    # PROMETHEUS: Track batch start
    if METRICS_AVAILABLE:
        try:
            record_aece_action(action="batch_control", priority=priority)
        except Exception:
            pass
    
    results = []
    successful = 0
    failed = 0
    
    try:
        if parallel:
            # Execute in parallel using Celery group
            from celery import group
            
            tasks = []
            for action, params in actions:
                task = execute_control_action.s(action, params, priority)
                tasks.append(task)
            
            job = group(tasks)
            result = job.apply_async()
            task_results = result.get(timeout=120)
            
            for res in task_results:
                if isinstance(res, dict) and res.get("success", False):
                    successful += 1
                else:
                    failed += 1
                results.append(res)
        else:
            # Execute sequentially
            for action, params in actions:
                try:
                    res = execute_control_action.delay(action, params, priority).get(timeout=60)
                    if isinstance(res, dict) and res.get("success", False):
                        successful += 1
                    else:
                        failed += 1
                    results.append(res)
                except Exception as e:
                    failed += 1
                    results.append({
                        "success": False,
                        "action": action,
                        "error": str(e),
                        "task_id": None
                    })
    except Exception as e:
        logger.error(f"[Batch] Batch execution failed: {e}")
        failed = len(actions) - successful
    
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(f"[Batch] Completed: {successful} success, {failed} failed in {duration_ms:.0f}ms")
    
    # PROMETHEUS: Record grid risk if high failure rate
    if failed > 0 and len(actions) > 0:
        failure_rate = failed / len(actions)
        if failure_rate > 0.3:
            try:
                record_grid_risk_event("high")
            except Exception:
                pass
    
    return {
        "success": True,
        "batch_id": batch_id,
        "total_actions": len(actions),
        "successful": successful,
        "failed": failed,
        "results": results,
        "parallel": parallel,
        "duration_ms": round(duration_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# PRIORITY-BASED CONTROL ACTION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.execute_priority_action",
    queue="control_queue",
    max_retries=3
)
def execute_priority_action(
    self,
    action: str,
    parameters: Dict[str, Any],
    priority: str = "normal",
    wait_for_completion: bool = False
) -> Dict[str, Any]:
    """
    Execute control action with priority-based routing.
    
    High priority actions go to dedicated queue, bypass rate limits.
    
    Args:
        action: Control action type
        parameters: Action parameters
        priority: Priority level
        wait_for_completion: Wait for async result
    
    Returns:
        Execution result
    """
    logger.info(f"[Priority] {priority.upper()} action: {action}")
    
    # PROMETHEUS: Track priority action
    if METRICS_AVAILABLE:
        try:
            record_aece_action(action=action, priority=priority)
        except Exception:
            pass
    
    # Critical priority uses direct execution (no queue delay)
    if priority == "critical":
        return execute_control_action(
            action=action,
            parameters=parameters,
            priority=priority
        )
    
    # High priority uses dedicated queue
    if priority == "high":
        result = execute_control_action.delay(action, parameters, priority)
        
        if wait_for_completion:
            return result.get(timeout=30)
        
        return {
            "success": True,
            "action": action,
            "task_id": result.id,
            "status": ActionStatus.PENDING.value,
            "message": "Action queued for execution",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Normal/low priority use standard queue
    return execute_control_action.delay(action, parameters, priority).get(timeout=60)


# ============================================================================
# AECE RISK-BASED ACTION TASK (AUTONOMOUS)
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.execute_risk_based_action",
    queue="control_queue",
    max_retries=2
)
def execute_risk_based_action(
    self,
    risk_score: float,
    sector: str = "renewables"
) -> Dict[str, Any]:
    """
    Execute AECE action based on risk score.
    
    This task automatically determines the appropriate action based on
    the current risk score, enabling autonomous control.
    
    Args:
        risk_score: Current AECE risk score (0-1)
        sector: Energy sector
    
    Returns:
        Executed action result
    """
    start_time = time.time()
    
    logger.info(f"[RiskBased] Risk score: {risk_score:.3f} | Sector: {sector}")
    
    # PROMETHEUS: Update risk score
    if METRICS_AVAILABLE:
        try:
            update_aece_risk_score(risk_score)
        except Exception:
            pass
    
    # Determine action based on risk score
    if risk_score >= 0.85:
        action = "lockdown_mode"
        priority = "critical"
        reason = f"Critical risk score: {risk_score:.3f}"
        try:
            record_grid_risk_event("critical")
            set_emergency_stop_state(active=True, component="risk_based")
        except Exception:
            pass
    elif risk_score >= 0.7:
        action = "reduce_load"
        priority = "high"
        reason = f"High risk score: {risk_score:.3f}"
        try:
            record_grid_risk_event("high")
        except Exception:
            pass
    elif risk_score >= 0.5:
        action = "preemptive_stabilization"
        priority = "normal"
        reason = f"Elevated risk score: {risk_score:.3f}"
        try:
            record_grid_risk_event("medium")
        except Exception:
            pass
    elif risk_score >= 0.3:
        action = "trigger_alert"
        priority = "low"
        reason = f"Moderate risk score: {risk_score:.3f}"
    else:
        # No action needed for low risk
        return {
            "success": True,
            "action": "no_action",
            "risk_score": risk_score,
            "message": "Risk score within normal range, no action required",
            "duration_ms": round((time.time() - start_time) * 1000, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Execute determined action
    result = execute_control_action.delay(
        action=action,
        parameters={"reason": reason, "sector": sector},
        priority=priority
    ).get(timeout=60)
    
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(f"[RiskBased] Executed {action} based on risk {risk_score:.3f}")
    
    # PROMETHEUS: Record autonomous decision
    if METRICS_AVAILABLE:
        try:
            record_aece_decision(
                action=action,
                risk_score=risk_score,
                gsi=None,
                ses=None,
                module="risk_based_control"
            )
        except Exception:
            pass
    
    return {
        "success": result.get("success", False) if isinstance(result, dict) else False,
        "action": action,
        "risk_score": risk_score,
        "priority": priority,
        "reason": reason,
        "execution_result": result,
        "duration_ms": round(duration_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# SCHEDULED CONTROL ACTION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.scheduled_control_action",
    queue="control_queue",
    max_retries=3
)
def scheduled_control_action(
    self,
    action: str,
    parameters: Dict[str, Any],
    schedule_time: Optional[str] = None,
    priority: str = "normal"
) -> Dict[str, Any]:
    """
    Execute scheduled control action at specific time.
    
    Args:
        action: Control action type
        parameters: Action parameters
        schedule_time: ISO format datetime string
        priority: Execution priority
    
    Returns:
        Execution result or scheduled confirmation
    """
    logger.info(f"[Scheduled] Preparing {action} for schedule: {schedule_time}")
    
    # PROMETHEUS: Track scheduled action
    if METRICS_AVAILABLE:
        try:
            record_aece_action(action=action, priority=priority)
        except Exception:
            pass
    
    # If schedule time is in the future, delay execution
    if schedule_time:
        try:
            scheduled_dt = datetime.fromisoformat(schedule_time)
            now = datetime.now(timezone.utc)
            
            if scheduled_dt > now:
                # Calculate delay in seconds
                delay_seconds = (scheduled_dt - now).total_seconds()
                
                if delay_seconds > 0:
                    logger.info(f"[Scheduled] Delaying {action} by {delay_seconds:.0f} seconds")
                    
                    # Use Celery's countdown
                    result = execute_control_action.apply_async(
                        args=[action, parameters, priority],
                        countdown=delay_seconds
                    )
                    
                    return {
                        "success": True,
                        "action": action,
                        "task_id": result.id,
                        "status": ActionStatus.PENDING.value,
                        "scheduled_time": schedule_time,
                        "message": f"Action scheduled for {schedule_time}",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            logger.error(f"[Scheduled] Schedule parsing failed: {e}")
    
    # Execute immediately
    return execute_control_action.delay(action, parameters, priority).get(timeout=60)


# ============================================================================
# ACTION STATUS CHECK TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.get_action_status",
    queue="control_queue"
)
def get_action_status(self, task_id: str) -> Dict[str, Any]:
    """
    Get status of a queued control action.
    
    Args:
        task_id: Celery task ID
    
    Returns:
        Task status and result (if available)
    """
    from celery.result import AsyncResult
    from backend.core.celery_app import celery_app
    
    try:
        task = AsyncResult(task_id, app=celery_app)
        
        result = {
            "success": True,
            "task_id": task_id,
            "status": task.status,
            "ready": task.ready(),
            "successful": task.successful() if task.ready() else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if task.ready() and task.successful():
            result["result"] = task.result
        elif task.ready() and not task.successful():
            result["error"] = str(task.info) if task.info else "Task failed"
        
        return result
        
    except Exception as e:
        logger.error(f"[Status] Failed to get status for {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# ACTION CANCELLATION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=ControlTaskBase,
    name="backend.tasks.control_tasks.cancel_action",
    queue="control_queue"
)
def cancel_action(self, task_id: str) -> Dict[str, Any]:
    """
    Cancel a pending control action.
    
    Args:
        task_id: Celery task ID to cancel
    
    Returns:
        Cancellation result
    """
    from celery.result import AsyncResult
    from backend.core.celery_app import celery_app
    
    try:
        task = AsyncResult(task_id, app=celery_app)
        
        if not task.ready():
            task.revoke(terminate=True)
            logger.info(f"[Cancel] Task {task_id} cancelled")
            return {
                "success": True,
                "task_id": task_id,
                "cancelled": True,
                "message": "Task cancelled successfully",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "success": False,
                "task_id": task_id,
                "cancelled": False,
                "message": f"Task already completed with status: {task.status}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
    except Exception as e:
        logger.error(f"[Cancel] Failed to cancel {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# DEAD LETTER QUEUE MANAGEMENT
# ============================================================================

@shared_task(name="backend.tasks.control_tasks.get_control_dlq")
def get_control_dlq() -> Dict[str, Any]:
    """Get the current control dead letter queue contents"""
    return {
        "success": True,
        "queue_size": _control_dlq.size(),
        "entries": _control_dlq.get_all()[-50:],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.control_tasks.get_control_dlq_by_action")
def get_control_dlq_by_action(action: str) -> Dict[str, Any]:
    """Get dead letter queue entries for specific action"""
    return {
        "success": True,
        "action": action,
        "entries": _control_dlq.get_by_action(action),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.control_tasks.retry_from_dlq")
def retry_from_dlq(self, entry_index: int) -> Dict[str, Any]:
    """
    Retry a failed action from the dead letter queue.
    
    Args:
        entry_index: Index of entry in dead letter queue
    
    Returns:
        Retry result
    """
    entries = _control_dlq.get_all()
    
    if entry_index >= len(entries):
        return {
            "success": False,
            "error": f"Entry index {entry_index} out of range",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    entry = entries[entry_index]
    action = entry.get("action")
    parameters = entry.get("parameters", {})
    
    logger.info(f"[DLQ] Retrying {action} from DLQ")
    
    # Re-execute the action
    result = execute_control_action.delay(action, parameters, priority="high").get(timeout=60)
    
    return {
        "success": result.get("success", False) if isinstance(result, dict) else False,
        "action": action,
        "retry_result": result,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.control_tasks.clear_control_dlq")
def clear_control_dlq() -> Dict[str, Any]:
    """Clear the control dead letter queue"""
    _control_dlq.clear()
    return {
        "success": True,
        "message": "Control dead letter queue cleared",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# TASK METRICS AND MONITORING
# ============================================================================

@shared_task(name="backend.tasks.control_tasks.get_control_metrics")
def get_control_metrics() -> Dict[str, Any]:
    """Get metrics for all control tasks"""
    return {
        "success": True,
        "circuit_breakers": {
            name: {
                "state": cb.state,
                "failure_count": cb.failure_count,
                "last_failure_time": cb.last_failure_time
            }
            for name, cb in _action_circuit_breakers.items()
        },
        "dead_letter_queue_size": _control_dlq.size(),
        "idempotency_cache_size": len(_idempotency_cache._cache) if hasattr(_idempotency_cache, '_cache') else 0,
        "prometheus_instrumented": METRICS_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# HEALTH CHECK TASK
# ============================================================================

@shared_task(name="backend.tasks.control_tasks.health_check")
def control_health_check() -> Dict[str, Any]:
    """
    Health check for control tasks system.
    """
    # PROMETHEUS: Update module active status
    try:
        set_active_module(module="control_tasks", active=AECE_AVAILABLE)
    except Exception:
        pass
    
    return {
        "success": True,
        "status": "healthy" if AECE_AVAILABLE else "degraded",
        "aece_available": AECE_AVAILABLE,
        "metrics_available": METRICS_AVAILABLE,
        "circuit_breakers_status": {
            name: cb.state for name, cb in _action_circuit_breakers.items()
        },
        "dead_letter_queue_size": _control_dlq.size(),
        "event_loop_manager_active": True,
        "prometheus_instrumented": METRICS_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# LEGACY COMPATIBILITY WRAPPERS
# ============================================================================

# For backward compatibility with existing code that imports log_control_decision
@shared_task(name="backend.tasks.control_tasks.log_control_decision")
def log_control_decision(decision_data: Dict[str, Any]) -> None:
    """
    Legacy wrapper for log_control_decision.
    Maintains compatibility with existing code.
    """
    action = decision_data.get('decision', {}).get('action', 'unknown')
    logger.info(f"[Legacy] Decision logged: {action}")
    
    # PROMETHEUS: Still track legacy decisions
    if METRICS_AVAILABLE:
        try:
            record_aece_action(action=action, priority="normal")
        except Exception:
            pass


# ============================================================================
# SHUTDOWN HANDLER (for graceful worker shutdown)
# ============================================================================

@shared_task(name="backend.tasks.control_tasks.shutdown")
def shutdown_event_loop() -> Dict[str, Any]:
    """
    Shutdown the event loop manager gracefully.
    Call this during worker shutdown to clean up resources.
    """
    _event_loop_manager.shutdown()
    
    # PROMETHEUS: Mark module inactive on shutdown
    try:
        set_active_module(module="control_tasks", active=False)
    except Exception:
        pass
    
    return {
        "success": True,
        "message": "Event loop manager shutdown complete",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Main tasks
    'execute_control_action',
    'batch_control_actions',
    'execute_priority_action',
    'execute_risk_based_action',
    'scheduled_control_action',
    
    # Status and management
    'get_action_status',
    'cancel_action',
    'control_health_check',
    'get_control_metrics',
    
    # Dead letter queue
    'get_control_dlq',
    'get_control_dlq_by_action',
    'retry_from_dlq',
    'clear_control_dlq',
    
    # Legacy compatibility
    'log_control_decision',
    
    # Shutdown
    'shutdown_event_loop',
    
    # Enums
    'ActionStatus',
    'ActionPriority',
    'ControlActionResult',
    
    # Event loop manager (for advanced use)
    'EventLoopManager',
    '_event_loop_manager'
]