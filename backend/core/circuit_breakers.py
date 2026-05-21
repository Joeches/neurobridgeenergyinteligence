
import os
import time
import threading
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

def _is_production_mode() -> bool:
    """Detect if running in production mode"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    return env in ["production", "prod"]


def _is_development_mode() -> bool:
    """Detect if running in development mode"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    return env in ["development", "dev", "local"]


# ============================================================================
# CIRCUIT BREAKER STATES
# ============================================================================

class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"          # Normal operation, requests allowed
    OPEN = "OPEN"              # Failure threshold exceeded, requests blocked
    HALF_OPEN = "HALF_OPEN"    # Testing recovery, limited requests allowed


# ============================================================================
# CIRCUIT BREAKER CONFIGURATION
# ============================================================================

@dataclass
class CircuitBreakerConfig:
    """
    Configuration for a circuit breaker.
    
    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before attempting recovery (OPEN → HALF_OPEN)
        success_threshold: Number of successes needed to close circuit (HALF_OPEN → CLOSED)
        timeout_threshold: Timeout threshold in seconds (counts as failure)
        max_retries: Maximum retries before opening circuit
        exponential_backoff: Enable exponential backoff for retries
        record_failure_timeout: Seconds to keep failure records
        max_failure_history: Maximum number of failures to track
    """
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 2
    timeout_threshold: float = 30.0
    max_retries: int = 3
    exponential_backoff: bool = True
    record_failure_timeout: int = 300
    max_failure_history: int = 100
    
    @classmethod
    def from_env(cls, prefix: str = "CIRCUIT_BREAKER") -> "CircuitBreakerConfig":
        """Create configuration from environment variables"""
        return cls(
            failure_threshold=int(os.getenv(f"{prefix}_FAILURE_THRESHOLD", "5")),
            recovery_timeout=int(os.getenv(f"{prefix}_RECOVERY_TIMEOUT", "60")),
            success_threshold=int(os.getenv(f"{prefix}_SUCCESS_THRESHOLD", "2")),
            timeout_threshold=float(os.getenv(f"{prefix}_TIMEOUT_THRESHOLD", "30.0")),
            max_retries=int(os.getenv(f"{prefix}_MAX_RETRIES", "3")),
            exponential_backoff=os.getenv(f"{prefix}_EXPONENTIAL_BACKOFF", "true").lower() == "true",
            record_failure_timeout=int(os.getenv(f"{prefix}_RECORD_FAILURE_TIMEOUT", "300")),
            max_failure_history=int(os.getenv(f"{prefix}_MAX_FAILURE_HISTORY", "100"))
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "success_threshold": self.success_threshold,
            "timeout_threshold": self.timeout_threshold,
            "max_retries": self.max_retries,
            "exponential_backoff": self.exponential_backoff,
            "record_failure_timeout": self.record_failure_timeout,
            "max_failure_history": self.max_failure_history
        }


# ============================================================================
# CIRCUIT BREAKER METRICS
# ============================================================================

@dataclass
class CircuitBreakerMetrics:
    """Metrics for a circuit breaker"""
    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_timeouts: int = 0
    state_changes: int = 0
    last_state_change: Optional[str] = None
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    current_failure_count: int = 0
    consecutive_successes: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_timeouts": self.total_timeouts,
            "state_changes": self.state_changes,
            "last_state_change": self.last_state_change,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "current_failure_count": self.current_failure_count,
            "consecutive_successes": self.consecutive_successes,
            "success_rate": round(self.total_successes / max(self.total_requests, 1) * 100, 1)
        }


# ============================================================================
# FAILURE RECORD
# ============================================================================

@dataclass
class FailureRecord:
    """Record of a failure event"""
    timestamp: float
    error_type: str
    error_message: str
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "error_type": self.error_type,
            "error_message": self.error_message[:200],
            "duration_ms": round(self.duration_ms, 2)
        }


# ============================================================================
# LOCAL CIRCUIT BREAKER (Thread-Safe)
# ============================================================================

class CircuitBreaker:
    """
    Thread-safe circuit breaker implementation.
    
    States:
        CLOSED: Normal operation, requests allowed.
                Failures increment counter. Opens when threshold reached.
        
        OPEN:  Requests blocked for recovery_timeout seconds.
               All calls fail fast.
        
        HALF_OPEN: Limited requests allowed for testing recovery.
                   Successes close the circuit.
                   Failures re-open the circuit.
    
    Usage:
        cb = CircuitBreaker("api_name")
        
        if cb.can_execute():
            try:
                result = do_something()
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure(e)
                raise
        else:
            raise CircuitBreakerOpenError("Circuit breaker is open")
    
    Features:
        - Thread-safe with RLock
        - Configurable thresholds
        - Failure history tracking
        - Event callbacks
        - Prometheus metrics integration
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        metrics: Optional[Any] = None,
        callbacks: Optional[Dict[str, List[Callable]]] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Unique identifier for this circuit breaker
            config: Configuration (uses defaults if None)
            metrics: Prometheus metrics instance (optional)
            callbacks: Event callbacks for state changes
        """
        self.name = name
        self.config = config or CircuitBreakerConfig.from_env(prefix=f"CB_{name.upper()}")
        self.metrics = metrics
        self.callbacks = callbacks or {"on_open": [], "on_close": [], "on_half_open": []}
        
        # State
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._consecutive_successes = 0
        self._last_failure_time = 0.0
        self._last_success_time = 0.0
        self._state_change_time = time.time()
        
        # Failure history
        self._failure_history: deque = deque(maxlen=self.config.max_failure_history)
        
        # Stats
        self._stats = CircuitBreakerMetrics()
        self._lock = threading.RLock()
        
        # Singleton tracking
        self._created_at = time.time()
        
        logger.info(f"[CircuitBreaker] {name} initialized | Threshold: {self.config.failure_threshold} | "
                   f"Recovery: {self.config.recovery_timeout}s | Success: {self.config.success_threshold}")
    
    @property
    def state(self) -> CircuitBreakerState:
        """Get current state"""
        with self._lock:
            return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self.state == CircuitBreakerState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)"""
        return self.state == CircuitBreakerState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)"""
        return self.state == CircuitBreakerState.HALF_OPEN
    
    def can_execute(self) -> bool:
        """
        Check if a request can be executed.
        
        Returns:
            True if request should be attempted, False otherwise
        """
        with self._lock:
            self._stats.total_requests += 1
            
            if self._state == CircuitBreakerState.CLOSED:
                return True
            
            elif self._state == CircuitBreakerState.OPEN:
                # Check if recovery timeout has elapsed
                if time.time() - self._state_change_time >= self.config.recovery_timeout:
                    self._transition_to_half_open()
                    return True
                return False
            
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # Allow limited requests in half-open state
                # Only allow one concurrent request in half-open
                # For simplicity, we allow all but track successes
                return True
            
            return False
    
    def record_success(self, duration_ms: float = 0.0) -> None:
        """
        Record a successful request.
        
        Args:
            duration_ms: Request duration in milliseconds (for metrics)
        """
        with self._lock:
            self._stats.total_successes += 1
            self._stats.last_success_time = time.time()
            self._last_success_time = time.time()
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.config.success_threshold:
                    self._transition_to_closed()
            elif self._state == CircuitBreakerState.CLOSED:
                # Reduce failure count gradually on success
                self._failure_count = max(0, self._failure_count - 1)
                self._consecutive_successes += 1
            
            # Update Prometheus metrics
            self._update_metrics(success=True, duration_ms=duration_ms)
    
    def record_failure(self, error: Exception = None, duration_ms: float = 0.0) -> None:
        """
        Record a failed request.
        
        Args:
            error: The exception that caused the failure
            duration_ms: Request duration in milliseconds (for metrics)
        """
        with self._lock:
            self._stats.total_failures += 1
            self._stats.last_failure_time = time.time()
            self._last_failure_time = time.time()
            
            # Record failure in history
            failure_record = FailureRecord(
                timestamp=time.time(),
                error_type=type(error).__name__ if error else "Unknown",
                error_message=str(error) if error else "No error details",
                duration_ms=duration_ms
            )
            self._failure_history.append(failure_record)
            
            if self._state == CircuitBreakerState.CLOSED:
                self._failure_count += 1
                self._consecutive_successes = 0
                
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to_open()
            
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open immediately re-opens
                self._transition_to_open()
            
            # Update Prometheus metrics
            self._update_metrics(success=False, duration_ms=duration_ms)
    
    def record_timeout(self, duration_ms: float = 0.0) -> None:
        """
        Record a timeout (treated as a failure).
        
        Args:
            duration_ms: Request duration in milliseconds
        """
        self._stats.total_timeouts += 1
        self.record_failure(TimeoutError(f"Request timed out after {duration_ms}ms"), duration_ms)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        with self._lock:
            stats = self._stats.to_dict()
            stats.update({
                "name": self.name,
                "state": self._state.value,
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
                "time_since_last_failure": round(time.time() - self._last_failure_time, 2) if self._last_failure_time > 0 else None,
                "time_since_last_success": round(time.time() - self._last_success_time, 2) if self._last_success_time > 0 else None,
                "recent_failures": [f.to_dict() for f in list(self._failure_history)[-10:]],
                "created_at": datetime.fromtimestamp(self._created_at, tz=timezone.utc).isoformat()
            })
            return stats
    
    def reset(self) -> None:
        """Reset circuit breaker to closed state"""
        with self._lock:
            self._transition_to_closed(force=True)
            self._failure_count = 0
            self._consecutive_successes = 0
            self._failure_history.clear()
            logger.info(f"[CircuitBreaker] {self.name} manually reset")
    
    def _transition_to_open(self) -> None:
        """Transition circuit to OPEN state"""
        if self._state == CircuitBreakerState.OPEN:
            return
        
        old_state = self._state
        self._state = CircuitBreakerState.OPEN
        self._state_change_time = time.time()
        self._stats.state_changes += 1
        self._stats.last_state_change = "OPEN"
        
        logger.warning(f"[CircuitBreaker] {self.name}: {old_state.value} → OPEN "
                      f"(failures: {self._failure_count}/{self.config.failure_threshold})")
        
        # Trigger callbacks
        for callback in self.callbacks.get("on_open", []):
            try:
                callback(self.name)
            except Exception as e:
                logger.error(f"Callback error for {self.name}: {e}")
    
    def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state"""
        if self._state == CircuitBreakerState.HALF_OPEN:
            return
        
        old_state = self._state
        self._state = CircuitBreakerState.HALF_OPEN
        self._state_change_time = time.time()
        self._consecutive_successes = 0
        self._stats.state_changes += 1
        self._stats.last_state_change = "HALF_OPEN"
        
        logger.info(f"[CircuitBreaker] {self.name}: {old_state.value} → HALF_OPEN (testing recovery)")
        
        # Trigger callbacks
        for callback in self.callbacks.get("on_half_open", []):
            try:
                callback(self.name)
            except Exception as e:
                logger.error(f"Callback error for {self.name}: {e}")
    
    def _transition_to_closed(self, force: bool = False) -> None:
        """Transition circuit to CLOSED state"""
        if self._state == CircuitBreakerState.CLOSED and not force:
            return
        
        old_state = self._state
        self._state = CircuitBreakerState.CLOSED
        self._state_change_time = time.time()
        self._failure_count = 0
        self._consecutive_successes = 0
        self._stats.state_changes += 1
        self._stats.last_state_change = "CLOSED"
        
        logger.info(f"[CircuitBreaker] {self.name}: {old_state.value} → CLOSED (recovered)")
        
        # Trigger callbacks
        for callback in self.callbacks.get("on_close", []):
            try:
                callback(self.name)
            except Exception as e:
                logger.error(f"Callback error for {self.name}: {e}")
    
    def _update_metrics(self, success: bool, duration_ms: float) -> None:
        """Update Prometheus metrics"""
        if self.metrics:
            try:
                if hasattr(self.metrics, 'circuit_breaker_state'):
                    self.metrics.circuit_breaker_state.labels(
                        name=self.name,
                        state=self._state.value
                    ).set(1 if success else 0)
                
                if hasattr(self.metrics, 'circuit_breaker_requests_total'):
                    status = "success" if success else "failure"
                    self.metrics.circuit_breaker_requests_total.labels(
                        name=self.name,
                        status=status
                    ).inc()
                
                if hasattr(self.metrics, 'circuit_breaker_duration_seconds'):
                    self.metrics.circuit_breaker_duration_seconds.labels(
                        name=self.name
                    ).observe(duration_ms / 1000)
                    
            except Exception as e:
                logger.debug(f"Metrics update failed: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        if not self.can_execute():
            raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is open")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure(exc_val)


# ============================================================================
# DISTRIBUTED CIRCUIT BREAKER (Redis-backed)
# ============================================================================

class DistributedCircuitBreaker(CircuitBreaker):
    """
    Distributed circuit breaker with Redis backend.
    
    Allows multiple workers to share circuit breaker state.
    Useful for distributed Celery workers.
    """
    
    def __init__(
        self,
        name: str,
        redis_manager: Any,
        config: Optional[CircuitBreakerConfig] = None,
        metrics: Optional[Any] = None,
        callbacks: Optional[Dict[str, List[Callable]]] = None
    ):
        """
        Initialize distributed circuit breaker.
        
        Args:
            name: Unique identifier for this circuit breaker
            redis_manager: Redis manager instance for distributed state
            config: Configuration (uses defaults if None)
            metrics: Prometheus metrics instance (optional)
            callbacks: Event callbacks for state changes
        """
        super().__init__(name, config, metrics, callbacks)
        self._redis_manager = redis_manager
        self._redis_available = False
        self._cache_ttl = config.recovery_timeout + 10 if config else 70
        
        # Redis keys
        self._state_key = f"circuit_breaker:{name}:state"
        self._failure_count_key = f"circuit_breaker:{name}:failure_count"
        self._state_change_key = f"circuit_breaker:{name}:state_change"
        self._consecutive_successes_key = f"circuit_breaker:{name}:consecutive_successes"
    
    async def _ensure_redis(self) -> bool:
        """Ensure Redis is available"""
        if self._redis_available:
            return True
        
        if self._redis_manager:
            try:
                if hasattr(self._redis_manager, 'initialize'):
                    await self._redis_manager.initialize()
                self._redis_available = self._redis_manager.available
            except Exception as e:
                logger.debug(f"Redis not available for {self.name}: {e}")
                self._redis_available = False
        
        return self._redis_available
    
    async def _load_state(self) -> None:
        """Load circuit breaker state from Redis"""
        if not await self._ensure_redis():
            return
        
        try:
            # Load state
            state_str = await self._redis_manager.get(self._state_key)
            if state_str:
                self._state = CircuitBreakerState(state_str)
            
            # Load failure count
            failure_count_str = await self._redis_manager.get(self._failure_count_key)
            if failure_count_str:
                self._failure_count = int(failure_count_str)
            
            # Load state change time
            state_change_str = await self._redis_manager.get(self._state_change_key)
            if state_change_str:
                self._state_change_time = float(state_change_str)
            
            # Load consecutive successes
            successes_str = await self._redis_manager.get(self._consecutive_successes_key)
            if successes_str:
                self._consecutive_successes = int(successes_str)
                
        except Exception as e:
            logger.debug(f"Failed to load state from Redis for {self.name}: {e}")
    
    async def _save_state(self) -> None:
        """Save circuit breaker state to Redis"""
        if not await self._ensure_redis():
            return
        
        try:
            await self._redis_manager.setex(self._state_key, self._cache_ttl, self._state.value)
            await self._redis_manager.setex(self._failure_count_key, self._cache_ttl, str(self._failure_count))
            await self._redis_manager.setex(self._state_change_key, self._cache_ttl, str(self._state_change_time))
            await self._redis_manager.setex(self._consecutive_successes_key, self._cache_ttl, str(self._consecutive_successes))
        except Exception as e:
            logger.debug(f"Failed to save state to Redis for {self.name}: {e}")
    
    def can_execute(self) -> bool:
        """Check if request can be executed (with Redis sync)"""
        # Try to load latest state from Redis
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._load_state())
            loop.close()
        except Exception:
            pass
        
        return super().can_execute()
    
    def _transition_to_open(self) -> None:
        """Transition to OPEN and save to Redis"""
        super()._transition_to_open()
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._save_state())
            loop.close()
        except Exception:
            pass
    
    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN and save to Redis"""
        super()._transition_to_half_open()
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._save_state())
            loop.close()
        except Exception:
            pass
    
    def _transition_to_closed(self, force: bool = False) -> None:
        """Transition to CLOSED and save to Redis"""
        super()._transition_to_closed(force)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._save_state())
            loop.close()
        except Exception:
            pass
    
    def record_success(self, duration_ms: float = 0.0) -> None:
        """Record success and save to Redis"""
        super().record_success(duration_ms)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._save_state())
            loop.close()
        except Exception:
            pass
    
    def record_failure(self, error: Exception = None, duration_ms: float = 0.0) -> None:
        """Record failure and save to Redis"""
        super().record_failure(error, duration_ms)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._save_state())
            loop.close()
        except Exception:
            pass


