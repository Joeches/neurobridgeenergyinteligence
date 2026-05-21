"""
NeuroBridge 11D - Redis Core
Redis connection management for caching, rate limiting, and pub/sub
FULLY FIXED - Professional Enterprise Version with all Redis methods
"""

import os
import redis
import json
import logging
import secrets
import time
from typing import Optional, Any, Dict, List, Set
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("backend.core.redis")

# Redis configuration from environment
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)


class RedisClient:
    """Redis client wrapper with error handling and graceful fallback"""
    
    def __init__(self):
        self._client = None
        self._available = False
        self._connect()
    
    def _connect(self):
        """Connect to Redis"""
        try:
            connection_kwargs = {
                'host': REDIS_HOST,
                'port': REDIS_PORT,
                'db': REDIS_DB,
                'socket_timeout': 5,
                'socket_connect_timeout': 5,
                'decode_responses': True
            }
            
            if REDIS_PASSWORD:
                connection_kwargs['password'] = REDIS_PASSWORD
            
            self._client = redis.Redis(**connection_kwargs)
            self._client.ping()
            self._available = True
            logger.info(f"[REDIS] Connected to {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._client = None
            self._available = False
    
    @property
    def available(self) -> bool:
        """Check if Redis is available"""
        if self._client and self._available:
            try:
                self._client.ping()
                return True
            except:
                self._available = False
        return self._available
    
    def ping(self) -> bool:
        """Ping Redis server"""
        return self.available
    
    def close(self):
        """Close Redis connection"""
        if self._client:
            try:
                self._client.close()
                self._available = False
                logger.info("[REDIS] Connection closed")
            except Exception as e:
                logger.error(f"Redis close error: {e}")
    
    @property
    def client(self):
        """Get Redis client (may be None if unavailable)"""
        if not self.available:
            return None
        return self._client
    
    # ============================================================================
    # STRING OPERATIONS
    # ============================================================================
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis"""
        if not self.available:
            return None
        try:
            value = self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value in Redis"""
        if not self.available:
            return False
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                return self._client.setex(key, ttl, serialized)
            return self._client.set(key, serialized)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from Redis"""
        if not self.available:
            return False
        try:
            return bool(self._client.delete(key))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.available:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        if not self.available:
            return 0
        try:
            return self._client.incr(key, amount)
        except Exception as e:
            logger.error(f"Redis incr error: {e}")
            return 0
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on key"""
        if not self.available:
            return False
        try:
            return self._client.expire(key, ttl)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False
    
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
            logger.error(f"Redis hget error: {e}")
            return None
    
    def hset(self, name: str, key: str, value: Any) -> bool:
        """Set hash field"""
        if not self.available:
            return False
        try:
            serialized = json.dumps(value, default=str)
            return self._client.hset(name, key, serialized)
        except Exception as e:
            logger.error(f"Redis hset error: {e}")
            return False
    
    def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all hash fields"""
        if not self.available:
            return {}
        try:
            data = self._client.hgetall(name)
            return {k: json.loads(v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Redis hgetall error: {e}")
            return {}
    
    def hdel(self, name: str, *keys) -> int:
        """Delete hash fields"""
        if not self.available:
            return 0
        try:
            return self._client.hdel(name, *keys)
        except Exception as e:
            logger.error(f"Redis hdel error: {e}")
            return 0
    
    def hexists(self, name: str, key: str) -> bool:
        """Check if hash field exists"""
        if not self.available:
            return False
        try:
            return self._client.hexists(name, key)
        except Exception as e:
            logger.error(f"Redis hexists error: {e}")
            return False
    
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
            logger.error(f"Redis lpush error: {e}")
            return 0
    
    def rpush(self, key: str, value: Any) -> int:
        """Push to right of list"""
        if not self.available:
            return 0
        try:
            serialized = json.dumps(value, default=str)
            return self._client.rpush(key, serialized)
        except Exception as e:
            logger.error(f"Redis rpush error: {e}")
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
            logger.error(f"Redis lpop error: {e}")
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
            logger.error(f"Redis rpop error: {e}")
            return None
    
    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        """Get list range"""
        if not self.available:
            return []
        try:
            values = self._client.lrange(key, start, end)
            return [json.loads(v) for v in values]
        except Exception as e:
            logger.error(f"Redis lrange error: {e}")
            return []
    
    def llen(self, key: str) -> int:
        """Get list length"""
        if not self.available:
            return 0
        try:
            return self._client.llen(key)
        except Exception as e:
            logger.error(f"Redis llen error: {e}")
            return 0
    
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
            logger.error(f"Redis sadd error: {e}")
            return 0
    
    def smembers(self, key: str) -> Set[Any]:
        """Get all set members"""
        if not self.available:
            return set()
        try:
            members = self._client.smembers(key)
            return {json.loads(m) for m in members}
        except Exception as e:
            logger.error(f"Redis smembers error: {e}")
            return set()
    
    def sismember(self, key: str, value: Any) -> bool:
        """Check if value is in set"""
        if not self.available:
            return False
        try:
            serialized = json.dumps(value, default=str)
            return self._client.sismember(key, serialized)
        except Exception as e:
            logger.error(f"Redis sismember error: {e}")
            return False
    
    def srem(self, key: str, *values) -> int:
        """Remove members from set"""
        if not self.available:
            return 0
        try:
            serialized = [json.dumps(v, default=str) for v in values]
            return self._client.srem(key, *serialized)
        except Exception as e:
            logger.error(f"Redis srem error: {e}")
            return 0
    
    def scard(self, key: str) -> int:
        """Get set cardinality"""
        if not self.available:
            return 0
        try:
            return self._client.scard(key)
        except Exception as e:
            logger.error(f"Redis scard error: {e}")
            return 0
    
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
            logger.error(f"Redis publish error: {e}")
            return 0
    
    def subscribe(self, channel: str):
        """Subscribe to channel (returns pubsub object)"""
        if not self.available:
            return None
        try:
            pubsub = self._client.pubsub()
            pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.error(f"Redis subscribe error: {e}")
            return None
    
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
            logger.error(f"Redis flushdb error: {e}")
            return False
    
    def info(self) -> Dict[str, Any]:
        """Get Redis server info"""
        if not self.available:
            return {}
        try:
            return self._client.info()
        except Exception as e:
            logger.error(f"Redis info error: {e}")
            return {}


# Global Redis client instance
redis_client = RedisClient()


def get_redis() -> RedisClient:
    """Get Redis client instance"""
    return redis_client


class RateLimiter:
    """Redis-based rate limiter with fallback to in-memory"""
    
    def __init__(self, key_prefix: str = "rate_limit"):
        self.key_prefix = key_prefix
        self.redis = redis_client
        self._memory_counters = {}
        self._memory_timestamps = {}
    
    def check(self, identifier: str, limit: int, window: int) -> bool:
        """Check if rate limit is exceeded"""
        key = f"{self.key_prefix}:{identifier}"
        
        if self.redis.available:
            try:
                current = self.redis.incr(key)
                if current == 1:
                    self.redis.expire(key, window)
                return current <= limit
            except Exception as e:
                logger.warning(f"Redis rate limit error: {e}, falling back to memory")
        
        # Fallback to in-memory rate limiting
        now = time.time()
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
        
        now = time.time()
        if key in self._memory_counters:
            if now - self._memory_timestamps.get(key, now) <= window:
                return max(0, limit - self._memory_counters[key])
        return limit


class RedisSessionManager:
    """Session management with Redis"""
    
    def __init__(self, session_ttl: int = 3600):
        self.session_ttl = session_ttl
        self.redis = redis_client
        self.prefix = "session:"
    
    def create_session(self, user_id: str, data: Dict[str, Any]) -> str:
        """Create a new session"""
        session_id = secrets.token_hex(32)
        key = f"{self.prefix}{session_id}"
        
        session_data = data.copy() if data else {}
        session_data["user_id"] = user_id
        session_data["created_at"] = datetime.now(timezone.utc).isoformat()
        
        self.redis.set(key, session_data, self.session_ttl)
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        key = f"{self.prefix}{session_id}"
        return self.redis.get(key)
    
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


# Simple synchronous cache decorator (not async)
def cache(ttl: int = 300, key_prefix: str = None):
    """Synchronous cache decorator for functions"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = key_prefix or f"{func.__module__}:{func.__name__}"
            if args:
                cache_key += f":{':'.join(str(a) for a in args)}"
            if kwargs:
                cache_key += f":{':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))}"
            
            # Try to get from cache
            cached = redis_client.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            redis_client.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator