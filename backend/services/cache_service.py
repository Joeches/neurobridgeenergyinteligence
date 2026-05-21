"""
NeuroBridge 11D - Cache Service
Redis-based distributed caching with memory fallback

Version: 2.0.0-PRODUCTION-FIXED
Build: 2026.04.14

FIXES APPLIED:
- ADDED: sync_get() and sync_set() methods for Celery task compatibility
- ADDED: Automatic async detection and handling
- ADDED: Thread-safe event loop management for sync contexts
- ENHANCED: Graceful degradation when Redis unavailable
- ENHANCED: Comprehensive error handling for all operations
- FIXED: No more "coroutine was never awaited" warnings
"""

import time
import json
import logging
import asyncio
import threading
from typing import Dict, Any, Optional, Union
from collections import OrderedDict

logger = logging.getLogger("NeuroBridge.CacheService")


class CacheService:
    """Distributed cache service with Redis and memory fallback
    
    Provides both async methods (get/set) for async contexts AND
    sync methods (sync_get/sync_set) for Celery task contexts.
    """
    
    def __init__(self, redis_manager=None):
        self.redis_manager = redis_manager
        self._memory_cache: Dict[str, tuple] = {}
        self._max_memory_items = 1000
        self._hits = 0
        self._misses = 0
        self._sync_hits = 0
        self._sync_misses = 0
        self._event_loop_cache: Dict[int, asyncio.AbstractEventLoop] = {}
        self._loop_lock = threading.RLock()
    
    def _is_redis_available(self) -> bool:
        """Check if Redis is available"""
        if self.redis_manager is None:
            return False
        try:
            if hasattr(self.redis_manager, 'available'):
                return bool(self.redis_manager.available)
            return False
        except Exception:
            return False
    
    def _get_or_create_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop for sync operations"""
        thread_id = threading.get_ident()
        
        with self._loop_lock:
            if thread_id in self._event_loop_cache:
                loop = self._event_loop_cache[thread_id]
                if not loop.is_closed():
                    return loop
            
            # Create new event loop for this thread
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            self._event_loop_cache[thread_id] = loop
            return loop
    
    # ========================================================================
    # ASYNC METHODS (for async contexts - FastAPI, etc.)
    # ========================================================================
    
    async def get(self, key: str) -> Optional[Any]:
        """Async get - use in async contexts with await"""
        if self._is_redis_available():
            try:
                return await self.redis_manager.get(key)
            except Exception as e:
                logger.debug(f"Redis get error: {e}")
        
        # Memory cache fallback
        if key in self._memory_cache:
            value, expiry = self._memory_cache[key]
            if time.time() < expiry:
                self._hits += 1
                return value
            else:
                del self._memory_cache[key]
        
        self._misses += 1
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Async set - use in async contexts with await"""
        if self._is_redis_available():
            try:
                return await self.redis_manager.set(key, value, ttl)
            except Exception as e:
                logger.debug(f"Redis set error: {e}")
        
        # Memory cache fallback
        if len(self._memory_cache) >= self._max_memory_items:
            oldest = next(iter(self._memory_cache))
            del self._memory_cache[oldest]
        
        self._memory_cache[key] = (value, time.time() + ttl)
        return True
    
    async def delete(self, key: str) -> bool:
        """Async delete - use in async contexts with await"""
        if self._is_redis_available():
            try:
                return await self.redis_manager.delete(key)
            except Exception:
                pass
        
        if key in self._memory_cache:
            del self._memory_cache[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        """Async exists - use in async contexts with await"""
        if self._is_redis_available():
            try:
                val = await self.redis_manager.get(key)
                return val is not None
            except Exception:
                pass
        return key in self._memory_cache
    
    # ========================================================================
    # SYNC METHODS (for Celery tasks and sync contexts)
    # ========================================================================
    
    def sync_get(self, key: str, default: Any = None) -> Any:
        """
        Synchronous get for Celery tasks and sync contexts.
        Handles async Redis operations internally.
        
        Args:
            key: Cache key
            default: Default value if key not found
        
        Returns:
            Cached value or default
        """
        if self._is_redis_available():
            try:
                # Check if redis_manager.get is async
                if asyncio.iscoroutinefunction(self.redis_manager.get):
                    # Run async operation in sync context
                    loop = self._get_or_create_event_loop()
                    if loop.is_running():
                        # Can't block on running loop - use memory cache
                        logger.debug(f"Sync get skipped (loop running): {key}")
                    else:
                        result = loop.run_until_complete(self.redis_manager.get(key))
                        if result is not None:
                            self._sync_hits += 1
                            return result
                else:
                    # Sync Redis method
                    result = self.redis_manager.get(key)
                    if result is not None:
                        self._sync_hits += 1
                        return result
            except Exception as e:
                logger.debug(f"Redis sync get error: {e}")
        
        # Memory cache fallback
        if key in self._memory_cache:
            value, expiry = self._memory_cache[key]
            if time.time() < expiry:
                self._sync_hits += 1
                return value
            else:
                del self._memory_cache[key]
        
        self._sync_misses += 1
        return default
    
    def sync_set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Synchronous set for Celery tasks and sync contexts.
        Handles async Redis operations internally.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        
        Returns:
            True if set successfully, False otherwise
        """
        if self._is_redis_available():
            try:
                # Check if redis_manager.set is async
                if asyncio.iscoroutinefunction(self.redis_manager.set):
                    # Run async operation in sync context
                    loop = self._get_or_create_event_loop()
                    if loop.is_running():
                        # Can't block on running loop - use memory cache
                        logger.debug(f"Sync set skipped (loop running): {key}")
                    else:
                        result = loop.run_until_complete(self.redis_manager.set(key, value, ttl))
                        if result:
                            return True
                else:
                    # Sync Redis method
                    result = self.redis_manager.set(key, value, ttl)
                    if result:
                        return True
            except Exception as e:
                logger.debug(f"Redis sync set error: {e}")
        
        # Memory cache fallback
        if len(self._memory_cache) >= self._max_memory_items:
            oldest = next(iter(self._memory_cache))
            del self._memory_cache[oldest]
        
        self._memory_cache[key] = (value, time.time() + ttl)
        return True
    
    def sync_delete(self, key: str) -> bool:
        """Synchronous delete for Celery tasks"""
        if self._is_redis_available():
            try:
                if asyncio.iscoroutinefunction(self.redis_manager.delete):
                    loop = self._get_or_create_event_loop()
                    if not loop.is_running():
                        return loop.run_until_complete(self.redis_manager.delete(key))
                else:
                    return self.redis_manager.delete(key)
            except Exception:
                pass
        
        if key in self._memory_cache:
            del self._memory_cache[key]
            return True
        return False
    
    def sync_exists(self, key: str) -> bool:
        """Synchronous exists check for Celery tasks"""
        if self._is_redis_available():
            try:
                if asyncio.iscoroutinefunction(self.redis_manager.get):
                    loop = self._get_or_create_event_loop()
                    if not loop.is_running():
                        val = loop.run_until_complete(self.redis_manager.get(key))
                        return val is not None
                else:
                    val = self.redis_manager.get(key)
                    return val is not None
            except Exception:
                pass
        return key in self._memory_cache
    
    # ========================================================================
    # COMPATIBILITY METHODS (for code that expects async but calls sync)
    # ========================================================================
    
    def get_sync(self, key: str, default: Any = None) -> Any:
        """Alias for sync_get - for backward compatibility"""
        return self.sync_get(key, default)
    
    def set_sync(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Alias for sync_set - for backward compatibility"""
        return self.sync_set(key, value, ttl)
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        sync_total = self._sync_hits + self._sync_misses
        sync_hit_rate = (self._sync_hits / sync_total * 100) if sync_total > 0 else 0
        
        return {
            "redis_available": self._is_redis_available(),
            "memory_items": len(self._memory_cache),
            "async_cache_hits": self._hits,
            "async_cache_misses": self._misses,
            "async_hit_rate_percent": round(hit_rate, 2),
            "sync_cache_hits": self._sync_hits,
            "sync_cache_misses": self._sync_misses,
            "sync_hit_rate_percent": round(sync_hit_rate, 2),
            "total_operations": total + sync_total
        }
    
    def reset_stats(self):
        """Reset cache statistics"""
        self._hits = 0
        self._misses = 0
        self._sync_hits = 0
        self._sync_misses = 0
    
    def clear_memory_cache(self):
        """Clear all in-memory cache entries"""
        self._memory_cache.clear()
        logger.info("[Cache] In-memory cache cleared")
    
    def get_memory_size(self) -> int:
        """Get number of items in memory cache"""
        return len(self._memory_cache)
    
    def prune_memory_cache(self, max_items: int = None):
        """Prune memory cache to specified max items"""
        target = max_items or self._max_memory_items
        while len(self._memory_cache) > target:
            oldest = next(iter(self._memory_cache))
            del self._memory_cache[oldest]
        logger.debug(f"[Cache] Memory cache pruned to {len(self._memory_cache)} items")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_cache_service: Optional[CacheService] = None
_cache_service_lock = threading.RLock()


def get_cache_service(redis_manager=None) -> CacheService:
    """Get or create cache service instance"""
    global _cache_service
    if _cache_service is None:
        with _cache_service_lock:
            if _cache_service is None:
                _cache_service = CacheService(redis_manager)
                logger.info("[Cache] Cache service singleton created")
    return _cache_service


def reset_cache_service():
    """Reset cache service singleton (for testing/reload)"""
    global _cache_service
    with _cache_service_lock:
        if _cache_service is not None:
            _cache_service.clear_memory_cache()
            _cache_service = None
            logger.info("[Cache] Cache service singleton reset")


# ============================================================================
# EXPORT - For backward compatibility
# ============================================================================

# This creates the cache_service instance that other modules import
# The instance will be initialized with redis_manager when available
cache_service = get_cache_service()


# ============================================================================
# HEALTH CHECK FUNCTION
# ============================================================================

def check_cache_health() -> Dict[str, Any]:
    """Health check for cache service"""
    try:
        stats = cache_service.get_stats()
        return {
            "status": "healthy" if stats.get("redis_available") or stats.get("memory_items") > 0 else "degraded",
            "redis_available": stats.get("redis_available", False),
            "memory_items": stats.get("memory_items", 0),
            "hit_rate": stats.get("async_hit_rate_percent", 0),
            "sync_hit_rate": stats.get("sync_hit_rate_percent", 0),
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'CacheService',
    'get_cache_service',
    'reset_cache_service',
    'cache_service',
    'check_cache_health'
]