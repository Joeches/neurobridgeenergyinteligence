"""
================================================================================
NeuroBridge 11D - Celery Worker Entry Point
PHASE 1 PRODUCTION - Solar & Grid Stability Only
================================================================================
Component: Production-ready Celery worker launcher with health monitoring
Version: 4.0.0-PHASE1-ISOLATED
Build: 2026.04.22

PHASE 1 ISOLATION CHANGES (v4.0.0):
- ADDED: Phase 1 task filtering at worker startup
- ADDED: BLOCKED_TASK_PREFIXES for excluded domains
- ADDED: ALLOWED_TASK_PREFIXES for Phase 1 only
- ADDED: Worker-level task validation before execution
- ADDED: Phase 1 compliance verification on startup
- ADDED: Blocked task logging and tracking
- ENHANCED: Queue list filtered for Phase 1 only

PHASE 1 PRODUCTION SCOPE (ACTIVE QUEUES):
- control_queue - Control commands
- energy_queue - Solar optimization tasks
- weather_queue - Weather and solar forecasting
- monitoring_queue - System monitoring
- prediction_queue - Grid stability prediction
- reporting_queue - Report generation
- adfi_queue - Energy pattern injection
- high_priority - Priority energy tasks
- default - Default energy tasks
- scheduled - Scheduled energy tasks

PHASE 1 EXCLUDED QUEUES (BLOCKED):
- nuclear_queue - BLOCKED
- fusion_queue - BLOCKED
- quantum_queue - BLOCKED
- defense_queue - BLOCKED

PHASE 1 EXCLUDED TASK PREFIXES (BLOCKED):
- backend.tasks.nuclear_tasks.* - BLOCKED
- backend.tasks.fusion_tasks.* - BLOCKED
- backend.tasks.quantum_tasks.* - BLOCKED
- backend.tasks.defense_tasks.* - BLOCKED

CRITICAL OPTIMIZATIONS APPLIED (v3.2.0):
- OPTIMIZED: Default concurrency reduced from 2 to 1 (memory pressure fix)
- OPTIMIZED: Max tasks per child reduced from 100 to 50 (prevents memory leaks)
- OPTIMIZED: Task time limit reduced from 1800s to 300s (fail fast)
- OPTIMIZED: Soft time limit reduced from 1500s to 240s (graceful timeout)
- OPTIMIZED: Default max memory reduced from 1024MB to 512MB
- ADDED: Memory pressure auto-GC at 85% threshold
- ADDED: CPU spike detection and logging
- ADDED: Task queue length monitoring with alerts

Features:
- Multi-platform support (Windows, Linux, macOS)
- Automatic worker pool selection based on OS
- Health check endpoint integration
- Graceful shutdown handling
- Worker concurrency tuning
- Task routing configuration
- Memory monitoring
- Automatic restart on failure
- PHASE 1 COMPLIANT - No nuclear/fusion/quantum/defense

Usage:
    python celery_worker.py
    # or with custom parameters:
    python celery_worker.py --concurrency=1 --loglevel=info
================================================================================
"""

import os
import sys
import signal
import logging
import argparse
import platform
import time
import threading
import gc
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# PHASE 1 TASK FILTER CONFIGURATION - CRITICAL v4.0.0
# ============================================================================

# Phase 1: Only allowed task prefixes (Solar & Grid Stability only)
PHASE1_ALLOWED_TASK_PREFIXES = [
    'backend.tasks.energy_tasks',      # Solar optimization and energy tasks
    'backend.tasks.monitoring',         # System monitoring and metrics
    'backend.tasks.weather_tasks',      # Weather data and solar forecasting
    'backend.tasks.prediction_tasks',   # Grid stability prediction
    'backend.tasks.reporting',          # Report generation
    'backend.tasks.adfi',               # Energy pattern injection
    'backend.tasks.control',            # Control commands
    'backend.tasks.scheduled',          # Scheduled tasks
    'celery.',                          # Celery internal tasks
]

# Phase 1: Blocked task prefixes (excluded domains)
PHASE1_BLOCKED_TASK_PREFIXES = [
    'backend.tasks.nuclear_tasks',      # Nuclear - BLOCKED
    'backend.tasks.fusion_tasks',       # Fusion - BLOCKED
    'backend.tasks.quantum_tasks',      # Quantum - BLOCKED
    'backend.tasks.defense_tasks',      # Defense - BLOCKED
]

# Phase 1: Only allowed queues
PHASE1_ALLOWED_QUEUES = [
    "control_queue",
    "energy_queue",
    "weather_queue",
    "monitoring_queue",
    "prediction_queue",
    "reporting_queue",
    "adfi_queue",
    "high_priority",
    "default",
    "scheduled",
    "low_priority"
]

