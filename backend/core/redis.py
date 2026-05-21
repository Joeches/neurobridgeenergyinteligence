
import os
import redis
import json
import logging
import secrets
import time
import zlib
import asyncio
import threading
import hashlib
from typing import Optional, Any, Dict, List, Set, Union, Callable, Awaitable
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone, timedelta
from functools import wraps
from collections import defaultdict
from enum import Enum

logger = logging.getLogger("NeuroBridge.Redis")

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

# Compression threshold (bytes)
COMPRESSION_THRESHOLD = 1024  # 1KB


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
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"[Redis-CB] {self.name} -> CLOSED")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold and self.state != "OPEN":
                self.state = "OPEN"
                logger.warning(f"[Redis-CB] {self.name} -> OPEN")
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout
            }


# ============================================================================
# REDIS CLIENT - FULLY FIXED WITH SINGLETON PATTERN
# ============================================================================

class RedisClient:
    """
    Enterprise Redis client with connection pooling, graceful fallback,
    and comprehensive error handling.
    
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
                "last_error_time": None
            }
            
            self._connect()
            self._initialized = True
            self._stats["initialization_count"] += 1
            self._stats["last_initialization"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"[Redis] Client initialized | ID: {id(self)}")
    
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
                "singleton_initialized": self.is_initialized()
            })
            return stats
    
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
        """
        Get the raw Redis client for advanced operations.
        
        Returns None if Redis is unavailable.
        """
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
    # STRING OPERATIONS
    # ============================================================================
    
    def get(self, key: str, decompress: bool = True) -> Optional[Any]:
        """Get value from Redis (sync)"""
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
        """Set value in Redis with optional compression (sync)"""
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
        """Set value with TTL (alias for set with ttl parameter)"""
        return self.set(key, value, ttl, compress)
    
    def delete(self, *keys) -> int:
        """Delete keys from Redis"""
        if not self.available:
            return 0
        
        try:
            result = self._client.delete(*keys)
            self._track_operation("delete", True)
            return result
        except Exception as e:
            logger.debug(f"[Redis] Delete error: {e}")
            self._track_operation("delete", False)
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
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
        """Increment counter"""
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
        """Set expiration on key"""
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
        """Get TTL of key"""
        if not self.available:
            return -2
        
        try:
            return self._client.ttl(key)
        except Exception as e:
            logger.debug(f"[Redis] TTL error: {e}")
            return -2
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern"""
        if not self.available:
            return []
        
        try:
            return self._client.keys(pattern)
        except Exception as e:
            logger.debug(f"[Redis] Keys error: {e}")
            return []
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern"""
        keys = self.keys(pattern)
        if keys:
            return self.delete(*keys)
        return 0
    
    # ============================================================================
    # HASH OPERATIONS
    # ============================================================================
    
    def hget(self, name: str, key: str) -> Optional[Any]:
        """Get hash field"""
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
        """Set hash field"""
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
        """Get all hash fields"""
        if not self.available:
            return {}
        
        try:
            data = self._client.hgetall(name)
            return {k: json.loads(v) for k, v in data.items()}
        except Exception as e:
            logger.debug(f"[Redis] Hgetall error: {e}")
            return {}
    
    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        """Increment hash field"""
        if not self.available:
            return 0
        
        try:
            return self._client.hincrby(name, key, amount)
        except Exception as e:
            logger.debug(f"[Redis] Hincrby error: {e}")
            return 0
    
    def hdel(self, name: str, *keys) -> int:
        """Delete hash fields"""
        if not self.available:
            return 0
        
        try:
            return self._client.hdel(name, *keys)
        except Exception as e:
            logger.debug(f"[Redis] Hdel error: {e}")
            return 0
    
    # ============================================================================
    # LIST OPERATIONS
    # ============================================================================
    
    def lpush(self, key: str, value: Any) -> int:
        """Push to left of list"""
        if not self.available:
            return 0
        
        try:
            serialized = json.dumps(value, default=str)
            return self._client.lpush(key, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Lpush error: {e}")
            return 0
    
    def rpush(self, key: str, value: Any) -> int:
        """Push to right of list"""
        if not self.available:
            return 0
        
        try:
            serialized = json.dumps(value, default=str)
            return self._client.rpush(key, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Rpush error: {e}")
            return 0
    
    def lpop(self, key: str) -> Optional[Any]:
        """Pop from left of list"""
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
        """Pop from right of list"""
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
        """Get list range"""
        if not self.available:
            return []
        
        try:
            values = self._client.lrange(key, start, end)
            return [json.loads(v) for v in values]
        except Exception as e:
            logger.debug(f"[Redis] Lrange error: {e}")
            return []
    
    def llen(self, key: str) -> int:
        """Get list length"""
        if not self.available:
            return 0
        
        try:
            return self._client.llen(key)
        except Exception as e:
            logger.debug(f"[Redis] Llen error: {e}")
            return 0
    
    def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim list to range"""
        if not self.available:
            return False
        
        try:
            return self._client.ltrim(key, start, end)
        except Exception as e:
            logger.debug(f"[Redis] Ltrim error: {e}")
            return False
    
    # ============================================================================
    # SET OPERATIONS
    # ============================================================================
    
    def sadd(self, key: str, *values) -> int:
        """Add members to set"""
        if not self.available:
            return 0
        
        try:
            serialized = [json.dumps(v, default=str) for v in values]
            return self._client.sadd(key, *serialized)
        except Exception as e:
            logger.debug(f"[Redis] Sadd error: {e}")
            return 0
    
    def smembers(self, key: str) -> Set[Any]:
        """Get all set members"""
        if not self.available:
            return set()
        
        try:
            members = self._client.smembers(key)
            return {json.loads(m) for m in members}
        except Exception as e:
            logger.debug(f"[Redis] Smembers error: {e}")
            return set()
    
    def sismember(self, key: str, value: Any) -> bool:
        """Check if value is in set"""
        if not self.available:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            return self._client.sismember(key, serialized)
        except Exception as e:
            logger.debug(f"[Redis] Sismember error: {e}")
            return False
    
    def srem(self, key: str, *values) -> int:
        """Remove members from set"""
        if not self.available:
            return 0
        
        try:
            serialized = [json.dumps(v, default=str) for v in values]
            return self._client.srem(key, *serialized)
        except Exception as e:
            logger.debug(f"[Redis] Srem error: {e}")
            return 0
    
    def scard(self, key: str) -> int:
        """Get set cardinality"""
        if not self.available:
            return 0
        
        try:
            return self._client.scard(key)
        except Exception as e:
            logger.debug(f"[Redis] Scard error: {e}")
            return 0
    
    # ============================================================================
    # SORTED SET OPERATIONS
    # ============================================================================
    
    def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """Add members to sorted set"""
        if not self.available:
            return 0
        
        try:
            return self._client.zadd(key, mapping)
        except Exception as e:
            logger.debug(f"[Redis] Zadd error: {e}")
            return 0
    
    def zincrby(self, key: str, amount: float, member: str) -> float:
        """Increment member score in sorted set"""
        if not self.available:
            return 0
        
        try:
            return self._client.zincrby(key, amount, member)
        except Exception as e:
            logger.debug(f"[Redis] Zincrby error: {e}")
            return 0
    
    def zrevrange(self, key: str, start: int, end: int, withscores: bool = False) -> List:
        """Get sorted set range by score (descending)"""
        if not self.available:
            return []
        
        try:
            return self._client.zrevrange(key, start, end, withscores=withscores)
        except Exception as e:
            logger.debug(f"[Redis] Zrevrange error: {e}")
            return []
    
    def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> List:
        """Get sorted set range by score (ascending)"""
        if not self.available:
            return []
        
        try:
            return self._client.zrange(key, start, end, withscores=withscores)
        except Exception as e:
            logger.debug(f"[Redis] Zrange error: {e}")
            return []
    
    # ============================================================================
    # PUB/SUB OPERATIONS
    # ============================================================================
    
    def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel"""
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
    # DISTRIBUTED LOCK
    # ============================================================================
    
    def lock(self, name: str, timeout: int = 10, blocking_timeout: int = 5) -> Optional[Any]:
        """Get distributed lock"""
        if not self.available:
            return None
        
        try:
            return self._client.lock(name, timeout=timeout, blocking_timeout=blocking_timeout)
        except Exception as e:
            logger.debug(f"[Redis] Lock error: {e}")
            return None
    
    @contextmanager
    def distributed_lock(self, name: str, timeout: int = 10, blocking_timeout: int = 5):
        """Context manager for distributed lock"""
        lock = self.lock(name, timeout, blocking_timeout)
        if lock and lock.acquire(blocking=blocking_timeout > 0):
            try:
                yield True
            finally:
                lock.release()
        else:
            yield False
    
    # ============================================================================
    # BATCH OPERATIONS
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
        """Get multiple keys"""
        if not self.available:
            return [None] * len(keys)
        
        try:
            values = self._client.mget(keys)
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
            return [None] * len(keys)
    
    def mset(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        """Set multiple keys"""
        if not self.available:
            return False
        
        try:
            serialized = {k: json.dumps(v, default=str) for k, v in mapping.items()}
            self._client.mset(serialized)
            if ttl:
                pipe = self._client.pipeline()
                for key in mapping.keys():
                    pipe.expire(key, ttl)
                pipe.execute()
            return True
        except Exception as e:
            logger.debug(f"[Redis] Mset error: {e}")
            return False
    
    # ============================================================================
    # ASYNC OPERATIONS (for compatibility with async clients)
    # ============================================================================
    
    async def aget(self, key: str, decompress: bool = True) -> Optional[Any]:
        """Async get value from Redis"""
        return self.get(key, decompress)
    
    async def aset(self, key: str, value: Any, ttl: int = None, compress: bool = True) -> bool:
        """Async set value in Redis"""
        return self.set(key, value, ttl, compress)
    
    async def asetex(self, key: str, ttl: int, value: Any, compress: bool = True) -> bool:
        """Async set with TTL"""
        return self.setex(key, ttl, value, compress)
    
    async def adelete(self, *keys) -> int:
        """Async delete keys"""
        return self.delete(*keys)
    
    async def aexists(self, key: str) -> bool:
        """Async check if key exists"""
        return self.exists(key)
    
    async def aincr(self, key: str, amount: int = 1) -> int:
        """Async increment counter"""
        return self.incr(key, amount)
    
    async def aexpire(self, key: str, ttl: int) -> bool:
        """Async set expiration"""
        return self.expire(key, ttl)
    
    # ============================================================================
    # UTILITY OPERATIONS
    # ============================================================================
    
    def flushdb(self) -> bool:
        """Flush current database (use with caution)"""
        if not self.available:
            return False
        
        try:
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
        """Get number of keys in database"""
        if not self.available:
            return 0
        
        try:
            return self._client.dbsize()
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
# CACHE DECORATORS
# ============================================================================

def cache(ttl: int = 300, key_prefix: str = None, cache_none: bool = False, compress: bool = True):
    """
    Enterprise-grade cache decorator with Redis
    
    Usage:
        @cache(ttl=3600, key_prefix="kernel")
        def expensive_function(param):
            return result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = key_prefix or f"{func.__module__}:{func.__name__}"
            
            # Create key from args and kwargs
            key_parts = [str(arg) for arg in args]
            key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
            
            if key_parts:
                key_hash = hashlib.md5(":".join(key_parts).encode()).hexdigest()[:16]
                cache_key = f"{cache_key}:{key_hash}"
            
            # Try to get from cache
            cached = redis_client.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            if result is not None or cache_none:
                redis_client.set(cache_key, result, ttl, compress)
                logger.debug(f"Cache set: {cache_key} (TTL: {ttl}s)")
            
            return result
        return wrapper
    return decorator