# ============================================================================
# CIRCUIT BREAKER MANAGER (ENHANCED SINGLETON)
# ============================================================================

class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers.
    
    Features:
        - Centralized registry of circuit breakers
        - Bulk operations (reset all, get all stats)
        - Thread-safe access
        - Singleton pattern with proper initialization
    """
    
    _instance: Optional['CircuitBreakerManager'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'CircuitBreakerManager':
        """
        Thread-safe singleton - accepts NO parameters.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        Initialize the circuit breaker manager.
        """
        # Prevent re-initialization
        if getattr(self, '_initialized', False):
            logger.debug("[CircuitBreakerManager] Already initialized, skipping re-initialization")
            return
        
        with self._lock:
            # Double-check after acquiring lock
            if getattr(self, '_initialized', False):
                return
            
            self._breakers: Dict[str, CircuitBreaker] = {}
            self._stats = {
                "singleton_created_at": datetime.now(timezone.utc).isoformat(),
                "initialization_count": 0,
                "last_initialization": None
            }
            
            self._initialized = True
            self._stats["initialization_count"] += 1
            self._stats["last_initialization"] = datetime.now(timezone.utc).isoformat()
            
            logger.info("[CircuitBreakerManager] Initialized")
    
    def is_initialized(self) -> bool:
        """Check if the manager is properly initialized"""
        return getattr(self, '_initialized', False)
    
    def reinitialize_if_needed(self) -> bool:
        """
        Reinitialize the manager if it's not properly initialized.
        Useful for recovery scenarios.
        
        Returns:
            True if reinitialization was performed
        """
        if not self.is_initialized():
            logger.warning("[CircuitBreakerManager] Manager not initialized, reinitializing...")
            self.__init__()
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        return self._stats.copy()
    
    def register(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        metrics: Optional[Any] = None,
        distributed: bool = False,
        redis_manager: Any = None
    ) -> CircuitBreaker:
        """
        Register a new circuit breaker.
        
        Args:
            name: Unique identifier
            config: Circuit breaker configuration
            metrics: Prometheus metrics instance
            distributed: Use distributed mode (Redis-backed)
            redis_manager: Redis manager for distributed mode
        
        Returns:
            Circuit breaker instance
        """
        with self._lock:
            if name in self._breakers:
                logger.warning(f"Circuit breaker '{name}' already registered, returning existing")
                return self._breakers[name]
            
            if distributed and redis_manager:
                cb = DistributedCircuitBreaker(name, redis_manager, config, metrics)
            else:
                cb = CircuitBreaker(name, config, metrics)
            
            self._breakers[name] = cb
            logger.info(f"[CircuitBreakerManager] Registered: {name}")
            return cb
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name"""
        with self._lock:
            return self._breakers.get(name)
    
    def get_all(self) -> Dict[str, CircuitBreaker]:
        """Get all registered circuit breakers"""
        with self._lock:
            return self._breakers.copy()
    
    def reset_all(self) -> int:
        """Reset all circuit breakers"""
        count = 0
        with self._lock:
            for cb in self._breakers.values():
                cb.reset()
                count += 1
        logger.info(f"[CircuitBreakerManager] Reset {count} circuit breakers")
        return count
    
    def reset(self, name: str) -> bool:
        """Reset a specific circuit breaker"""
        with self._lock:
            cb = self._breakers.get(name)
            if cb:
                cb.reset()
                return True
            return False
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers"""
        with self._lock:
            return {name: cb.get_stats() for name, cb in self._breakers.items()}
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all circuit breakers"""
        with self._lock:
            open_count = sum(1 for cb in self._breakers.values() if cb.is_open)
            half_open_count = sum(1 for cb in self._breakers.values() if cb.is_half_open)
            closed_count = sum(1 for cb in self._breakers.values() if cb.is_closed)
            
            return {
                "total": len(self._breakers),
                "closed": closed_count,
                "open": open_count,
                "half_open": half_open_count,
                "manager_stats": self._stats,
                "singleton_initialized": self.is_initialized(),
                "breakers": {
                    name: {
                        "state": cb.state.value,
                        "failure_count": cb._failure_count,
                        "success_rate": cb._stats.total_successes / max(cb._stats.total_requests, 1) * 100
                    }
                    for name, cb in self._breakers.items()
                }
            }