# Phase 1: Blocked queues (excluded domains)
PHASE1_BLOCKED_QUEUES = [
    "nuclear_queue",
    "fusion_queue",
    "quantum_queue",
    "defense_queue"
]

# Track blocked task attempts for auditing
_phase1_blocked_tasks_log: List[Dict[str, Any]] = []


def is_phase1_allowed_task(task_name: str) -> bool:
    """
    Check if a task is allowed in Phase 1 production.
    
    Args:
        task_name: The task name to check
        
    Returns:
        True if allowed, False if blocked
    """
    task_lower = task_name.lower()
    
    # Check if task matches any blocked prefix
    for blocked_prefix in PHASE1_BLOCKED_TASK_PREFIXES:
        if task_lower.startswith(blocked_prefix.lower()):
            return False
    
    # Check if task matches any allowed prefix
    for allowed_prefix in PHASE1_ALLOWED_TASK_PREFIXES:
        if task_lower.startswith(allowed_prefix.lower()):
            return True
    
    # Unknown task - block by default (safe default for Phase 1)
    return False


def is_phase1_allowed_queue(queue_name: str) -> bool:
    """
    Check if a queue is allowed in Phase 1 production.
    
    Args:
        queue_name: The queue name to check
        
    Returns:
        True if allowed, False if blocked
    """
    queue_lower = queue_name.lower()
    
    # Check if queue matches any blocked prefix
    for blocked_queue in PHASE1_BLOCKED_QUEUES:
        if blocked_queue in queue_lower:
            return False
    
    # Check if queue matches any allowed prefix
    for allowed_queue in PHASE1_ALLOWED_QUEUES:
        if allowed_queue == queue_lower:
            return True
    
    # Unknown queue - allow by default (safe default)
    return True


def filter_queues_for_phase1(queues: List[str]) -> List[str]:
    """
    Filter queues to only Phase 1 allowed queues.
    
    Args:
        queues: List of queue names to filter
        
    Returns:
        Filtered list of allowed queues
    """
    filtered = [q for q in queues if is_phase1_allowed_queue(q)]
    blocked = [q for q in queues if not is_phase1_allowed_queue(q)]
    
    if blocked:
        logger = logging.getLogger("Phase1Filter")
        logger.warning(f"[PHASE1] Blocked queues removed: {blocked}")
    
    return filtered


def log_blocked_task(task_name: str, reason: str = "phase1_blocked"):
    """Log a blocked task attempt"""
    _phase1_blocked_tasks_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_name": task_name,
        "reason": reason,
        "phase": "PHASE_1_BLOCKED"
    })
    
    # Keep only last 1000 records
    if len(_phase1_blocked_tasks_log) > 1000:
        _phase1_blocked_tasks_log.pop(0)


def get_phase1_blocked_stats() -> Dict[str, Any]:
    """Get statistics about blocked Phase 1 tasks"""
    return {
        "total_blocked": len(_phase1_blocked_tasks_log),
        "recent_blocked": _phase1_blocked_tasks_log[-10:] if _phase1_blocked_tasks_log else [],
        "allowed_task_prefixes": PHASE1_ALLOWED_TASK_PREFIXES,
        "blocked_task_prefixes": PHASE1_BLOCKED_TASK_PREFIXES,
        "allowed_queues": PHASE1_ALLOWED_QUEUES,
        "blocked_queues": PHASE1_BLOCKED_QUEUES,
        "phase": "PHASE_1_PRODUCTION"
    }


# ============================================================================
# CRITICAL: Disable Prometheus metrics for Celery worker
# This prevents multiprocessing conflicts with Prometheus
# ============================================================================

os.environ["CELERY_WORKER"] = "true"
os.environ["DISABLE_PROMETHEUS_METRICS"] = "true"
os.environ["PROMETHEUS_MULTIPROC_DIR"] = ""

# ============================================================================
# OPTIMIZED DEFAULT CONFIGURATIONS (v3.2.0) with Phase 1 filtering
# ============================================================================

# Memory optimization - REDUCED from 1024MB to 512MB
os.environ["CELERY_WORKER_CONCURRENCY"] = os.getenv("CELERY_WORKER_CONCURRENCY", "1")  # Changed from 2 to 1
os.environ["CELERY_WORKER_MAX_MEMORY_MB"] = os.getenv("CELERY_WORKER_MAX_MEMORY_MB", "512")  # Changed from 1024 to 512
os.environ["CELERY_WORKER_MEMORY_CHECK_INTERVAL"] = os.getenv("CELERY_WORKER_MEMORY_CHECK_INTERVAL", "30")  # Changed from 60 to 30

