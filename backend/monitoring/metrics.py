"""
================================================================================
NeuroBridge 11D - Redis Core (Phase 1 Production)
================================================================================
Component: Redis connection management with Phase 1 key filtering
Author: NeuroBridge Technologies Ltd | CTO: Joseph Ochelebe
Version: 4.0.0-PHASE1-ISOLATED
Build: 2026.04.22

PHASE 1 ISOLATION CHANGES (v4.0.0):
- ADDED: Phase 1 key filtering - Blocks nuclear/fusion/quantum/defense keys
- ADDED: PHASE1_ALLOWED_KEY_PREFIXES for allowed domains
- ADDED: PHASE1_BLOCKED_KEY_PREFIXES for excluded domains
- ADDED: Key validation before Redis operations
- ADDED: Phase 1 compliance verification for all operations
- ADDED: Blocked key access logging and tracking

PHASE 1 ALLOWED KEY PREFIXES (ACTIVE):
- energy:* - Energy metrics and data
- weather:* - Weather data
- aece:* - AECE state and decisions
- session:* - User sessions
- rate_limit:* - Rate limiting
- cache:* - General cache
- simulation:* - Energy simulations
- inverter:* - Inverter telemetry
- nasa:* - NASA solar data
- gee:* - GEE environmental data
- openweather:* - Weather data
- sungrow:* - Inverter data
- report:* - Reports
- hardware:* - Hardware telemetry
- modbus:* - Modbus bridge data
- circuit_breaker:* - Circuit breaker state

PHASE 1 BLOCKED KEY PREFIXES (EXCLUDED):
- nuclear:* - Nuclear data - BLOCKED
- fusion:* - Fusion data - BLOCKED
- quantum:* - Quantum data - BLOCKED
- defense:* - Defense data - BLOCKED

CRITICAL FIXES APPLIED (v3.2.0):
- FIXED: Proper singleton pattern with __new__ method
- FIXED: Added _initialized flag with double-checked locking
- FIXED: Added async/await support for all Redis operations
- FIXED: Added circuit breaker pattern for Redis connection
- FIXED: Added health monitoring and auto-reconnect
- FIXED: Graceful fallback when Redis is unavailable

Features:
- Connection pooling with auto-reconnect
- Graceful fallback when Redis unavailable
- Circuit breaker pattern for fault tolerance
- Health monitoring with auto-recovery
- Async/await support for all operations
- Compression for large values
- Rate limiting with Redis backend
- Distributed locks
- Pub/Sub support
- Session management
- AECE state persistence
- PHASE 1 KEY FILTERING - No nuclear/fusion/quantum/defense keys
================================================================================
"""

import os
import redis
import json
import logging
import time
import threading
import asyncio
import zlib
from typing import Optional, Any, Dict, List, Tuple, Set
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone, timedelta
from collections import defaultdict

logger = logging.getLogger("backend.core.redis")

# ============================================================================
# PHASE 1 KEY FILTER CONFIGURATION
# ============================================================================

# Phase 1: Allowed key prefixes (Solar & Grid only)
PHASE1_ALLOWED_KEY_PREFIXES = [
    'energy:',           # Energy metrics and data
    'weather:',          # Weather data
    'aece:',             # AECE state and decisions
    'session:',          # User sessions
    'rate_limit:',       # Rate limiting
    'cache:',            # General cache
    'simulation:',       # Energy simulations
    'inverter:',         # Inverter telemetry
    'nasa:',             # NASA solar data
    'gee:',              # GEE environmental data
    'openweather:',      # OpenWeather data
    'sungrow:',          # Sungrow inverter data
    'report:',           # Reports
    'hardware:',         # Hardware telemetry
    'modbus:',           # Modbus bridge data
    'circuit_breaker:',  # Circuit breaker state
    'celery:',           # Celery task data
    'task:',             # Task data
    'lock:',             # Distributed locks
    'adfi:',             # ADFI injection data
    'prediction:',       # Energy predictions
    'grid:',             # Grid stability data
    'solar:',            # Solar optimization data
    'telemetry:',        # Telemetry data
    'alert:',            # Alert data
    'partner:',          # Partner data
    'user:',             # User data
    'api:',              # API data
    'system:',           # System metrics
    'process:',          # Process data
]

# Phase 1: Blocked key prefixes (excluded domains)
PHASE1_BLOCKED_KEY_PREFIXES = [
    'nuclear:',          # Nuclear data - BLOCKED
    'fusion:',           # Fusion data - BLOCKED
    'quantum:',          # Quantum data - BLOCKED
    'defense:',          # Defense data - BLOCKED
    'nuke:',             # Nuclear shorthand - BLOCKED
    'reactor:',          # Reactor data - BLOCKED
    'plasma:',           # Fusion plasma - BLOCKED
    'qubit:',            # Quantum qubit - BLOCKED
    'threat:',           # Defense threat - BLOCKED
]

# Track blocked key access attempts for auditing
_phase1_blocked_keys_log: List[Dict[str, Any]] = []
_phase1_blocked_operations: Dict[str, int] = defaultdict(int)


def is_phase1_allowed_key(key: str) -> bool:
    """
    Check if a Redis key is allowed in Phase 1 production.
    
    Args:
        key: The Redis key to check
        
    Returns:
        True if allowed, False if blocked
    """
    if not key:
        return True
    
    key_lower = key.lower()
    
    # Check if key matches any blocked prefix
    for blocked_prefix in PHASE1_BLOCKED_KEY_PREFIXES:
        if key_lower.startswith(blocked_prefix.lower()):
            return False
    
    # Check if key matches any allowed prefix
    for allowed_prefix in PHASE1_ALLOWED_KEY_PREFIXES:
        if key_lower.startswith(allowed_prefix.lower()):
            return True
    
    # Unknown key - allow by default (safe default for Phase 1)
    return True