# ============================================================================
# EXCEPTIONS
# ============================================================================

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request cannot be executed"""
    pass


class CircuitBreakerTimeoutError(Exception):
    """Raised when a request times out"""
    pass


# ============================================================================
# DECORATOR
# ============================================================================

def circuit_breaker(
    name: str,
    fallback_value: Any = None,
    raise_on_open: bool = True,
    config: Optional[CircuitBreakerConfig] = None
):
    """
    Decorator to protect a function with a circuit breaker.
    
    Args:
        name: Circuit breaker name
        fallback_value: Value to return when circuit is open (if raise_on_open is False)
        raise_on_open: Raise CircuitBreakerOpenError when circuit is open
        config: Circuit breaker configuration
    
    Usage:
        @circuit_breaker("api_call", fallback_value={"status": "degraded"})
        def call_external_api():
            return requests.get("https://api.example.com")
    """
    def decorator(func):
        # Get or create circuit breaker
        manager = get_circuit_breaker_manager()
        cb = manager.get(name)
        if cb is None:
            cb = manager.register(name, config)
        
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            if not cb.can_execute():
                if raise_on_open:
                    raise CircuitBreakerOpenError(f"Circuit breaker '{name}' is open")
                return fallback_value
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                cb.record_success(duration_ms)
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                cb.record_failure(e, duration_ms)
                raise
        
        return wrapper
    
    return decorator


# ============================================================================
# ASYNC DECORATOR
# ============================================================================

def async_circuit_breaker(
    name: str,
    fallback_value: Any = None,
    raise_on_open: bool = True,
    config: Optional[CircuitBreakerConfig] = None
):
    """
    Async decorator to protect an async function with a circuit breaker.
    
    Usage:
        @async_circuit_breaker("api_call")
        async def call_external_api():
            return await aiohttp.get("https://api.example.com")
    """
    def decorator(func):
        manager = get_circuit_breaker_manager()
        cb = manager.get(name)
        if cb is None:
            cb = manager.register(name, config)
        
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            if not cb.can_execute():
                if raise_on_open:
                    raise CircuitBreakerOpenError(f"Circuit breaker '{name}' is open")
                return fallback_value
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                cb.record_success(duration_ms)
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                cb.record_failure(e, duration_ms)
                raise
        
        return wrapper
    
    return decorator


# ============================================================================
# GLOBAL INSTANCE (ENHANCED)
# ============================================================================

_circuit_breaker_manager: Optional[CircuitBreakerManager] = None
_manager_lock = threading.RLock()


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get global circuit breaker manager instance"""
    global _circuit_breaker_manager
    
    if _circuit_breaker_manager is None:
        with _manager_lock:
            if _circuit_breaker_manager is None:
                _circuit_breaker_manager = CircuitBreakerManager()
                logger.info(f"[CircuitBreakerManager] Global instance created | ID: {id(_circuit_breaker_manager)}")
    
    # Verify the instance is properly initialized
    if _circuit_breaker_manager and not _circuit_breaker_manager.is_initialized():
        logger.warning("[CircuitBreakerManager] Manager exists but not initialized - reinitializing")
        _circuit_breaker_manager.__init__()
    
    return _circuit_breaker_manager