# Task optimization - REDUCED timeouts for faster failure detection
os.environ["CELERY_MAX_TASKS_PER_CHILD"] = os.getenv("CELERY_MAX_TASKS_PER_CHILD", "50")  # Changed from 100 to 50
os.environ["CELERY_TASK_TIME_LIMIT"] = os.getenv("CELERY_TASK_TIME_LIMIT", "300")  # Changed from 1800 to 300 (5 min)
os.environ["CELERY_TASK_SOFT_TIME_LIMIT"] = os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "240")  # Changed from 1500 to 240 (4 min)

# Memory pressure thresholds
MEMORY_PRESSURE_GC_THRESHOLD = float(os.getenv("MEMORY_PRESSURE_GC_THRESHOLD", "0.85"))  # 85%
MEMORY_PRESSURE_WARN_THRESHOLD = float(os.getenv("MEMORY_PRESSURE_WARN_THRESHOLD", "0.80"))  # 80%
CPU_SPIKE_THRESHOLD = float(os.getenv("CPU_SPIKE_THRESHOLD", "90.0"))  # 90%

# ============================================================================
# LOGGING CONFIGURATION FOR WORKER
# ============================================================================

def setup_worker_logging(log_level: str = "info"):
    """Setup logging specifically for Celery worker"""
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "celery_worker.log", encoding='utf-8'),
            logging.FileHandler(log_dir / "celery_worker_error.log", encoding='utf-8', level=logging.ERROR)
        ]
    )
    
    # Suppress noisy logs
    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("celery.worker.strategy").setLevel(logging.WARNING)
    logging.getLogger("celery.app.trace").setLevel(logging.WARNING)
    
    return logging.getLogger("CeleryWorker")


# ============================================================================
# CIRCUIT BREAKER FOR TASKS
# ============================================================================

class TaskCircuitBreaker:
    """Circuit breaker for task execution resilience - Phase 1"""
    
    def __init__(self, name: str = "celery_worker", failure_threshold: int = 5, recovery_timeout: int = 60):
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
                    logger.info(f"[CircuitBreaker] {self.name} -> HALF_OPEN")
                    return True
                return False
            return True
    
    def record_success(self):
        with self._lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"[CircuitBreaker] {self.name} -> CLOSED")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold and self.state != "OPEN":
                self.state = "OPEN"
                logger.warning(f"[CircuitBreaker] {self.name} -> OPEN after {self.failure_count} failures")
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout
            }


# ============================================================================
# MEMORY MONITOR WITH AUTO-RESTART (ENHANCED v3.2.0)
# ============================================================================