def acache(ttl: int = 300, key_prefix: str = None, cache_none: bool = False, compress: bool = True):
    """Async cache decorator for coroutines"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = key_prefix or f"{func.__module__}:{func.__name__}"
            
            # Create key from args and kwargs
            key_parts = [str(arg) for arg in args]
            key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
            
            if key_parts:
                key_hash = hashlib.md5(":".join(key_parts).encode()).hexdigest()[:16]
                cache_key = f"{cache_key}:{key_hash}"
            
            # Try to get from cache
            cached = redis_client.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            if result is not None or cache_none:
                redis_client.set(cache_key, result, ttl, compress)
            
            return result
        return wrapper
    return decorator


# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    """Redis-based rate limiter with sliding window"""
    
    def __init__(self, key_prefix: str = "rate_limit"):
        self.key_prefix = key_prefix
        self.redis = get_redis()
        self._memory_counters: Dict[str, int] = defaultdict(int)
        self._memory_timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()
    
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
        key = f"{self.key_prefix}:{identifier}"
        
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
        key = f"{self.key_prefix}:{identifier}"
        
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
        key = f"{self.key_prefix}:{identifier}"
        
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


# ============================================================================
# ANALYTICS COUNTERS
# ============================================================================

class AnalyticsCounter:
    """Redis-based analytics counters for production metrics"""
    
    def __init__(self):
        self.redis = get_redis()
        self.prefix = "analytics"
        self._memory_counters: Dict[str, int] = defaultdict(int)
    
    def increment(self, metric: str, amount: int = 1) -> int:
        """Increment analytics counter"""
        key = f"{self.prefix}:{metric}"
        if self.redis.available:
            return self.redis.incr(key, amount)
        
        # Fallback to memory
        self._memory_counters[metric] += amount
        return self._memory_counters[metric]
    
    def get(self, metric: str) -> int:
        """Get analytics counter value"""
        key = f"{self.prefix}:{metric}"
        if self.redis.available:
            val = self.redis.get(key)
            return int(val) if val else 0
        return self._memory_counters.get(metric, 0)
    
    def increment_api_call(self, endpoint: str) -> int:
        """Increment API call counter"""
        return self.increment(f"api:{endpoint}")
    
    def increment_kernel_calculation(self, sector: str) -> int:
        """Increment kernel calculation counter"""
        return self.increment(f"kernel:{sector}")
    
    def increment_adfi_injection(self, sector: str, pattern: str) -> int:
        """Increment ADFI injection counter"""
        return self.increment(f"adfi:{sector}:{pattern}")
    
    def increment_aece_action(self, action: str, priority: str) -> int:
        """Increment AECE action counter"""
        return self.increment(f"aece:{action}:{priority}")
    
    def increment_error(self, error_type: str) -> int:
        """Increment error counter"""
        return self.increment(f"error:{error_type}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get all analytics stats"""
        if self.redis.available:
            try:
                keys = self.redis.keys(f"{self.prefix}:*")
                stats = {}
                for key in keys:
                    name = key.replace(f"{self.prefix}:", "")
                    stats[name] = int(self.redis.get(key) or 0)
                return stats
            except Exception:
                pass
        return dict(self._memory_counters)