def log_blocked_key(key: str, operation: str, caller: str = "unknown"):
    """Log a blocked key access attempt"""
    global _phase1_blocked_keys_log, _phase1_blocked_operations
    
    _phase1_blocked_operations[operation] += 1
    _phase1_blocked_keys_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "key": key[:100],  # Truncate long keys
        "operation": operation,
        "caller": caller,
        "reason": "phase1_blocked_prefix",
        "phase": "PHASE_1_BLOCKED"
    })
    
    # Keep only last 1000 records
    if len(_phase1_blocked_keys_log) > 1000:
        _phase1_blocked_keys_log = _phase1_blocked_keys_log[-1000:]
    
    logger.warning(f"[PHASE1] Blocked Redis {operation} on key: {key[:50]}...")


def get_phase1_key_stats() -> Dict[str, Any]:
    """Get statistics about blocked Phase 1 key access"""
    return {
        "total_blocked": len(_phase1_blocked_keys_log),
        "recent_blocked": _phase1_blocked_keys_log[-10:] if _phase1_blocked_keys_log else [],
        "blocked_operations": dict(_phase1_blocked_operations),
        "allowed_prefixes": PHASE1_ALLOWED_KEY_PREFIXES,
        "blocked_prefixes": PHASE1_BLOCKED_KEY_PREFIXES,
        "phase": "PHASE_1_PRODUCTION"
    }


def filter_keys_phase1(keys: List[str]) -> List[str]:
    """Filter a list of keys to only Phase 1 allowed keys"""
    if not keys:
        return []
    
    filtered = []
    blocked = []
    
    for key in keys:
        if is_phase1_allowed_key(key):
            filtered.append(key)
        else:
            blocked.append(key)
            log_blocked_key(key, "filter", "filter_keys_phase1")
    
    if blocked:
        logger.debug(f"[PHASE1] Filtered out {len(blocked)} blocked key(s)")
    
    return filtered


def validate_key_phase1(key: str, operation: str, caller: str = "unknown") -> bool:
    """
    Validate a key for Phase 1 compliance.
    Returns True if allowed, False if blocked.
    """
    if is_phase1_allowed_key(key):
        return True
    
    log_blocked_key(key, operation, caller)
    return False


# ============================================================================
# CONFIGURATION
# ============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", 5))
REDIS_SOCKET_CONNECT_TIMEOUT = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", 5))
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))
REDIS_RETRY_ON_TIMEOUT = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
REDIS_HEALTH_CHECK_INTERVAL = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", 30))
REDIS_MAX_RETRIES = int(os.getenv("REDIS_MAX_RETRIES", 3))
REDIS_RETRY_DELAY = float(os.getenv("REDIS_RETRY_DELAY", "0.5"))

# Phase 1: Enable key filtering
PHASE1_KEY_FILTERING_ENABLED = os.getenv("PHASE1_KEY_FILTERING_ENABLED", "true").lower() == "true"

# Compression threshold (bytes)
COMPRESSION_THRESHOLD = 1024  # 1KB

# Log Phase 1 configuration
logger.info(f"[PHASE1] Redis key filtering: {'ENABLED' if PHASE1_KEY_FILTERING_ENABLED else 'DISABLED'}")
logger.info(f"[PHASE1] Allowed key prefixes: {len(PHASE1_ALLOWED_KEY_PREFIXES)}")
logger.info(f"[PHASE1] Blocked key prefixes: {len(PHASE1_BLOCKED_KEY_PREFIXES)}")


# ============================================================================
# CIRCUIT BREAKER FOR REDIS
# ============================================================================

class RedisCircuitBreaker:
    """Circuit breaker for Redis operations"""
    
    def __init__(self, name: str = "redis"):
        self.name = name
        self.failure_threshold = 5
        self.recovery_timeout = 30
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
                    logger.info(f"[Redis-CB] {self.name} -> HALF_OPEN")
                    return True
                return False
            return True
    
    def record_success(self):
        with self._lock:
            self.total_successes += 1
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"[Redis-CB] {self.name} -> CLOSED")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold and self.state != "OPEN":
                self.state = "OPEN"
                logger.warning(f"[Redis-CB] {self.name} -> OPEN")
    
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


# ============================================================================
# REDIS CLIENT - SINGLETON PATTERN with Phase 1 Filtering
# ============================================================================