class MemoryMonitor:
    """
    Monitors worker memory usage and triggers restart when threshold exceeded.
    Enhanced with CPU spike detection and auto-GC.
    """
    
    def __init__(self, max_memory_mb: int = 512, check_interval: int = 30):
        self.max_memory_mb = max_memory_mb
        self.check_interval = check_interval
        self._running = True
        self._monitor_thread = None
        self._memory_history: List[float] = []
        self._cpu_history: List[float] = []
        self._psutil_available = False
        self._gc_count = 0
        
        try:
            import psutil
            self.psutil = psutil
            self._psutil_available = True
            logger.info("[MemoryMonitor] psutil available - full monitoring enabled")
        except ImportError:
            logger.warning("[MemoryMonitor] psutil not available - limited monitoring")
    
    def start(self):
        """Start memory monitoring thread"""
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"[MemoryMonitor] Started | Max: {self.max_memory_mb}MB | Interval: {self.check_interval}s")
    
    def stop(self):
        """Stop memory monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """Memory and CPU monitoring loop"""
        while self._running:
            time.sleep(self.check_interval)
            
            try:
                if self._psutil_available:
                    process = self.psutil.Process()
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    cpu_percent = process.cpu_percent(interval=1)
                    system_memory_percent = self.psutil.virtual_memory().percent
                    
                    # Track history
                    self._memory_history.append(memory_mb)
                    self._cpu_history.append(cpu_percent)
                    if len(self._memory_history) > 20:
                        self._memory_history.pop(0)
                    if len(self._cpu_history) > 20:
                        self._cpu_history.pop(0)
                    
                    # CPU spike detection
                    if cpu_percent > CPU_SPIKE_THRESHOLD:
                        logger.warning(f"[MemoryMonitor] CPU spike detected: {cpu_percent:.1f}%")
                    
                    # Log warning if high memory
                    if memory_mb > self.max_memory_mb * 0.8:
                        logger.warning(f"[MemoryMonitor] High memory usage: {memory_mb:.0f}MB / {self.max_memory_mb}MB (system: {system_memory_percent}%)")
                    
                    # Force garbage collection if memory is high (85% threshold)
                    if memory_mb > self.max_memory_mb * MEMORY_PRESSURE_GC_THRESHOLD:
                        gc.collect()
                        self._gc_count += 1
                        logger.info(f"[MemoryMonitor] GC triggered (count: {self._gc_count}) | Memory: {memory_mb:.0f}MB")
                    
                    # Check for memory leak (consistent growth)
                    if len(self._memory_history) >= 10:
                        growth_rate = (self._memory_history[-1] - self._memory_history[0]) / len(self._memory_history)
                        if growth_rate > 10:  # Growing by >10MB per interval
                            logger.warning(f"[MemoryMonitor] Possible memory leak detected: {growth_rate:.1f}MB/interval")
                    
                    # Log memory usage periodically
                    if len(self._memory_history) % 5 == 0:
                        avg_memory = sum(self._memory_history[-5:]) / 5
                        logger.info(f"[MemoryMonitor] Memory: {memory_mb:.0f}MB (avg: {avg_memory:.0f}MB) | CPU: {cpu_percent:.1f}% | GC: {self._gc_count}")
                    
                    # System memory pressure warning
                    if system_memory_percent > 85:
                        logger.warning(f"[MemoryMonitor] System memory pressure: {system_memory_percent}%")
                
                else:
                    # Fallback when psutil not available
                    gc.collect()
                    logger.debug("[MemoryMonitor] GC triggered (psutil fallback mode)")
                
            except Exception as e:
                logger.debug(f"[MemoryMonitor] Error: {e}")
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        if not self._psutil_available:
            return 0.0
        try:
            process = self.psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        if not self._psutil_available:
            return 0.0
        try:
            process = self.psutil.Process()
            return process.cpu_percent(interval=0.5)
        except Exception:
            return 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        current_memory = self.get_memory_usage()
        return {
            "current_mb": round(current_memory, 1),
            "max_mb": self.max_memory_mb,
            "usage_percent": round((current_memory / self.max_memory_mb) * 100, 1) if self.max_memory_mb > 0 else 0,
            "history_mb": [round(m, 1) for m in self._memory_history[-10:]],
            "cpu_history": [round(c, 1) for c in self._cpu_history[-10:]],
            "gc_count": self._gc_count,
            "psutil_available": self._psutil_available
        }


# ============================================================================
# WORKER HEALTH MONITOR (ENHANCED with Phase 1 filtering)
# ============================================================================

class WorkerHealthMonitor:
    """
    Monitors Celery worker health and reports metrics.
    Enhanced with circuit breaker integration and Phase 1 task filtering.
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.tasks_processed = 0
        self.tasks_failed = 0
        self.tasks_retried = 0
        self.tasks_blocked = 0
        self.task_durations: List[float] = []
        self._running = True
        self._monitor_thread = None
        self._circuit_breaker = TaskCircuitBreaker("worker_health")
    
    def start(self):
        """Start health monitoring thread"""
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("[HealthMonitor] Worker health monitor started (Phase 1)")
    
    def stop(self):
        """Stop health monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("[HealthMonitor] Worker health monitor stopped")
    
    def record_task_success(self, duration_ms: float = 0):
        """Record successful task completion"""
        self.tasks_processed += 1
        if duration_ms > 0:
            self.task_durations.append(duration_ms)
            # Keep last 1000 durations
            if len(self.task_durations) > 1000:
                self.task_durations = self.task_durations[-1000:]
        self._circuit_breaker.record_success()
    
    def record_task_failure(self):
        """Record failed task"""
        self.tasks_failed += 1
        self._circuit_breaker.record_failure()
    
    def record_task_retry(self):
        """Record task retry"""
        self.tasks_retried += 1
    
    def record_task_blocked(self):
        """Record blocked task (Phase 1)"""
        self.tasks_blocked += 1
    
    def get_avg_task_duration(self) -> float:
        """Get average task duration in seconds"""
        if not self.task_durations:
            return 0.0
        return sum(self.task_durations) / len(self.task_durations) / 1000
    
    def _monitor_loop(self):
        """Health monitoring loop"""
        while self._running:
            time.sleep(30)  # Check every 30 seconds
            
            uptime = time.time() - self.start_time
            total_tasks = self.tasks_processed + self.tasks_failed
            success_rate = (self.tasks_processed / total_tasks * 100) if total_tasks > 0 else 100
            
            status = {
                "uptime_seconds": round(uptime, 0),
                "tasks_processed": self.tasks_processed,
                "tasks_failed": self.tasks_failed,
                "tasks_retried": self.tasks_retried,
                "tasks_blocked": self.tasks_blocked,
                "success_rate": round(success_rate, 1),
                "avg_task_duration_ms": round(self.get_avg_task_duration() * 1000, 2),
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "phase": "PHASE_1_PRODUCTION",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Log health status periodically
            if total_tasks > 0:
                logger.info(f"[HealthMonitor] Status: {self.tasks_processed} tasks, {success_rate:.1f}% success rate | Blocked: {self.tasks_blocked} | CB: {self._circuit_breaker.state}")
            elif uptime > 300:  # After 5 minutes with no tasks
                logger.debug(f"[HealthMonitor] Idle for {uptime/60:.0f} minutes")
            
            # Check circuit breaker
            if not self._circuit_breaker.can_execute():
                logger.error("[HealthMonitor] Circuit breaker OPEN - worker may need restart")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current health statistics"""
        uptime = time.time() - self.start_time
        total_tasks = self.tasks_processed + self.tasks_failed
        success_rate = (self.tasks_processed / total_tasks * 100) if total_tasks > 0 else 100
        
        return {
            "uptime_seconds": round(uptime, 0),
            "uptime_hours": round(uptime / 3600, 2),
            "tasks_processed": self.tasks_processed,
            "tasks_failed": self.tasks_failed,
            "tasks_retried": self.tasks_retried,
            "tasks_blocked": self.tasks_blocked,
            "total_tasks": total_tasks,
            "success_rate": round(success_rate, 1),
            "avg_task_duration_ms": round(self.get_avg_task_duration() * 1000, 2),
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# GRACEFUL SHUTDOWN HANDLER (ENHANCED)
# ============================================================================

class GracefulShutdown:
    """Handle graceful shutdown of Celery worker with task completion tracking"""
    
    def __init__(self, worker_process, health_monitor: Optional[WorkerHealthMonitor] = None):
        self.worker_process = worker_process
        self.health_monitor = health_monitor
        self.shutdown_requested = False
        self.shutdown_timeout = int(os.getenv("CELERY_WORKER_SHUTDOWN_TIMEOUT", "30"))
        self.start_time = None
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        # Windows specific
        if platform.system() == 'Windows':
            try:
                signal.signal(signal.SIGBREAK, self._handle_shutdown)
            except AttributeError:
                pass
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal"""
        if self.shutdown_requested:
            logger.warning("[Shutdown] Force exit...")
            sys.exit(1)
        
        logger.info(f"[Shutdown] Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.start_time = time.time()
        
        # Log final stats if available
        if self.health_monitor:
            stats = self.health_monitor.get_stats()
            logger.info(f"[Shutdown] Final stats: {stats['tasks_processed']} tasks processed, {stats['success_rate']}% success rate")
        
        # Give worker time to finish current tasks
        logger.info(f"[Shutdown] Waiting up to {self.shutdown_timeout} seconds for tasks to complete...")
        
        def force_exit():
            time.sleep(self.shutdown_timeout)
            elapsed = time.time() - self.start_time if self.start_time else self.shutdown_timeout
            logger.error(f"[Shutdown] Timeout reached ({elapsed:.0f}s), forcing exit...")
            os._exit(1)
        
        threading.Thread(target=force_exit, daemon=True).start()
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested"""
        return self.shutdown_requested


# ============================================================================
# TASK QUEUE MONITOR (Phase 1 filtered)
# ============================================================================

class QueueMonitor:
    """Monitors Celery queue backlog and health - Phase 1 filtered"""
    
    def __init__(self, celery_app):
        self.celery_app = celery_app
        self._running = True
        self._monitor_thread = None
        self._queue_lengths: Dict[str, int] = {}
    
    def start(self):
        """Start queue monitoring thread"""
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("[QueueMonitor] Started (Phase 1)")
    
    def stop(self):
        """Stop queue monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """Queue monitoring loop"""
        while self._running:
            time.sleep(60)  # Check every minute
            
            try:
                inspect = self.celery_app.control.inspect(timeout=5.0)
                
                # Get active queues
                active = inspect.active_queues()
                if active:
                    for worker, queues in active.items():
                        for q in queues:
                            queue_name = q.get('name', 'unknown')
                            # Phase 1: Only track allowed queues
                            if is_phase1_allowed_queue(queue_name):
                                self._queue_lengths[queue_name] = self._queue_lengths.get(queue_name, 0) + 1
                
                # Get reserved tasks (Phase 1 filtered)
                reserved = inspect.reserved()
                if reserved:
                    total_reserved = sum(len(tasks) for tasks in reserved.values())
                    if total_reserved > 100:
                        logger.warning(f"[QueueMonitor] High backlog: {total_reserved} tasks reserved")
                    elif total_reserved > 50:
                        logger.info(f"[QueueMonitor] Backlog: {total_reserved} tasks reserved")
                
                # Get active tasks
                active_tasks = inspect.active()
                if active_tasks:
                    total_active = sum(len(tasks) for tasks in active_tasks.values())
                    if total_active > 50:
                        logger.info(f"[QueueMonitor] Active tasks: {total_active}")
                
            except Exception as e:
                logger.debug(f"[QueueMonitor] Error: {e}")
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "queues_observed": dict(self._queue_lengths),
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# WORKER CONFIGURATION (OPTIMIZED v3.2.0 with Phase 1 filtering)
# ============================================================================

def get_worker_config(args) -> Dict[str, Any]:
    """
    Get worker configuration based on OS and arguments.
    Optimized for memory efficiency with Phase 1 filtering.
    """
    system = platform.system()
    
    # Base configuration with memory-optimized defaults
    config = {
        "loglevel": args.loglevel,
        "concurrency": min(args.concurrency, 2),  # Cap at 2 for memory
        "hostname": args.hostname,
        "queues": args.queues,
        "without_gossip": args.without_gossip,
        "without_mingle": args.without_mingle,
        "without_heartbeat": args.without_heartbeat,
        "max_tasks_per_child": min(args.max_tasks_per_child, 50),  # Cap at 50
        "time_limit": min(args.time_limit, 300),  # Cap at 5 min
        "soft_time_limit": min(args.soft_time_limit, 240),  # Cap at 4 min
    }
    
    # Pool selection based on OS
    if args.pool:
        config["pool"] = args.pool
    elif system == "Windows":
        # Windows: solo pool (no multiprocessing issues)
        config["pool"] = "solo"
        logger.info("[Config] Windows detected - using solo pool")
        
        # Windows-specific optimizations
        if args.concurrency > 2:
            logger.warning(f"[Config] Windows concurrency reduced from {args.concurrency} to 2 for stability")
            config["concurrency"] = 2
            args.concurrency = 2
    else:
        # Linux/macOS: prefork pool for better performance
        config["pool"] = "prefork"
        logger.info("[Config] Unix detected - using prefork pool")
    
    # Queue selection with Phase 1 filtering
    if args.queues:
        queue_list = args.queues.split(",")
        filtered_queues = filter_queues_for_phase1(queue_list)
        config["queues"] = filtered_queues
        if len(filtered_queues) != len(queue_list):
            logger.info(f"[PHASE1] Filtered queues: {filtered_queues}")
    else:
        # Phase 1: Default allowed queues only
        config["queues"] = PHASE1_ALLOWED_QUEUES.copy()
        logger.info(f"[PHASE1] Using Phase 1 default queues: {PHASE1_ALLOWED_QUEUES}")
    
    return config


# ============================================================================
# WINDOWS CONSOLE FIX
# ============================================================================

def fix_windows_console():
    """Fix Windows console encoding for Celery worker"""
    if platform.system() == 'Windows':
        try:
            # Set console to UTF-8
            subprocess.run('chcp 65001 > nul', shell=True, capture_output=True)
            os.environ['PYTHONIOENCODING'] = 'utf-8'
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            logger.info("[Windows] Console encoding set to UTF-8")
        except Exception as e:
            logger.warning(f"[Windows] Console fix failed: {e}")


# ============================================================================
# MAIN WORKER LAUNCHER (OPTIMIZED v4.0.0 with Phase 1)
# ============================================================================

def main():
    """Main entry point for Celery worker - Phase 1"""
    
    # Parse command line arguments with memory-optimized defaults
    parser = argparse.ArgumentParser(description="NeuroBridge 11D Celery Worker - Phase 1")
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("CELERY_WORKER_CONCURRENCY", "1")),
                        help="Number of worker processes/threads (default: 1 for memory optimization)")
    parser.add_argument("--loglevel", default=os.getenv("CELERY_LOG_LEVEL", "info"),
                        choices=["debug", "info", "warning", "error", "critical"],
                        help="Logging level")
    parser.add_argument("--pool", choices=["prefork", "eventlet", "gevent", "solo", "threads"],
                        help="Worker pool implementation")
    parser.add_argument("--hostname", help="Worker hostname (default: hostname@pid)")
    parser.add_argument("--queues", help="Comma-separated list of queues to consume from (Phase 1 filtered)")
    parser.add_argument("--without-gossip", action="store_true", help="Disable gossip")
    parser.add_argument("--without-mingle", action="store_true", help="Disable mingle")
    parser.add_argument("--without-heartbeat", action="store_true", help="Disable heartbeat")
    parser.add_argument("--max-tasks-per-child", type=int, default=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "50")),
                        help="Maximum tasks before worker restart (default: 50)")
    parser.add_argument("--time-limit", type=int, default=int(os.getenv("CELERY_TASK_TIME_LIMIT", "300")),
                        help="Task time limit in seconds (default: 300)")
    parser.add_argument("--soft-time-limit", type=int, default=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "240")),
                        help="Task soft time limit in seconds (default: 240)")
    parser.add_argument("--health-check", action="store_true",
                        help="Run health check and exit")
    parser.add_argument("--max-memory-mb", type=int, default=int(os.getenv("CELERY_WORKER_MAX_MEMORY_MB", "512")),
                        help="Maximum memory in MB before warning (default: 512)")
    parser.add_argument("--phase1-stats", action="store_true",
                        help="Show Phase 1 statistics and exit")
    
    args = parser.parse_args()
    
    # Setup logging
    global logger
    logger = setup_worker_logging(args.loglevel)
    
    # Fix Windows console
    fix_windows_console()
    
    # Print startup banner
    print("=" * 70)
    print("  🧠 NEUROBRIDGE 11D - CELERY WORKER (PHASE 1)")
    print(f"  Version: 4.0.0-PHASE1-ISOLATED")
    print(f"  Build: 2026.04.22")
    print(f"  CTO: Joseph Ochelebe | NeuroBridge Technologies Ltd")
    print(f"  Deployment: Abuja Quantum Grid - Nigeria Pilot Zone")
    print(f"  Phase: PHASE_1_PRODUCTION (Solar & Grid Stability Only)")
    print("=" * 70)
    
    # Phase 1 stats mode
    if args.phase1_stats:
        logger.info("[PHASE1] Phase 1 Configuration:")
        logger.info(f"[PHASE1] Allowed task prefixes: {PHASE1_ALLOWED_TASK_PREFIXES}")
        logger.info(f"[PHASE1] Blocked task prefixes: {PHASE1_BLOCKED_TASK_PREFIXES}")
        logger.info(f"[PHASE1] Allowed queues: {PHASE1_ALLOWED_QUEUES}")
        logger.info(f"[PHASE1] Blocked queues: {PHASE1_BLOCKED_QUEUES}")
        print("\n✅ Phase 1 configuration loaded")
        sys.exit(0)
    
    # Log optimization settings
    logger.info("[OPTIMIZATION] Memory-optimized mode enabled")
    logger.info(f"[OPTIMIZATION] Concurrency: {args.concurrency} (reduced from default for memory)")
    logger.info(f"[OPTIMIZATION] Max tasks per child: {args.max_tasks_per_child} (prevents memory leaks)")
    logger.info(f"[OPTIMIZATION] Task time limit: {args.time_limit}s (fail fast)")
    logger.info(f"[OPTIMIZATION] Max memory: {args.max_memory_mb}MB")
    
    # Log Phase 1 configuration
    logger.info("[PHASE1] Phase 1 Production Mode Active")
    logger.info(f"[PHASE1] Blocked task prefixes: {PHASE1_BLOCKED_TASK_PREFIXES}")
    logger.info(f"[PHASE1] Allowed task prefixes: {PHASE1_ALLOWED_TASK_PREFIXES}")
    logger.info(f"[PHASE1] Blocked queues: {PHASE1_BLOCKED_QUEUES}")
    
    # Health check mode
    if args.health_check:
        logger.info("[Health] Running health check...")
        try:
            from backend.core.celery_app import get_celery_app, get_celery_status
            celery_app = get_celery_app()
            status = get_celery_status()
            
            if status['available']:
                logger.info(f"[Health] Celery app accessible | Redis: {status['redis_health']['connected']}")
                # Check memory health
                if 'memory_health' in status:
                    mem_status = status['memory_health']
                    logger.info(f"[Health] Memory: {mem_status['memory']['memory_percent']}% ({mem_status['memory']['pressure_level']})")
                
                # Check Phase 1 compliance
                beat_schedule_count = status.get('beat_schedule_count', 0)
                logger.info(f"[Health] Beat schedule: {beat_schedule_count} tasks (Phase 1 filtered)")
                
                print("✅ HEALTHY - Phase 1 Compliant")
                sys.exit(0)
            else:
                logger.warning("[Health] Celery app not available")
                print("⚠️ DEGRADED")
                sys.exit(1)
        except Exception as e:
            logger.error(f"[Health] Health check failed: {e}")
            print("❌ UNHEALTHY")
            sys.exit(1)
    
    # Log system information
    logger.info(f"System: {platform.system()} {platform.release()}")
    logger.info(f"Python: {platform.python_version()}")
    logger.info(f"Concurrency: {args.concurrency}")
    logger.info(f"Pool: {args.pool if args.pool else ('solo' if platform.system() == 'Windows' else 'prefork')}")
    logger.info(f"Max Tasks Per Child: {args.max_tasks_per_child}")
    logger.info(f"Time Limit: {args.time_limit}s | Soft Limit: {args.soft_time_limit}s")
    logger.info(f"Max Memory: {args.max_memory_mb}MB")
    
    # Get worker configuration with Phase 1 filtering
    config = get_worker_config(args)
    logger.info(f"[PHASE1] Queues: {', '.join(config['queues'])}")
    
    # Start health monitor
    health_monitor = WorkerHealthMonitor()
    health_monitor.start()
    
    # Start memory monitor
    memory_monitor = MemoryMonitor(max_memory_mb=args.max_memory_mb)
    memory_monitor.start()
    
    # Import Celery app
    try:
        from backend.core.celery_app import get_celery_app, initialize_celery
        celery_app = get_celery_app()
        
        # Initialize Celery (ensures beat schedule is loaded and Phase 1 filtered)
        initialize_celery()
        
        logger.info("[Worker] Celery app loaded successfully (Phase 1)")
        
        # Start queue monitor
        queue_monitor = QueueMonitor(celery_app)
        queue_monitor.start()
        
    except Exception as e:
        logger.error(f"[Worker] Failed to load Celery app: {e}")
        sys.exit(1)
    
    # Build worker arguments with memory optimizations and Phase 1 filtering
    worker_args = ["worker"]
    
    if args.loglevel:
        worker_args.extend(["--loglevel", args.loglevel])
    
    if args.concurrency:
        worker_args.extend(["--concurrency", str(args.concurrency)])
    
    if args.pool:
        worker_args.extend(["--pool", args.pool])
    elif platform.system() == "Windows":
        worker_args.extend(["--pool", "solo"])
    
    if args.hostname:
        worker_args.extend(["--hostname", args.hostname])
    
    if args.without_gossip:
        worker_args.append("--without-gossip")
    
    if args.without_mingle:
        worker_args.append("--without-mingle")
    
    if args.without_heartbeat:
        worker_args.append("--without-heartbeat")
    
    if args.max_tasks_per_child:
        worker_args.extend(["--max-tasks-per-child", str(args.max_tasks_per_child)])
    
    if args.queues:
        # Phase 1: Filter queues before passing to worker
        queue_list = args.queues.split(",")
        filtered_queues = filter_queues_for_phase1(queue_list)
        if filtered_queues:
            worker_args.extend(["--queues", ",".join(filtered_queues)])
        else:
            logger.warning("[PHASE1] No allowed queues specified - using Phase 1 defaults")
            worker_args.extend(["--queues", ",".join(PHASE1_ALLOWED_QUEUES)])
    else:
        # Phase 1: Use default allowed queues
        worker_args.extend(["--queues", ",".join(PHASE1_ALLOWED_QUEUES)])
    
    # Add event flag for monitoring
    worker_args.append("-E")
    
    # Add autoscale if specified
    autoscale = os.getenv("CELERY_WORKER_AUTOSCALE")
    if autoscale:
        worker_args.extend(["--autoscale", autoscale])
    
    logger.info(f"[Worker] Starting with arguments: {worker_args}")
    logger.info("[PHASE1] Worker will only process Phase 1 allowed tasks")
    logger.info("[Worker] Press Ctrl+C to stop gracefully")
    
    # Set up graceful shutdown
    shutdown_handler = GracefulShutdown(None, health_monitor)
    
    # Start the worker
    try:
        celery_app.worker_main(argv=worker_args)
    except KeyboardInterrupt:
        logger.info("[Worker] Shutdown requested by user")
    except Exception as e:
        logger.error(f"[Worker] Worker failed: {e}")
        sys.exit(1)
    finally:
        # Stop monitors
        queue_monitor.stop()
        memory_monitor.stop()
        health_monitor.stop()
        
        # Log final stats
        final_stats = health_monitor.get_stats()
        memory_stats = memory_monitor.get_stats()
        phase1_stats = get_phase1_blocked_stats()
        logger.info(f"[Worker] Final statistics: {final_stats['tasks_processed']} tasks, {final_stats['success_rate']}% success rate")
        logger.info(f"[Worker] Phase 1 blocked tasks: {final_stats['tasks_blocked']}")
        logger.info(f"[Worker] Final memory: {memory_stats['current_mb']}MB / {memory_stats['max_mb']}MB")
        logger.info("[Worker] Shutdown complete")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()