def get_circuit_breaker_manager_safe() -> Optional[CircuitBreakerManager]:
    """
    Safely get circuit breaker manager without auto-creating.
    Returns None if not initialized.
    
    Returns:
        CircuitBreakerManager instance or None
    """
    global _circuit_breaker_manager
    
    if _circuit_breaker_manager is None:
        return None
    
    return _circuit_breaker_manager


def reset_circuit_breaker_manager():
    """
    Reset circuit breaker manager (for testing/hot-reload).
    
    WARNING: This should only be used in testing or during hot-reload.
    In production, use with extreme caution.
    """
    global _circuit_breaker_manager
    with _manager_lock:
        if _circuit_breaker_manager is not None:
            _circuit_breaker_manager.reset_all()
            logger.info("[CircuitBreakerManager] Resetting singleton instance")
            _circuit_breaker_manager = None
            logger.info("[CircuitBreakerManager] Manager singleton reset")


def is_circuit_breaker_manager_initialized() -> bool:
    """Check if circuit breaker manager is initialized"""
    global _circuit_breaker_manager
    return _circuit_breaker_manager is not None and _circuit_breaker_manager.is_initialized()


# ============================================================================
# PRESET CONFIGURATIONS
# ============================================================================

# Predefined configurations for common use cases
PRESET_CONFIGS = {
    "api_external": CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=60,
        success_threshold=2,
        timeout_threshold=30.0
    ),
    "api_internal": CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30,
        success_threshold=1,
        timeout_threshold=10.0
    ),
    "database": CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=60,
        success_threshold=2,
        timeout_threshold=5.0
    ),
    "redis": CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30,
        success_threshold=2,
        timeout_threshold=2.0
    ),
    "hardware": CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30,
        success_threshold=2,
        timeout_threshold=5.0
    ),
    "aece": CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=120,
        success_threshold=3,
        timeout_threshold=10.0
    )
}