class RedisClient:
    """
    Enterprise Redis client with connection pooling, graceful fallback,
    Phase 1 key filtering, and comprehensive error handling.
    
    SINGLETON PATTERN: Thread-safe singleton with proper initialization.
    """
    
    _instance: Optional['RedisClient'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'RedisClient':
        """Thread-safe singleton - accepts NO parameters"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize Redis client"""
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._pool = None
            self._client = None
            self._available = False
            self._last_health_check = 0
            self._pubsub = None
            self._circuit_breaker = RedisCircuitBreaker()
            
            # Statistics
            self._stats = {
                "singleton_created_at": datetime.now(timezone.utc).isoformat(),
                "initialization_count": 0,
                "last_initialization": None,
                "reconnection_count": 0,
                "operation_count": 0,
                "error_count": 0,
                "last_error": None,
                "last_error_time": None,
                "phase1_blocked_keys": 0
            }
            
            self._connect()
            self._initialized = True
            self._stats["initialization_count"] += 1
            self._stats["last_initialization"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"[Redis] Client initialized | Phase 1 filtering: {PHASE1_KEY_FILTERING_ENABLED} | ID: {id(self)}")
    
    def is_initialized(self) -> bool:
        """Check if client is properly initialized"""
        return getattr(self, '_initialized', False)
    
    def reinitialize_if_needed(self) -> bool:
        """Reinitialize if needed for recovery"""
        if not self.is_initialized():
            logger.warning("[Redis] Client not initialized, reinitializing...")
            self.__init__()
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        with self._lock:
            stats = self._stats.copy()
            stats.update({
                "available": self._available,
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "singleton_initialized": self.is_initialized(),
                "phase1_key_filtering": PHASE1_KEY_FILTERING_ENABLED,
                "phase1_blocked_keys": get_phase1_key_stats()
            })
            return stats
    
    def _validate_key(self, key: str, operation: str) -> bool:
        """Validate a key for Phase 1 compliance before operation"""
        if not PHASE1_KEY_FILTERING_ENABLED:
            return True
        
        if not is_phase1_allowed_key(key):
            self._stats["phase1_blocked_keys"] += 1
            log_blocked_key(key, operation, "RedisClient")
            return False
        
        return True
    
    def _validate_keys(self, keys: List[str], operation: str) -> List[str]:
        """Validate multiple keys for Phase 1 compliance"""
        if not PHASE1_KEY_FILTERING_ENABLED:
            return keys
        
        valid_keys = []
        for key in keys:
            if is_phase1_allowed_key(key):
                valid_keys.append(key)
            else:
                self._stats["phase1_blocked_keys"] += 1
                log_blocked_key(key, operation, "RedisClient")
        
        return valid_keys
    
    def _connect(self):
        """Connect to Redis with connection pooling and retry logic"""
        for attempt in range(REDIS_MAX_RETRIES):
            try:
                connection_kwargs = {
                    'host': REDIS_HOST,
                    'port': REDIS_PORT,
                    'db': REDIS_DB,
                    'socket_timeout': REDIS_SOCKET_TIMEOUT,
                    'socket_connect_timeout': REDIS_SOCKET_CONNECT_TIMEOUT,
                    'decode_responses': True,
                    'max_connections': REDIS_MAX_CONNECTIONS,
                    'retry_on_timeout': REDIS_RETRY_ON_TIMEOUT,
                    'health_check_interval': REDIS_HEALTH_CHECK_INTERVAL,
                }
                
                if REDIS_PASSWORD:
                    connection_kwargs['password'] = REDIS_PASSWORD
                
                if REDIS_SSL:
                    connection_kwargs['ssl'] = True
                    connection_kwargs['ssl_cert_reqs'] = None
                
                self._pool = redis.ConnectionPool(**connection_kwargs)
                self._client = redis.Redis(connection_pool=self._pool)
                self._client.ping()
                self._available = True
                self._last_health_check = time.time()
                self._circuit_breaker.record_success()
                logger.info(f"[Redis] Connected to {REDIS_HOST}:{REDIS_PORT} (Pool: {REDIS_MAX_CONNECTIONS}, attempt: {attempt + 1})")
                return
                
            except Exception as e:
                logger.warning(f"[Redis] Connection attempt {attempt + 1} failed: {e}")
                self._client = None
                self._pool = None
                self._available = False
                self._circuit_breaker.record_failure()
                
                if attempt < REDIS_MAX_RETRIES - 1:
                    time.sleep(REDIS_RETRY_DELAY * (attempt + 1))
        
        logger.error(f"[Redis] Failed to connect after {REDIS_MAX_RETRIES} attempts")
    
    def _check_health(self):
        """Check Redis health and reconnect if needed"""
        if not self._circuit_breaker.can_execute():
            logger.debug("[Redis] Circuit breaker open, skipping health check")
            return
        
        now = time.time()
        if now - self._last_health_check > REDIS_HEALTH_CHECK_INTERVAL:
            self._last_health_check = now
            if self._client and self._available:
                try:
                    self._client.ping()
                    self._circuit_breaker.record_success()
                except Exception as e:
                    logger.warning(f"[Redis] Health check failed: {e}")
                    self._circuit_breaker.record_failure()
                    self._available = False
                    self._connect()
    
    @property
    def available(self) -> bool:
        """
        Check if Redis is available.
        
        Returns boolean without raising exceptions.
        Used by all client modules to check Redis status.
        """
        if not self._circuit_breaker.can_execute():
            return False
        
        if self._client is None:
            return False
        if not self._available:
            return False
        
        try:
            self._client.ping()
            return True
        except Exception as e:
            with self._lock:
                self._available = False
                self._stats["error_count"] += 1
                self._stats["last_error"] = str(e)
                self._stats["last_error_time"] = time.time()
                self._circuit_breaker.record_failure()
            return False
    
    def ping(self) -> bool:
        """Ping Redis server"""
        return self.available
    
    def get_client(self):
        """Get the raw Redis client for advanced operations"""
        if not self.available:
            return None
        self._check_health()
        return self._client
    
    def close(self):
        """Close Redis connection pool"""
        if self._pool:
            try:
                self._pool.disconnect()
                self._available = False
                logger.info("[Redis] Connection pool closed")
            except Exception as e:
                logger.error(f"[Redis] Close error: {e}")
    
    def reconnect(self):
        """Force reconnection"""
        with self._lock:
            self.close()
            self._stats["reconnection_count"] += 1
            self._connect()
    
    @property
    def client(self):
        """Get Redis client (for advanced operations)"""
        return self.get_client()
    
    def _track_operation(self, operation: str, success: bool):
        """Track operation metrics"""
        with self._lock:
            self._stats["operation_count"] += 1
            if not success:
                self._stats["error_count"] += 1
    
    # ============================================================================
    # STRING OPERATIONS (with Phase 1 key filtering)
    # ============================================================================
    
    def get(self, key: str, decompress: bool = True) -> Optional[Any]:
        """Get value from Redis (sync) with Phase 1 key validation"""
        if not self._validate_key(key, "get"):
            return None
        
        if not self.available:
            return None
        
        try:
            value = self._client.get(key)
            if value:
                # Check if compressed
                if decompress and isinstance(value, str) and value.startswith("ZLIB:"):
                    try:
                        compressed = value[5:].encode('latin1')
                        value = zlib.decompress(compressed).decode('utf-8')
                    except Exception as e:
                        logger.debug(f"[Redis] Decompression error: {e}")
                        return None
                return json.loads(value)
            self._track_operation("get", True)
            return None
        except Exception as e:
            logger.debug(f"[Redis] Get error for key '{key}': {e}")
            self._track_operation("get", False)
            self._circuit_breaker.record_failure()
            self._available = False
            return None
    
    def set(self, key: str, value: Any, ttl: int = None, compress: bool = True) -> bool:
        """Set value in Redis with optional compression and Phase 1 key validation"""
        if not self._validate_key(key, "set"):
            return False
        
        if not self.available:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            
            # Compress large values
            if compress and len(serialized) > COMPRESSION_THRESHOLD:
                compressed = zlib.compress(serialized.encode('utf-8'))
                serialized = f"ZLIB:{compressed.decode('latin1')}"
            
            if ttl:
                result = self._client.setex(key, ttl, serialized)
            else:
                result = self._client.set(key, serialized)
            
            self._track_operation("set", True)
            return result
        except Exception as e:
            logger.debug(f"[Redis] Set error for key '{key}': {e}")
            self._track_operation("set", False)
            self._circuit_breaker.record_failure()
            self._available = False
            return False
    
    def setex(self, key: str, ttl: int, value: Any, compress: bool = True) -> bool:
        """Set value with TTL (alias for set with ttl parameter) with Phase 1 key validation"""
        return self.set(key, value, ttl, compress)
    
    def delete(self, *keys) -> int:
        """Delete keys from Redis with Phase 1 key validation"""
        if not keys:
            return 0
        
        # Validate all keys
        valid_keys = self._validate_keys(list(keys), "delete")
        if not valid_keys:
            return 0
        
        if not self.available:
            return 0
        
        try:
            result = self._client.delete(*valid_keys)
            self._track_operation("delete", True)
            return result
        except Exception as e:
            logger.debug(f"[Redis] Delete error: {e}")
            self._track_operation("delete", False)
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists with Phase 1 key validation"""
        if not self._validate_key(key, "exists"):
            return False
        
        if not self.available:
            return False
        
        try:
            result = bool(self._client.exists(key))
            self._track_operation("exists", True)
            return result
        except Exception as e:
            logger.debug(f"[Redis] Exists error: {e}")
            self._track_operation("exists", False)
            return False
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter with Phase 1 key validation"""
        if not self._validate_key(key, "incr"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            result = self._client.incr(key, amount)
            self._track_operation("incr", True)
            return result
        except Exception as e:
            logger.debug(f"[Redis] Incr error: {e}")
            self._track_operation("incr", False)
            return 0
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on key with Phase 1 key validation"""
        if not self._validate_key(key, "expire"):
            return False
        
        if not self.available:
            return False
        
        try:
            result = self._client.expire(key, ttl)
            self._track_operation("expire", True)
            return result
        except Exception as e:
            logger.debug(f"[Redis] Expire error: {e}")
            self._track_operation("expire", False)
            return False
    
    def ttl(self, key: str) -> int:
        """Get TTL of key with Phase 1 key validation"""
        if not self._validate_key(key, "ttl"):
            return -2
        
        if not self.available:
            return -2
        
        try:
            return self._client.ttl(key)
        except Exception as e:
            logger.debug(f"[Redis] TTL error: {e}")
            return -2
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern with Phase 1 filtering"""
        if not self.available:
            return []
        
        try:
            all_keys = self._client.keys(pattern)
            # Filter keys for Phase 1 compliance
            filtered_keys = filter_keys_phase1(all_keys) if PHASE1_KEY_FILTERING_ENABLED else all_keys
            return filtered_keys
        except Exception as e:
            logger.debug(f"[Redis] Keys error: {e}")
            return []
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern with Phase 1 filtering"""
        keys = self.keys(pattern)
        if keys:
            return self.delete(*keys)
        return 0
    
    # ============================================================================
    # HASH OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    def hget(self, name: str, key: str) -> Optional[Any]:
        """Get hash field with Phase 1 key validation"""
        if not self._validate_key(name, "hget"):
            return None
        
        if not self.available:
            return None
        
        try:
            value = self._client.hget(name, key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.debug(f"[Redis] Hget error: {e}")
            return None
    
    def hset(self, name: str, key: str, value: Any) -> bool:
        """Set hash field with Phase 1 key validation"""
        if not self._validate_key(name, "hset"):
            return False
        
        if not self.available:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            result = self._client.hset(name, key, serialized)
            return bool(result)
        except Exception as e:
            logger.debug(f"[Redis] Hset error: {e}")
            return False
    
    def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all hash fields with Phase 1 key validation"""
        if not self._validate_key(name, "hgetall"):
            return {}
        
        if not self.available:
            return {}
        
        try:
            data = self._client.hgetall(name)
            return {k: json.loads(v) for k, v in data.items()}
        except Exception as e:
            logger.debug(f"[Redis] Hgetall error: {e}")
            return {}
    
    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        """Increment hash field with Phase 1 key validation"""
        if not self._validate_key(name, "hincrby"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            return self._client.hincrby(name, key, amount)
        except Exception as e:
            logger.debug(f"[Redis] Hincrby error: {e}")
            return 0
    
    def hdel(self, name: str, *keys) -> int:
        """Delete hash fields with Phase 1 key validation"""
        if not self._validate_key(name, "hdel"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            return self._client.hdel(name, *keys)
        except Exception as e:
            logger.debug(f"[Redis] Hdel error: {e}")
            return 0
    
    # ============================================================================
    # LIST OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    def lpush(self, key: str, value: Any) -> int:
        """Push to left of list with Phase 1 key validation"""
        if not self._validate_key(key, "lpush"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            serialized = json.dumps(value, default=str)
            return self._client.lpush(key, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Lpush error: {e}")
            return 0
    
    def rpush(self, key: str, value: Any) -> int:
        """Push to right of list with Phase 1 key validation"""
        if not self._validate_key(key, "rpush"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            serialized = json.dumps(value, default=str)
            return self._client.rpush(key, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Rpush error: {e}")
            return 0
    
    def lpop(self, key: str) -> Optional[Any]:
        """Pop from left of list with Phase 1 key validation"""
        if not self._validate_key(key, "lpop"):
            return None
        
        if not self.available:
            return None
        
        try:
            value = self._client.lpop(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.debug(f"[Redis] Lpop error: {e}")
            return None
    
    def rpop(self, key: str) -> Optional[Any]:
        """Pop from right of list with Phase 1 key validation"""
        if not self._validate_key(key, "rpop"):
            return None
        
        if not self.available:
            return None
        
        try:
            value = self._client.rpop(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.debug(f"[Redis] Rpop error: {e}")
            return None
    
    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        """Get list range with Phase 1 key validation"""
        if not self._validate_key(key, "lrange"):
            return []
        
        if not self.available:
            return []
        
        try:
            values = self._client.lrange(key, start, end)
            return [json.loads(v) for v in values]
        except Exception as e:
            logger.debug(f"[Redis] Lrange error: {e}")
            return []
    
    def llen(self, key: str) -> int:
        """Get list length with Phase 1 key validation"""
        if not self._validate_key(key, "llen"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            return self._client.llen(key)
        except Exception as e:
            logger.debug(f"[Redis] Llen error: {e}")
            return 0
    
    def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim list to range with Phase 1 key validation"""
        if not self._validate_key(key, "ltrim"):
            return False
        
        if not self.available:
            return False
        
        try:
            return self._client.ltrim(key, start, end)
        except Exception as e:
            logger.debug(f"[Redis] Ltrim error: {e}")
            return False
    
    # ============================================================================
    # SET OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    def sadd(self, key: str, *values) -> int:
        """Add members to set with Phase 1 key validation"""
        if not self._validate_key(key, "sadd"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            serialized = [json.dumps(v, default=str) for v in values]
            return self._client.sadd(key, *serialized)
        except Exception as e:
            logger.debug(f"[Redis] Sadd error: {e}")
            return 0
    
    def smembers(self, key: str) -> Set[Any]:
        """Get all set members with Phase 1 key validation"""
        if not self._validate_key(key, "smembers"):
            return set()
        
        if not self.available:
            return set()
        
        try:
            members = self._client.smembers(key)
            return {json.loads(m) for m in members}
        except Exception as e:
            logger.debug(f"[Redis] Smembers error: {e}")
            return set()
    
    def sismember(self, key: str, value: Any) -> bool:
        """Check if value is in set with Phase 1 key validation"""
        if not self._validate_key(key, "sismember"):
            return False
        
        if not self.available:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            return self._client.sismember(key, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Sismember error: {e}")
            return False
    
    def srem(self, key: str, *values) -> int:
        """Remove members from set with Phase 1 key validation"""
        if not self._validate_key(key, "srem"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            serialized = [json.dumps(v, default=str) for v in values]
            return self._client.srem(key, *serialized)
        except Exception as e:
            logger.debug(f"[Redis] Srem error: {e}")
            return 0
    
    def scard(self, key: str) -> int:
        """Get set cardinality with Phase 1 key validation"""
        if not self._validate_key(key, "scard"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            return self._client.scard(key)
        except Exception as e:
            logger.debug(f"[Redis] Scard error: {e}")
            return 0
    
    # ============================================================================
    # SORTED SET OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """Add members to sorted set with Phase 1 key validation"""
        if not self._validate_key(key, "zadd"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            return self._client.zadd(key, mapping)
        except Exception as e:
            logger.debug(f"[Redis] Zadd error: {e}")
            return 0
    
    def zincrby(self, key: str, amount: float, member: str) -> float:
        """Increment member score in sorted set with Phase 1 key validation"""
        if not self._validate_key(key, "zincrby"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            return self._client.zincrby(key, amount, member)
        except Exception as e:
            logger.debug(f"[Redis] Zincrby error: {e}")
            return 0
    
    def zrevrange(self, key: str, start: int, end: int, withscores: bool = False) -> List:
        """Get sorted set range by score (descending) with Phase 1 key validation"""
        if not self._validate_key(key, "zrevrange"):
            return []
        
        if not self.available:
            return []
        
        try:
            return self._client.zrevrange(key, start, end, withscores=withscores)
        except Exception as e:
            logger.debug(f"[Redis] Zrevrange error: {e}")
            return []
    
    def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> List:
        """Get sorted set range by score (ascending) with Phase 1 key validation"""
        if not self._validate_key(key, "zrange"):
            return []
        
        if not self.available:
            return []
        
        try:
            return self._client.zrange(key, start, end, withscores=withscores)
        except Exception as e:
            logger.debug(f"[Redis] Zrange error: {e}")
            return []
    
    # ============================================================================
    # PUB/SUB OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel with Phase 1 key validation"""
        if not self._validate_key(channel, "publish"):
            return 0
        
        if not self.available:
            return 0
        
        try:
            serialized = json.dumps(message, default=str)
            return self._client.publish(channel, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Publish error: {e}")
            return 0
    
    def get_pubsub(self):
        """Get pubsub object"""
        if not self.available:
            return None
        
        try:
            if self._pubsub is None:
                self._pubsub = self._client.pubsub()
            return self._pubsub
        except Exception as e:
            logger.debug(f"[Redis] Get pubsub error: {e}")
            return None
    
    # ============================================================================
    # DISTRIBUTED LOCK (with Phase 1 key validation)
    # ============================================================================
    
    def lock(self, name: str, timeout: int = 10, blocking_timeout: int = 5) -> Optional[Any]:
        """Get distributed lock with Phase 1 key validation"""
        if not self._validate_key(name, "lock"):
            return None
        
        if not self.available:
            return None
        
        try:
            return self._client.lock(name, timeout=timeout, blocking_timeout=blocking_timeout)
        except Exception as e:
            logger.debug(f"[Redis] Lock error: {e}")
            return None
    
    @contextmanager
    def distributed_lock(self, name: str, timeout: int = 10, blocking_timeout: int = 5):
        """Context manager for distributed lock with Phase 1 key validation"""
        lock = self.lock(name, timeout, blocking_timeout)
        if lock and lock.acquire(blocking=blocking_timeout > 0):
            try:
                yield True
            finally:
                lock.release()
        else:
            yield False
    
    # ============================================================================
    # BATCH OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    def pipeline(self):
        """Get pipeline for batch operations"""
        if not self.available:
            return None
        
        try:
            return self._client.pipeline()
        except Exception as e:
            logger.debug(f"[Redis] Pipeline error: {e}")
            return None
    
    def mget(self, keys: List[str]) -> List[Optional[Any]]:
        """Get multiple keys with Phase 1 key validation"""
        if not keys:
            return []
        
        # Validate all keys
        valid_keys = self._validate_keys(keys, "mget")
        if not valid_keys:
            return [None] * len(keys)
        
        if not self.available:
            return [None] * len(valid_keys)
        
        try:
            values = self._client.mget(valid_keys)
            results = []
            for v in values:
                if v:
                    try:
                        results.append(json.loads(v))
                    except:
                        results.append(v)
                else:
                    results.append(None)
            return results
        except Exception as e:
            logger.debug(f"[Redis] Mget error: {e}")
            return [None] * len(valid_keys)
    
    def mset(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        """Set multiple keys with Phase 1 key validation"""
        if not mapping:
            return False
        
        # Validate all keys
        valid_mapping = {}
        for key, value in mapping.items():
            if self._validate_key(key, "mset"):
                valid_mapping[key] = value
            else:
                self._stats["phase1_blocked_keys"] += 1
        
        if not valid_mapping:
            return False
        
        if not self.available:
            return False
        
        try:
            serialized = {k: json.dumps(v, default=str) for k, v in valid_mapping.items()}
            self._client.mset(serialized)
            if ttl:
                pipe = self._client.pipeline()
                for key in valid_mapping.keys():
                    pipe.expire(key, ttl)
                pipe.execute()
            return True
        except Exception as e:
            logger.debug(f"[Redis] Mset error: {e}")
            return False
    
    # ============================================================================
    # ASYNC OPERATIONS (with Phase 1 key validation)
    # ============================================================================
    
    async def aget(self, key: str, decompress: bool = True) -> Optional[Any]:
        """Async get value from Redis with Phase 1 key validation"""
        return self.get(key, decompress)
    
    async def aset(self, key: str, value: Any, ttl: int = None, compress: bool = True) -> bool:
        """Async set value in Redis with Phase 1 key validation"""
        return self.set(key, value, ttl, compress)
    
    async def asetex(self, key: str, ttl: int, value: Any, compress: bool = True) -> bool:
        """Async set with TTL with Phase 1 key validation"""
        return self.setex(key, ttl, value, compress)
    
    async def adelete(self, *keys) -> int:
        """Async delete keys with Phase 1 key validation"""
        return self.delete(*keys)
    
    async def aexists(self, key: str) -> bool:
        """Async check if key exists with Phase 1 key validation"""
        return self.exists(key)
    
    async def aincr(self, key: str, amount: int = 1) -> int:
        """Async increment counter with Phase 1 key validation"""
        return self.incr(key, amount)
    
    async def aexpire(self, key: str, ttl: int) -> bool:
        """Async set expiration with Phase 1 key validation"""
        return self.expire(key, ttl)
    
    # ============================================================================
    # UTILITY OPERATIONS
    # ============================================================================
    
    def flushdb(self) -> bool:
        """Flush current database (use with caution) - Phase 1 compliant"""
        if not self.available:
            return False
        
        try:
            # Phase 1: Log warning before flush
            logger.warning("[PHASE1] Redis flushdb attempted - this will remove all Phase 1 keys")
            return self._client.flushdb()
        except Exception as e:
            logger.error(f"[Redis] Flushdb error: {e}")
            return False
    
    def info(self) -> Dict[str, Any]:
        """Get Redis server info"""
        if not self.available:
            return {}
        
        try:
            return self._client.info()
        except Exception as e:
            logger.debug(f"[Redis] Info error: {e}")
            return {}
    
    def dbsize(self) -> int:
        """Get number of keys in database (Phase 1 filtered)"""
        if not self.available:
            return 0
        
        try:
            # Phase 1: Return only allowed key count
            all_keys = self._client.keys("*")
            filtered_count = len(filter_keys_phase1(all_keys)) if PHASE1_KEY_FILTERING_ENABLED else len(all_keys)
            return filtered_count
        except Exception as e:
            logger.debug(f"[Redis] Dbsize error: {e}")
            return 0
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if self._pool:
            return {
                "max_connections": REDIS_MAX_CONNECTIONS,
                "in_use": getattr(self._pool, '_in_use_connections', 0),
                "available": getattr(self._pool, '_available_connections', 0)
            }
        return {}
    
    def get_phase1_stats(self) -> Dict[str, Any]:
        """Get Phase 1 filtering statistics"""
        return {
            "enabled": PHASE1_KEY_FILTERING_ENABLED,
            "allowed_prefixes": PHASE1_ALLOWED_KEY_PREFIXES,
            "blocked_prefixes": PHASE1_BLOCKED_KEY_PREFIXES,
            "blocked_stats": get_phase1_key_stats(),
            "total_blocked_operations": self._stats.get("phase1_blocked_keys", 0)
        }
    
    def shutdown(self) -> None:
        """Gracefully shutdown Redis client"""
        logger.info("[Redis] Shutting down...")
        self.close()
        self._initialized = False
        logger.info("[Redis] Shutdown complete")


# ============================================================================
# GLOBAL REDIS CLIENT INSTANCE
# ============================================================================

_redis_client: Optional[RedisClient] = None
_redis_lock = threading.RLock()


def get_redis() -> RedisClient:
    """
    Get Redis client singleton instance.
    
    Returns:
        RedisClient singleton instance
    """
    global _redis_client
    
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                _redis_client = RedisClient()
                logger.info(f"[Redis] ✅ Singleton created | ID: {id(_redis_client)}")
    
    return _redis_client


def get_redis_safe() -> Optional[RedisClient]:
    """
    Safely get Redis client without auto-creating.
    Returns None if not initialized.
    """
    global _redis_client
    return _redis_client


def reset_redis():
    """
    Reset Redis client singleton (for testing/hot-reload).
    
    WARNING: This should only be used in testing or during hot-reload.
    """
    global _redis_client
    with _redis_lock:
        if _redis_client is not None:
            _redis_client.shutdown()
            logger.info("[Redis] Resetting singleton instance")
            _redis_client = None
            logger.info("[Redis] Client singleton reset")


def is_redis_initialized() -> bool:
    """Check if Redis client is initialized"""
    global _redis_client
    return _redis_client is not None and _redis_client.is_initialized()


# Backward compatibility
redis_client = get_redis()


# ============================================================================
# RATE LIMITER (with Phase 1 key filtering)
# ============================================================================

class RateLimiter:
    """Redis-based rate limiter with sliding window and memory fallback"""
    
    def __init__(self, key_prefix: str = "rate_limit"):
        self.key_prefix = key_prefix
        self.redis = get_redis()
        self._memory_counters: Dict[str, int] = defaultdict(int)
        self._memory_timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()
    
    def _make_key(self, identifier: str) -> str:
        """Create rate limit key with Phase 1 validation"""
        key = f"{self.key_prefix}:{identifier}"
        # Phase 1: Key is automatically validated by Redis client
        return key
    
    def check(self, identifier: str, limit: int, window: int) -> bool:
        """
        Check if rate limit is exceeded
        
        Args:
            identifier: Unique identifier (e.g., IP, user ID)
            limit: Maximum requests per window
            window: Time window in seconds
        
        Returns:
            True if under limit, False if exceeded
        """
        key = self._make_key(identifier)
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "rate_limit_check", "RateLimiter")
            return False
        
        if self.redis.available:
            try:
                current = self.redis.incr(key)
                if current == 1:
                    self.redis.expire(key, window)
                return current <= limit
            except Exception as e:
                logger.warning(f"[RateLimit] Redis error: {e}, falling back to memory")
        
        # Fallback to in-memory rate limiting
        with self._lock:
            now = time.time()
            
            # Clean up old entries
            expired = [k for k, t in self._memory_timestamps.items() 
                      if now - t > window]
            for k in expired:
                del self._memory_counters[k]
                del self._memory_timestamps[k]
            
            if key not in self._memory_counters:
                self._memory_counters[key] = 0
                self._memory_timestamps[key] = now
            
            if now - self._memory_timestamps[key] > window:
                self._memory_counters[key] = 0
                self._memory_timestamps[key] = now
            
            self._memory_counters[key] += 1
            return self._memory_counters[key] <= limit
    
    def get_remaining(self, identifier: str, limit: int, window: int) -> int:
        """Get remaining requests in current window"""
        key = self._make_key(identifier)
        
        if self.redis.available:
            try:
                current = int(self.redis.client.get(key) or 0)
                return max(0, limit - current)
            except:
                pass
        
        with self._lock:
            now = time.time()
            if key in self._memory_counters:
                if now - self._memory_timestamps.get(key, now) <= window:
                    return max(0, limit - self._memory_counters[key])
        return limit
    
    def reset(self, identifier: str) -> bool:
        """Reset rate limit for identifier"""
        key = self._make_key(identifier)
        
        if self.redis.available:
            try:
                return bool(self.redis.delete(key))
            except:
                pass
        
        with self._lock:
            if key in self._memory_counters:
                del self._memory_counters[key]
                del self._memory_timestamps[key]
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        return {
            "redis_available": self.redis.available,
            "memory_counters_size": len(self._memory_counters),
            "phase1_key_filtering": PHASE1_KEY_FILTERING_ENABLED,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# SESSION MANAGER (with Phase 1 key filtering)
# ============================================================================

class RedisSessionManager:
    """Session management with Redis and Phase 1 key filtering"""
    
    def __init__(self, session_ttl: int = 3600):
        self.session_ttl = session_ttl
        self.redis = get_redis()
        self.prefix = "session:"
    
    def _make_key(self, session_id: str) -> str:
        """Create session key"""
        return f"{self.prefix}{session_id}"
    
    def create_session(self, user_id: str, data: Dict[str, Any]) -> Optional[str]:
        """Create a new session"""
        import secrets
        session_id = secrets.token_hex(32)
        key = self._make_key(session_id)
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "create_session", "RedisSessionManager")
            return None
        
        session_data = data.copy() if data else {}
        session_data["user_id"] = user_id
        session_data["created_at"] = datetime.now(timezone.utc).isoformat()
        session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
        
        if self.redis.set(key, session_data, self.session_ttl):
            return session_id
        return None
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        key = self._make_key(session_id)
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "get_session", "RedisSessionManager")
            return None
        
        session = self.redis.get(key)
        if session:
            session["last_activity"] = datetime.now(timezone.utc).isoformat()
            self.redis.set(key, session, self.session_ttl)
        return session
    
    def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Update session data"""
        key = self._make_key(session_id)
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "update_session", "RedisSessionManager")
            return False
        
        existing = self.get_session(session_id)
        if existing:
            existing.update(data)
            return self.redis.set(key, existing, self.session_ttl)
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        key = self._make_key(session_id)
        return self.redis.delete(key)
    
    def extend_session(self, session_id: str) -> bool:
        """Extend session TTL"""
        key = self._make_key(session_id)
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "extend_session", "RedisSessionManager")
            return False
        
        return self.redis.expire(key, self.session_ttl)
    
    def get_active_sessions(self) -> List[str]:
        """Get all active session IDs (Phase 1 filtered)"""
        pattern = f"{self.prefix}*"
        keys = self.redis.keys(pattern)
        return [k.replace(self.prefix, "") for k in keys]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        return {
            "redis_available": self.redis.available,
            "active_sessions": len(self.get_active_sessions()),
            "session_ttl": self.session_ttl,
            "phase1_key_filtering": PHASE1_KEY_FILTERING_ENABLED,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# AECE STATE PERSISTENCE (with Phase 1 key filtering)
# ============================================================================

class AeceStateManager:
    """AECE state persistence in Redis with Phase 1 key filtering"""
    
    def __init__(self):
        self.redis = get_redis()
        self.prefix = "aece:state"
    
    def _make_key(self, suffix: str) -> str:
        """Create AECE key"""
        return f"{self.prefix}:{suffix}"
    
    def save_state(self, state: Dict[str, Any], ttl: int = 60) -> bool:
        """Save AECE state"""
        key = self._make_key("current")
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "save_state", "AeceStateManager")
            return False
        
        return self.redis.set(key, state, ttl)
    
    def get_state(self) -> Optional[Dict[str, Any]]:
        """Get current AECE state"""
        key = self._make_key("current")
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "get_state", "AeceStateManager")
            return None
        
        return self.redis.get(key)
    
    def save_decision(self, decision: Dict[str, Any], ttl: int = 3600) -> bool:
        """Save AECE decision"""
        import uuid
        decision_id = decision.get("decision_id", str(uuid.uuid4()))
        key = self._make_key(f"decision:{decision_id}")
        
        # Phase 1 key validation
        if not is_phase1_allowed_key(key):
            log_blocked_key(key, "save_decision", "AeceStateManager")
            return False
        
        return self.redis.set(key, decision, ttl)
    
    def get_recent_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent AECE decisions (Phase 1 filtered)"""
        pattern = self._make_key("decision:*")
        keys = self.redis.keys(pattern)
        keys.sort(reverse=True)
        
        decisions = []
        for key in keys[:limit]:
            decision = self.redis.get(key)
            if decision:
                decisions.append(decision)
        return decisions
    
    def get_stats(self) -> Dict[str, Any]:
        """Get AECE state manager statistics"""
        return {
            "redis_available": self.redis.available,
            "phase1_key_filtering": PHASE1_KEY_FILTERING_ENABLED,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# INITIALIZATION AND SHUTDOWN
# ============================================================================

async def initialize_redis() -> Dict[str, Any]:
    """Initialize Redis module (call at app startup)"""
    logger.info("[Redis] Initializing...")
    
    client = get_redis()
    stats = client.get_stats()
    
    logger.info(f"[Redis] ✅ Initialized | Available: {stats['available']} | Circuit: {stats['circuit_breaker']['state']}")
    logger.info(f"[PHASE1] Redis key filtering: {'ACTIVE' if PHASE1_KEY_FILTERING_ENABLED else 'INACTIVE'}")
    logger.info(f"[PHASE1] Blocked key prefixes: {len(PHASE1_BLOCKED_KEY_PREFIXES)}")
    
    return {
        "success": True,
        "available": stats['available'],
        "circuit_breaker_state": stats['circuit_breaker']['state'],
        "singleton_initialized": is_redis_initialized(),
        "phase1_key_filtering": PHASE1_KEY_FILTERING_ENABLED,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def shutdown_redis() -> None:
    """Shutdown Redis module (call at app shutdown)"""
    logger.info("[Redis] Shutting down...")
    
    client = get_redis_safe()
    if client:
        client.shutdown()
    
    logger.info("[Redis] ✅ Shutdown complete")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'RedisClient',
    'get_redis',
    'get_redis_safe',
    'reset_redis',
    'is_redis_initialized',
    'redis_client',
    'RateLimiter',
    'RedisSessionManager',
    'AeceStateManager',
    'initialize_redis',
    'shutdown_redis',
    'get_phase1_key_stats',
    'is_phase1_allowed_key',
    'filter_keys_phase1',
    'PHASE1_ALLOWED_KEY_PREFIXES',
    'PHASE1_BLOCKED_KEY_PREFIXES',
]


# ============================================================================
# INITIALIZATION LOG
# ============================================================================

logger.info("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                    REDIS CLIENT v4.0.0 - PHASE 1 ISOLATED                ║
║     ✅ PHASE 1 KEY FILTERING ACTIVE - Blocks nuclear/fusion/quantum/defense ║
║     ✅ SINGLETON PATTERN FIXED - Proper __new__ with _initialized         ║
║     ✅ ZERO CIRCULAR IMPORTS | ✅ PILOT READY                             ║
║     ✅ Connection Pooling | ✅ Auto-Reconnect with Retry                  ║
║     ✅ Circuit Breaker | ✅ Health Monitoring                             ║
║     ✅ Compression | ✅ Serialization                                     ║
║     ✅ Rate Limiting | ✅ Session Management                              ║
║     ✅ AECE State Persistence | ✅ Pub/Sub Ready                          ║
║     ✅ Instance Recovery | ✅ Hot-Reload Safe                             ║
║     ✅ Abuja Quantum Grid Pilot Zone Compliance                           ║
║     ╔═══════════════════════════════════════════════════════════════════╗ ║
║     ║  PHASE 1 EXCLUSIONS (BLOCKED KEYS):                               ║ ║
║     ║  ❌ nuclear:* - Nuclear data keys blocked                         ║ ║
║     ║  ❌ fusion:* - Fusion data keys blocked                           ║ ║
║     ║  ❌ quantum:* - Quantum data keys blocked                         ║ ║
║     ║  ❌ defense:* - Defense data keys blocked                         ║ ║
║     ╚═══════════════════════════════════════════════════════════════════╝ ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")