# ============================================================================
# SESSION MANAGER
# ============================================================================

class RedisSessionManager:
    """Session management with Redis"""
    
    def __init__(self, session_ttl: int = 3600):
        self.session_ttl = session_ttl
        self.redis = get_redis()
        self.prefix = "session:"
    
    def create_session(self, user_id: str, data: Dict[str, Any]) -> str:
        """Create a new session"""
        session_id = secrets.token_hex(32)
        key = f"{self.prefix}{session_id}"
        
        session_data = data.copy() if data else {}
        session_data["user_id"] = user_id
        session_data["created_at"] = datetime.now(timezone.utc).isoformat()
        session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
        
        self.redis.set(key, session_data, self.session_ttl)
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        key = f"{self.prefix}{session_id}"
        session = self.redis.get(key)
        if session:
            session["last_activity"] = datetime.now(timezone.utc).isoformat()
            self.redis.set(key, session, self.session_ttl)
        return session
    
    def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Update session data"""
        key = f"{self.prefix}{session_id}"
        existing = self.get_session(session_id)
        if existing:
            existing.update(data)
            return self.redis.set(key, existing, self.session_ttl)
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        key = f"{self.prefix}{session_id}"
        return self.redis.delete(key)
    
    def extend_session(self, session_id: str) -> bool:
        """Extend session TTL"""
        key = f"{self.prefix}{session_id}"
        return self.redis.expire(key, self.session_ttl)
    
    def get_active_sessions(self) -> List[str]:
        """Get all active session IDs"""
        pattern = f"{self.prefix}*"
        keys = self.redis.keys(pattern)
        return [k.replace(self.prefix, "") for k in keys]


# ============================================================================
# AECE STATE PERSISTENCE
# ============================================================================

class AeceStateManager:
    """AECE state persistence in Redis"""
    
    def __init__(self):
        self.redis = get_redis()
        self.prefix = "aece:state"
    
    def save_state(self, state: Dict[str, Any], ttl: int = 60) -> bool:
        """Save AECE state"""
        key = f"{self.prefix}:current"
        return self.redis.set(key, state, ttl)
    
    def get_state(self) -> Optional[Dict[str, Any]]:
        """Get current AECE state"""
        key = f"{self.prefix}:current"
        return self.redis.get(key)
    
    def save_decision(self, decision: Dict[str, Any], ttl: int = 3600) -> bool:
        """Save AECE decision"""
        import uuid
        decision_id = decision.get("decision_id", str(uuid.uuid4()))
        key = f"{self.prefix}:decision:{decision_id}"
        return self.redis.set(key, decision, ttl)
    
    def get_recent_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent AECE decisions"""
        pattern = f"{self.prefix}:decision:*"
        keys = self.redis.keys(pattern)
        keys.sort(reverse=True)
        
        decisions = []
        for key in keys[:limit]:
            decision = self.redis.get(key)
            if decision:
                decisions.append(decision)
        return decisions


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

rate_limiter = RateLimiter()
analytics_counter = AnalyticsCounter()
session_manager = RedisSessionManager()
aece_state_manager = AeceStateManager()


# ============================================================================
# INITIALIZATION AND SHUTDOWN
# ============================================================================

async def initialize_redis() -> Dict[str, Any]:
    """Initialize Redis module (call at app startup)"""
    logger.info("[Redis] Initializing...")
    
    client = get_redis()
    stats = client.get_stats()
    
    logger.info(f"[Redis] ✅ Initialized | Available: {stats['available']} | Circuit: {stats['circuit_breaker']['state']}")
    
    return {
        "success": True,
        "available": stats['available'],
        "circuit_breaker_state": stats['circuit_breaker']['state'],
        "singleton_initialized": is_redis_initialized(),
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
    'cache',
    'acache',
    'RateLimiter',
    'AnalyticsCounter',
    'RedisSessionManager',
    'AeceStateManager',
    'rate_limiter',
    'analytics_counter',
    'session_manager',
    'aece_state_manager',
    'initialize_redis',
    'shutdown_redis'
]