# ============================================================================
# INITIALIZATION
# ============================================================================

async def initialize_circuit_breakers() -> Dict[str, Any]:
    """Initialize all circuit breakers (call at app startup)"""
    logger.info("[CircuitBreaker] Initializing...")
    
    manager = get_circuit_breaker_manager()
    
    # Register common circuit breakers with presets
    for name, config in PRESET_CONFIGS.items():
        manager.register(name, config)
    
    logger.info(f"[CircuitBreaker] ✅ Initialized {len(PRESET_CONFIGS)} circuit breakers")
    
    return {
        "success": True,
        "circuit_breakers": list(PRESET_CONFIGS.keys()),
        "manager_initialized": manager.is_initialized(),
        "manager_stats": manager.get_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def shutdown_circuit_breakers() -> None:
    """Shutdown circuit breakers (call at app shutdown)"""
    logger.info("[CircuitBreaker] Shutting down...")
    
    manager = get_circuit_breaker_manager_safe()
    if manager:
        manager.reset_all()
        logger.info("[CircuitBreaker] All circuit breakers reset")
    
    logger.info("[CircuitBreaker] ✅ Shutdown complete")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Classes
    'CircuitBreaker',
    'DistributedCircuitBreaker',
    'CircuitBreakerManager',
    'CircuitBreakerConfig',
    'CircuitBreakerMetrics',
    'FailureRecord',
    'CircuitBreakerState',
    
    # Exceptions
    'CircuitBreakerOpenError',
    'CircuitBreakerTimeoutError',
    
    # Decorators
    'circuit_breaker',
    'async_circuit_breaker',
    
    # Global functions
    'get_circuit_breaker_manager',
    'get_circuit_breaker_manager_safe',
    'reset_circuit_breaker_manager',
    'is_circuit_breaker_manager_initialized',
    'initialize_circuit_breakers',
    'shutdown_circuit_breakers',
    
    # Presets
    'PRESET_CONFIGS'
]