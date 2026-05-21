
import asyncio
import logging
import math
import json
import random
import threading
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple, Union
from enum import Enum
from collections import deque
from dataclasses import dataclass, field

import aiohttp

# ============================================================================
# LOGGER SETUP - NO EXTERNAL IMPORTS
# ============================================================================

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
# INDEPENDENT REDIS MANAGER (NO CIRCULAR IMPORTS)
# ============================================================================

class IndependentRedisManager:
    """
    Standalone Redis manager with no dependencies on backend.core.
    Prevents circular import warnings.
    """
    
    _instance = None
    _lock = threading.RLock()
    
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
            logger.info("[WeatherService] ✅ Redis connected (independent mode)")
        except ImportError:
            logger.debug("[WeatherService] Redis library not installed")
            self.available = False
        except Exception as e:
            logger.debug(f"[WeatherService] Redis not available: {e}")
            self.available = False
        
        return self.available
    
    async def get(self, key: str) -> Optional[str]:
        """Get a Redis key value"""
        if not self.available or self.client is None:
            return None
        try:
            return await self.client.get(key)
        except Exception:
            return None
    
    async def setex(self, key: str, ttl: int, value: str) -> bool:
        """Set a Redis key with TTL"""
        if not self.available or self.client is None:
            return False
        try:
            await self.client.setex(key, ttl, value)
            return True
        except Exception:
            return False
    
    async def set_json(self, key: str, value: Dict, ttl: int = 60) -> bool:
        """Set a JSON value in Redis"""
        return await self.setex(key, ttl, json.dumps(value))
    
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
# WTTR.IN FALLBACK CLIENT (Free weather API, no API key required)
# ============================================================================

class WTTRClient:
    """Free weather API client (wttr.in) - no API key required"""
    
    BASE_URL = "https://wttr.in"
    
    async def get_current_weather(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get current weather from wttr.in"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.BASE_URL}/{lat},{lon}?format=j1"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        current = data.get("current_condition", [{}])[0]
                        return {
                            "temperature_c": float(current.get("temp_C", 25)),
                            "humidity_percent": int(current.get("humidity", 55)),
                            "wind_speed_ms": float(current.get("windspeedKmph", 10)) / 3.6,
                            "pressure_hpa": int(current.get("pressure", 1013)),
                            "cloud_cover_percent": int(current.get("cloudcover", 25)),
                            "weather_condition": current.get("weatherDesc", [{}])[0].get("value", "Clear"),
                            "condition_code": "01d",
                            "visibility_m": 10000,
                            "uv_index": 5,
                            "data_source": "WTTR_IN"
                        }
        except Exception as e:
            logger.debug(f"[WTTR] Failed to fetch weather: {e}")
        return None
    
    async def close(self):
        pass


# ============================================================================
# CLIENT AVAILABILITY FLAGS (Graceful degradation)
# ============================================================================

NASA_AVAILABLE = False
OPENWEATHER_AVAILABLE = False
GEE_AVAILABLE = False
SUNGROW_AVAILABLE = False
WTTR_AVAILABLE = True  # Always available (free API)

# Lazy load clients to avoid circular imports
_nasa_client = None
_weather_client = None
_gee_client = None
_sungrow_client = None
_wttr_client = None

_clients_lock = threading.RLock()


def _get_wttr_client():
    """Get WTTR client (always available)"""
    global _wttr_client
    if _wttr_client is None:
        _wttr_client = WTTRClient()
    return _wttr_client


async def _get_nasa_client(redis_mgr, metrics):
    """Lazy load NASA client"""
    global NASA_AVAILABLE, _nasa_client
    if _nasa_client is not None:
        return _nasa_client
    
    try:
        from backend.clients.nasa_client import get_nasa_client
        _nasa_client = get_nasa_client(redis_manager=redis_mgr, metrics=metrics)
        NASA_AVAILABLE = True
        logger.debug("[WeatherService] NASA client initialized")
    except ImportError as e:
        logger.debug(f"[WeatherService] NASA client not available: {e}")
        NASA_AVAILABLE = False
    except Exception as e:
        logger.warning(f"[WeatherService] Failed to initialize NASA client: {e}")
        NASA_AVAILABLE = False
    
    return _nasa_client


async def _get_weather_client(redis_mgr, metrics):
    """Lazy load OpenWeather client"""
    global OPENWEATHER_AVAILABLE, _weather_client
    if _weather_client is not None:
        return _weather_client
    
    try:
        from backend.clients.openweather_client import get_openweather_client
        _weather_client = get_openweather_client(redis_manager=redis_mgr, metrics=metrics)
        OPENWEATHER_AVAILABLE = True
        logger.debug("[WeatherService] OpenWeather client initialized")
    except ImportError as e:
        logger.debug(f"[WeatherService] OpenWeather client not available: {e}")
        OPENWEATHER_AVAILABLE = False
    except Exception as e:
        logger.warning(f"[WeatherService] Failed to initialize OpenWeather client: {e}")
        OPENWEATHER_AVAILABLE = False
    
    return _weather_client


async def _get_gee_client(redis_mgr, metrics):
    """Lazy load GEE client"""
    global GEE_AVAILABLE, _gee_client
    if _gee_client is not None:
        return _gee_client
    
    try:
        from backend.clients.gee_client import get_gee_client
        _gee_client = get_gee_client(redis_manager=redis_mgr, metrics=metrics)
        GEE_AVAILABLE = True
        logger.debug("[WeatherService] GEE client initialized")
    except ImportError as e:
        logger.debug(f"[WeatherService] GEE client not available: {e}")
        GEE_AVAILABLE = False
    except Exception as e:
        logger.warning(f"[WeatherService] Failed to initialize GEE client: {e}")
        GEE_AVAILABLE = False
    
    return _gee_client


async def _get_sungrow_client(redis_mgr, metrics):
    """Lazy load Sungrow client"""
    global SUNGROW_AVAILABLE, _sungrow_client
    if _sungrow_client is not None:
        return _sungrow_client
    
    try:
        from backend.clients.sungrow_client import get_sungrow_client
        _sungrow_client = get_sungrow_client(redis_manager=redis_mgr, metrics=metrics)
        SUNGROW_AVAILABLE = True
        logger.debug("[WeatherService] Sungrow client initialized")
    except ImportError as e:
        logger.debug(f"[WeatherService] Sungrow client not available: {e}")
        SUNGROW_AVAILABLE = False
    except Exception as e:
        logger.warning(f"[WeatherService] Failed to initialize Sungrow client: {e}")
        SUNGROW_AVAILABLE = False
    
    return _sungrow_client


# ============================================================================
# ENUMS & DATA MODELS
# ============================================================================

class WeatherImpactLevel(str, Enum):
    """Weather impact level on grid operations"""
    OPTIMAL = "optimal"           # Best conditions for generation
    NORMAL = "normal"             # Standard operating conditions
    MODERATE = "moderate"         # Some impact on efficiency
    SEVERE = "severe"             # Significant impact expected
    EXTREME = "extreme"           # Emergency conditions


class GenerationForecast(str, Enum):
    """Generation forecast categories"""
    HIGH = "high"                 # Above average generation
    NORMAL = "normal"             # Average generation expected
    LOW = "low"                   # Below average generation
    MINIMAL = "minimal"           # Very low generation expected


@dataclass
class WeatherImpact:
    """Weather impact on grid operations"""
    impact_level: WeatherImpactLevel
    efficiency_reduction_percent: float = 0.0
    risk_multiplier: float = 1.0
    primary_factor: str = ""
    recommendation: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "impact_level": self.impact_level.value,
            "efficiency_reduction_percent": round(self.efficiency_reduction_percent, 1),
            "risk_multiplier": round(self.risk_multiplier, 2),
            "primary_factor": self.primary_factor,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeatherImpact":
        return cls(
            impact_level=WeatherImpactLevel(data.get("impact_level", "normal")),
            efficiency_reduction_percent=data.get("efficiency_reduction_percent", 0.0),
            risk_multiplier=data.get("risk_multiplier", 1.0),
            primary_factor=data.get("primary_factor", ""),
            recommendation=data.get("recommendation", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )


@dataclass
class SolarGenerationForecast:
    """Solar generation forecast"""
    forecast_category: GenerationForecast
    expected_output_mw: float = 0.0
    confidence_percent: float = 0.0
    peak_hours: List[str] = field(default_factory=list)
    cloud_impact_percent: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "forecast_category": self.forecast_category.value,
            "expected_output_mw": round(self.expected_output_mw, 1),
            "confidence_percent": round(self.confidence_percent, 1),
            "peak_hours": self.peak_hours,
            "cloud_impact_percent": round(self.cloud_impact_percent, 1),
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SolarGenerationForecast":
        return cls(
            forecast_category=GenerationForecast(data.get("forecast_category", "normal")),
            expected_output_mw=data.get("expected_output_mw", 0.0),
            confidence_percent=data.get("confidence_percent", 0.0),
            peak_hours=data.get("peak_hours", []),
            cloud_impact_percent=data.get("cloud_impact_percent", 0.0),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )


@dataclass
class GridStabilityIndex:
    """Grid stability assessment based on weather"""
    stability_score: float = 0.0  # 0-100, higher = more stable
    risk_level: str = "low"
    primary_risks: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stability_score": round(self.stability_score, 1),
            "risk_level": self.risk_level,
            "primary_risks": self.primary_risks,
            "recommended_actions": self.recommended_actions,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GridStabilityIndex":
        return cls(
            stability_score=data.get("stability_score", 0.0),
            risk_level=data.get("risk_level", "low"),
            primary_risks=data.get("primary_risks", []),
            recommended_actions=data.get("recommended_actions", []),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )


@dataclass
class UnifiedWeatherData:
    """Complete unified weather intelligence"""
    current_weather: Dict[str, Any]
    solar_data: Dict[str, Any]
    forecast: Dict[str, Any]
    vegetation: Dict[str, Any]
    thermal: Dict[str, Any]
    air_quality: Dict[str, Any]
    inverter_status: Dict[str, Any]
    weather_impact: WeatherImpact
    solar_forecast: SolarGenerationForecast
    grid_stability: GridStabilityIndex
    data_sources: List[str]
    confidence_score: float = 0.85
    response_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_weather": self.current_weather,
            "solar_data": self.solar_data,
            "forecast": self.forecast,
            "vegetation": self.vegetation,
            "thermal": self.thermal,
            "air_quality": self.air_quality,
            "inverter_status": self.inverter_status,
            "weather_impact": self.weather_impact.to_dict(),
            "solar_forecast": self.solar_forecast.to_dict(),
            "grid_stability": self.grid_stability.to_dict(),
            "data_sources": self.data_sources,
            "confidence_score": round(self.confidence_score, 2),
            "response_time_ms": round(self.response_time_ms, 2),
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedWeatherData":
        return cls(
            current_weather=data.get("current_weather", {}),
            solar_data=data.get("solar_data", {}),
            forecast=data.get("forecast", {}),
            vegetation=data.get("vegetation", {}),
            thermal=data.get("thermal", {}),
            air_quality=data.get("air_quality", {}),
            inverter_status=data.get("inverter_status", {}),
            weather_impact=WeatherImpact.from_dict(data.get("weather_impact", {})),
            solar_forecast=SolarGenerationForecast.from_dict(data.get("solar_forecast", {})),
            grid_stability=GridStabilityIndex.from_dict(data.get("grid_stability", {})),
            data_sources=data.get("data_sources", []),
            confidence_score=data.get("confidence_score", 0.85),
            response_time_ms=data.get("response_time_ms", 0.0),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat())
        )


# ============================================================================
# UNIFIED WEATHER SERVICE - FULLY FIXED (v3.1.0)
# ============================================================================

class UnifiedWeatherService:
    """
    Production-grade Unified Weather Intelligence Service
    
    Features:
    - Aggregates data from NASA, OpenWeather, GEE, Sungrow, and WTTR.IN
    - Calculates weather impact on grid operations
    - Generates weather-adjusted energy forecasts
    - Real-time anomaly detection
    - Smart data fusion with confidence scoring
    
    FIXED: Independent Redis manager with no circular imports
    FIXED: Lazy client loading with fallback to WTTR.IN
    """
    
    def __init__(self, redis_manager=None, metrics=None):
        """
        Initialize Unified Weather Service
        
        Args:
            redis_manager: Redis cache manager (can be None, will use independent)
            metrics: Prometheus metrics instance
        """
        # Use provided redis_manager or create independent one
        if redis_manager is not None:
            self.redis_manager = redis_manager
            self._redis_available = hasattr(redis_manager, 'available') and redis_manager.available
        else:
            self.redis_manager = get_redis_manager()
            self._redis_available = self.redis_manager.available
        
        self.metrics = metrics
        
        # Client instances (lazy loaded)
        self._nasa_client = None
        self._weather_client = None
        self._gee_client = None
        self._sungrow_client = None
        self._wttr_client = _get_wttr_client()
        
        # Cache for aggregated data
        self._cache = {}
        self._last_update: Dict[str, float] = {}
        
        # Historical data for trend analysis
        self._historical_solar: deque = deque(maxlen=168)  # 7 days of hourly data
        self._historical_temp: deque = deque(maxlen=168)
        
        # Abuja coordinates
        self.lat = 9.0765
        self.lon = 7.3986
        
        redis_status = "Available" if self._redis_available else "Not Available (using memory cache)"
        logger.info(f"[WeatherService] Unified Weather Service initialized | Redis: {redis_status}")
        logger.info(f"[WeatherService] Fallback: WTTR.IN available (free API)")
    
    async def _redis_get(self, key: str) -> Optional[str]:
        """Safely get from Redis"""
        if not self._redis_available or self.redis_manager is None:
            return None
        
        try:
            if hasattr(self.redis_manager, 'get'):
                if asyncio.iscoroutinefunction(self.redis_manager.get):
                    return await self.redis_manager.get(key)
                else:
                    return self.redis_manager.get(key)
        except Exception as e:
            logger.debug(f"[WeatherService] Redis get error: {e}")
        return None
    
    async def _redis_setex(self, key: str, ttl: int, value: str) -> bool:
        """Safely set in Redis with TTL"""
        if not self._redis_available or self.redis_manager is None:
            return False
        
        try:
            if hasattr(self.redis_manager, 'setex'):
                if asyncio.iscoroutinefunction(self.redis_manager.setex):
                    await self.redis_manager.setex(key, ttl, value)
                else:
                    self.redis_manager.setex(key, ttl, value)
                return True
            elif hasattr(self.redis_manager, 'set'):
                if asyncio.iscoroutinefunction(self.redis_manager.set):
                    await self.redis_manager.set(key, value, ex=ttl)
                else:
                    self.redis_manager.set(key, value, ex=ttl)
                return True
        except Exception as e:
            logger.debug(f"[WeatherService] Redis set error: {e}")
        return False
    
    def _update_metrics(self, operation: str, duration_ms: float, success: bool):
        """Update Prometheus metrics"""
        if self.metrics:
            try:
                if hasattr(self.metrics, 'api_requests_total'):
                    status = "success" if success else "error"
                    self.metrics.api_requests_total.labels(
                        method="GET",
                        endpoint=f"/weather/unified/{operation}",
                        status_code="200" if success else "500",
                        user_type="system"
                    ).inc()
                
                if hasattr(self.metrics, 'api_request_duration_seconds'):
                    self.metrics.api_request_duration_seconds.labels(
                        method="GET",
                        endpoint=f"/weather/unified/{operation}"
                    ).observe(duration_ms / 1000)
                    
            except Exception as e:
                logger.debug(f"[WeatherService] Metrics update failed: {e}")
    
    async def _get_nasa_client(self):
        """Get NASA client (lazy loaded)"""
        if self._nasa_client is None:
            self._nasa_client = await _get_nasa_client(self.redis_manager, self.metrics)
        return self._nasa_client
    
    async def _get_weather_client(self):
        """Get OpenWeather client (lazy loaded)"""
        if self._weather_client is None:
            self._weather_client = await _get_weather_client(self.redis_manager, self.metrics)
        return self._weather_client
    
    async def _get_gee_client(self):
        """Get GEE client (lazy loaded)"""
        if self._gee_client is None:
            self._gee_client = await _get_gee_client(self.redis_manager, self.metrics)
        return self._gee_client
    
    async def _get_sungrow_client(self):
        """Get Sungrow client (lazy loaded)"""
        if self._sungrow_client is None:
            self._sungrow_client = await _get_sungrow_client(self.redis_manager, self.metrics)
        return self._sungrow_client
    
    async def _get_wttr_weather(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get weather from WTTR.IN fallback"""
        return await self._wttr_client.get_current_weather(lat, lon)
    
    async def _safe_fetch(self, fetch_func, *args, **kwargs):
        """Safely fetch data with error handling"""
        try:
            return await fetch_func(*args, **kwargs)
        except Exception as e:
            logger.debug(f"[WeatherService] Fetch failed: {e}")
            return None
    
    async def get_unified_weather(
        self,
        lat: float = 9.0765,
        lon: float = 7.3986,
        use_cache: bool = True
    ) -> UnifiedWeatherData:
        """
        Get complete unified weather intelligence from all sources
        
        Args:
            lat: Latitude (default: Abuja)
            lon: Longitude (default: Abuja)
            use_cache: Use Redis cache
        
        Returns:
            UnifiedWeatherData object
        """
        import time
        start_time = time.time()
        
        cache_key = f"weather:unified:{lat}:{lon}"
        
        if use_cache and self._redis_available:
            try:
                cached = await self._redis_get(cache_key)
                if cached:
                    if isinstance(cached, str):
                        try:
                            cached = json.loads(cached)
                        except json.JSONDecodeError:
                            pass
                    logger.debug("[WeatherService] Cache hit for unified weather")
                    self._update_metrics("get_unified_weather", 0, True)
                    return UnifiedWeatherData.from_dict(cached)
            except Exception as e:
                logger.debug(f"[WeatherService] Cache read error: {e}")
        
        # Initialize clients
        nasa_client = await self._get_nasa_client()
        weather_client = await self._get_weather_client()
        gee_client = await self._get_gee_client()
        sungrow_client = await self._get_sungrow_client()
        
        # Fetch all data sources in parallel with graceful degradation
        tasks = []
        
        if NASA_AVAILABLE and nasa_client:
            tasks.append(self._safe_fetch(nasa_client.fetch_telemetry, lat, lon, use_cache))
        else:
            tasks.append(asyncio.sleep(0, result=None))
        
        if OPENWEATHER_AVAILABLE and weather_client:
            tasks.append(self._safe_fetch(weather_client.get_complete_weather, lat, lon, True, True))
        else:
            tasks.append(asyncio.sleep(0, result=None))
        
        if GEE_AVAILABLE and gee_client:
            tasks.append(self._safe_fetch(gee_client.get_complete_geospatial_data, lat, lon, False))
        else:
            tasks.append(asyncio.sleep(0, result=None))
        
        if SUNGROW_AVAILABLE and sungrow_client:
            tasks.append(self._safe_fetch(sungrow_client.get_fleet_summary))
        else:
            tasks.append(asyncio.sleep(0, result=None))
        
        # Always try WTTR.IN as fallback for weather
        tasks.append(self._get_wttr_weather(lat, lon))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        nasa_data = results[0] if len(results) > 0 and not isinstance(results[0], Exception) else None
        weather_data = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else None
        gee_data = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else None
        inverter_data = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else None
        wttr_data = results[4] if len(results) > 4 and not isinstance(results[4], Exception) else None
        
        # Build unified data structure
        unified = self._build_unified_data(
            nasa_data, weather_data, gee_data, inverter_data, wttr_data
        )
        
        duration_ms = (time.time() - start_time) * 1000
        unified.response_time_ms = duration_ms
        self._update_metrics("get_unified_weather", duration_ms, True)
        
        # Cache result
        if use_cache and self._redis_available:
            try:
                await self._redis_setex(cache_key, 300, json.dumps(unified.to_dict()))
            except Exception as e:
                logger.debug(f"[WeatherService] Cache write error: {e}")
        
        # Update historical data
        self._update_historical_data(unified)
        
        return unified
    
    def _build_unified_data(
        self,
        nasa_data,
        weather_data,
        gee_data,
        inverter_data,
        wttr_data
    ) -> UnifiedWeatherData:
        """Build unified data structure from all sources with WTTR.IN fallback"""
        
        data_sources = []
        
        # Current weather - prioritize OpenWeather, then NASA, then WTTR.IN
        current_weather = {}
        
        if weather_data and hasattr(weather_data, 'current') and weather_data.current:
            current_weather = weather_data.current.to_dict()
            data_sources.append("openweather")
        elif nasa_data and hasattr(nasa_data, 'weather'):
            current_weather = {
                "temperature_c": nasa_data.weather.temperature_c,
                "humidity_percent": nasa_data.weather.humidity_percent,
                "wind_speed_ms": nasa_data.weather.wind_speed_ms,
                "pressure_hpa": nasa_data.weather.pressure_hpa,
                "weather_condition": "partly cloudy",
                "condition_code": "02d",
                "data_source": "nasa"
            }
            data_sources.append("nasa")
        elif wttr_data:
            current_weather = {
                "temperature_c": wttr_data.get("temperature_c", 29.5),
                "humidity_percent": wttr_data.get("humidity_percent", 55),
                "wind_speed_ms": wttr_data.get("wind_speed_ms", 3.2),
                "pressure_hpa": wttr_data.get("pressure_hpa", 1013),
                "cloud_cover_percent": wttr_data.get("cloud_cover_percent", 25),
                "weather_condition": wttr_data.get("weather_condition", "clear sky"),
                "condition_code": wttr_data.get("condition_code", "01d"),
                "data_source": "wttr.in"
            }
            data_sources.append("wttr.in")
        
        # Solar data (from NASA or fallback)
        solar_data = {}
        if nasa_data and hasattr(nasa_data, 'solar'):
            solar_data = nasa_data.solar.to_dict()
            if "nasa" not in data_sources:
                data_sources.append("nasa")
        else:
            # Estimate solar from time of day
            hour = datetime.now().hour
            if 6 <= hour <= 18:
                solar_factor = math.sin(math.pi * (hour - 6) / 12)
                ghi = 850 * solar_factor
            else:
                ghi = 0
            solar_data = {
                "ghi_wm2": round(ghi, 1),
                "dni_wm2": round(ghi * 0.85, 1),
                "dhi_wm2": round(ghi * 0.15, 1),
                "cloud_cover_percent": current_weather.get("cloud_cover_percent", 25),
                "data_quality": 0.75
            }
        
        # Forecast (from OpenWeather or fallback)
        forecast = {}
        if weather_data and hasattr(weather_data, 'forecast') and weather_data.forecast:
            forecast = weather_data.forecast.to_dict()
            if "openweather" not in data_sources:
                data_sources.append("openweather")
        
        # Vegetation (from GEE)
        vegetation = {}
        if gee_data and hasattr(gee_data, 'vegetation'):
            vegetation = gee_data.vegetation.to_dict()
            data_sources.append("gee")
        
        # Thermal (from GEE)
        thermal = {}
        if gee_data and hasattr(gee_data, 'thermal'):
            thermal = gee_data.thermal.to_dict()
        
        # Air quality (from OpenWeather)
        air_quality = {}
        if weather_data and hasattr(weather_data, 'air_quality') and weather_data.air_quality:
            air_quality = weather_data.air_quality.to_dict()
        
        # Inverter status (from Sungrow)
        inverter_status = {}
        if inverter_data and hasattr(inverter_data, 'to_dict'):
            inverter_status = inverter_data.to_dict()
            data_sources.append("sungrow")
        
        # Calculate weather impact
        weather_impact = self._calculate_weather_impact(nasa_data, weather_data, gee_data, wttr_data)
        
        # Calculate solar generation forecast
        solar_forecast = self._calculate_solar_forecast(nasa_data, weather_data, wttr_data)
        
        # Calculate grid stability index
        grid_stability = self._calculate_grid_stability(nasa_data, weather_data, gee_data, inverter_data, wttr_data)
        
        # Calculate overall confidence score
        confidence_score = self._calculate_confidence_score(data_sources)
        
        return UnifiedWeatherData(
            current_weather=current_weather,
            solar_data=solar_data,
            forecast=forecast,
            vegetation=vegetation,
            thermal=thermal,
            air_quality=air_quality,
            inverter_status=inverter_status,
            weather_impact=weather_impact,
            solar_forecast=solar_forecast,
            grid_stability=grid_stability,
            data_sources=data_sources,
            confidence_score=confidence_score
        )
    
    def _calculate_weather_impact(
        self,
        nasa_data,
        weather_data,
        gee_data,
        wttr_data
    ) -> WeatherImpact:
        """
        Calculate weather impact on grid operations
        
        Factors considered:
        - Cloud cover (reduces solar generation)
        - Temperature extremes (affects efficiency)
        - Wind speed (affects grid stability)
        - Thermal anomalies (grid stress)
        """
        cloud_cover = 25.0
        temperature = 29.5
        wind_speed = 3.2
        thermal_anomaly = 0
        
        # Get data from available sources
        if nasa_data and hasattr(nasa_data, 'solar') and hasattr(nasa_data, 'weather'):
            cloud_cover = nasa_data.solar.cloud_cover_percent
            temperature = nasa_data.weather.temperature_c
            wind_speed = nasa_data.weather.wind_speed_ms
        elif wttr_data:
            cloud_cover = wttr_data.get("cloud_cover_percent", 25)
            temperature = wttr_data.get("temperature_c", 29.5)
            wind_speed = wttr_data.get("wind_speed_ms", 3.2)
        
        if weather_data and hasattr(weather_data, 'current') and weather_data.current:
            temperature = weather_data.current.temperature_c
            wind_speed = weather_data.current.wind_speed_ms
            if hasattr(weather_data.current, 'cloud_cover_percent'):
                cloud_cover = weather_data.current.cloud_cover_percent
        
        if gee_data and hasattr(gee_data, 'thermal') and gee_data.thermal:
            thermal_anomaly = getattr(gee_data.thermal, 'anomaly_strength', 0)
        
        # Calculate efficiency reduction
        efficiency_reduction = 0.0
        primary_factor = ""
        
        # Cloud impact
        if cloud_cover > 80:
            efficiency_reduction += 40
            primary_factor = "heavy_cloud_cover"
        elif cloud_cover > 60:
            efficiency_reduction += 25
            primary_factor = "moderate_cloud_cover"
        elif cloud_cover > 40:
            efficiency_reduction += 10
        
        # Temperature impact
        if temperature > 40:
            efficiency_reduction += 15
            primary_factor = "extreme_heat"
        elif temperature > 35:
            efficiency_reduction += 8
        elif temperature < 15:
            efficiency_reduction += 5
        
        # Wind impact
        if wind_speed > 15:
            efficiency_reduction += 20
            primary_factor = "high_wind"
        elif wind_speed > 10:
            efficiency_reduction += 10
        
        # Thermal anomaly impact
        if thermal_anomaly > 5:
            efficiency_reduction += 25
            primary_factor = "thermal_anomaly"
        elif thermal_anomaly > 3:
            efficiency_reduction += 10
        
        # Determine impact level
        if efficiency_reduction >= 50:
            impact_level = WeatherImpactLevel.EXTREME
            recommendation = "Consider load shedding and backup systems"
            risk_multiplier = 2.5
        elif efficiency_reduction >= 30:
            impact_level = WeatherImpactLevel.SEVERE
            recommendation = "Reduce non-critical loads, monitor closely"
            risk_multiplier = 1.8
        elif efficiency_reduction >= 15:
            impact_level = WeatherImpactLevel.MODERATE
            recommendation = "Optimize energy distribution"
            risk_multiplier = 1.3
        elif efficiency_reduction >= 5:
            impact_level = WeatherImpactLevel.NORMAL
            recommendation = "Standard operations"
            risk_multiplier = 1.0
        else:
            impact_level = WeatherImpactLevel.OPTIMAL
            recommendation = "Maximum efficiency expected"
            risk_multiplier = 0.8
        
        return WeatherImpact(
            impact_level=impact_level,
            efficiency_reduction_percent=min(100, efficiency_reduction),
            risk_multiplier=risk_multiplier,
            primary_factor=primary_factor,
            recommendation=recommendation
        )
    
    def _calculate_solar_forecast(
        self,
        nasa_data,
        weather_data,
        wttr_data
    ) -> SolarGenerationForecast:
        """
        Calculate solar generation forecast based on weather conditions
        
        Returns:
            SolarGenerationForecast with expected output and confidence
        """
        cloud_cover = 25.0
        current_ghi = 850.0
        
        if nasa_data and hasattr(nasa_data, 'solar'):
            cloud_cover = nasa_data.solar.cloud_cover_percent
            current_ghi = nasa_data.solar.ghi_wm2
        elif wttr_data:
            cloud_cover = wttr_data.get("cloud_cover_percent", 25)
            current_ghi = 850 * (1 - cloud_cover / 100)
        
        if weather_data and hasattr(weather_data, 'current') and weather_data.current:
            if hasattr(weather_data.current, 'cloud_cover_percent'):
                cloud_cover = weather_data.current.cloud_cover_percent
        
        # Calculate expected output based on cloud cover
        cloud_impact = min(100, cloud_cover)
        expected_output_mw = 100 * (1 - cloud_impact / 100)
        
        # Determine forecast category
        if expected_output_mw >= 80:
            forecast_category = GenerationForecast.HIGH
            confidence = 0.9
        elif expected_output_mw >= 50:
            forecast_category = GenerationForecast.NORMAL
            confidence = 0.85
        elif expected_output_mw >= 20:
            forecast_category = GenerationForecast.LOW
            confidence = 0.75
        else:
            forecast_category = GenerationForecast.MINIMAL
            confidence = 0.7
        
        # Calculate peak hours (solar noon ± 3 hours)
        now = datetime.now()
        solar_noon = now.replace(hour=12, minute=30, second=0, microsecond=0)
        peak_hours = [
            (solar_noon - timedelta(hours=2)).strftime("%H:00"),
            (solar_noon - timedelta(hours=1)).strftime("%H:00"),
            solar_noon.strftime("%H:00"),
            (solar_noon + timedelta(hours=1)).strftime("%H:00"),
            (solar_noon + timedelta(hours=2)).strftime("%H:00")
        ]
        
        return SolarGenerationForecast(
            forecast_category=forecast_category,
            expected_output_mw=round(expected_output_mw, 1),
            confidence_percent=round(confidence * 100, 1),
            peak_hours=peak_hours,
            cloud_impact_percent=round(cloud_impact, 1)
        )
    
    def _calculate_grid_stability(
        self,
        nasa_data,
        weather_data,
        gee_data,
        inverter_data,
        wttr_data
    ) -> GridStabilityIndex:
        """
        Calculate grid stability index based on all data sources
        
        Returns:
            GridStabilityIndex with score 0-100
        """
        stability_score = 85.0  # Base score
        primary_risks = []
        recommended_actions = []
        
        # Weather impact
        weather_impact = self._calculate_weather_impact(nasa_data, weather_data, gee_data, wttr_data)
        stability_score -= weather_impact.efficiency_reduction_percent * 0.5
        
        if weather_impact.impact_level in [WeatherImpactLevel.SEVERE, WeatherImpactLevel.EXTREME]:
            primary_risks.append(f"severe_weather_{weather_impact.primary_factor}")
            recommended_actions.append(weather_impact.recommendation)
        
        # Thermal anomalies
        if gee_data and hasattr(gee_data, 'thermal') and gee_data.thermal:
            thermal_anomaly = getattr(gee_data.thermal, 'thermal_anomaly_detected', False)
            if thermal_anomaly:
                primary_risks.append("thermal_anomaly_detected")
                stability_score -= 15
                recommended_actions.append("Investigate thermal anomaly source")
        
        # Inverter performance
        if inverter_data:
            online_count = getattr(inverter_data, 'online_count', 0)
            total_inverters = getattr(inverter_data, 'total_inverters', 0)
            if total_inverters > 0 and online_count < total_inverters:
                offline_count = total_inverters - online_count
                stability_score -= offline_count * 5
                primary_risks.append(f"{offline_count}_inverters_offline")
                recommended_actions.append("Check offline inverters")
        
        # Temperature extremes
        temperature = 29.5
        if nasa_data and hasattr(nasa_data, 'weather'):
            temperature = nasa_data.weather.temperature_c
        elif wttr_data:
            temperature = wttr_data.get("temperature_c", 29.5)
        
        if temperature > 40:
            stability_score -= 10
            primary_risks.append("extreme_temperature")
            recommended_actions.append("Monitor equipment cooling")
        elif temperature < 10:
            stability_score -= 5
            primary_risks.append("low_temperature")
        
        # Cloud cover impact
        cloud_cover = 25.0
        if nasa_data and hasattr(nasa_data, 'solar'):
            cloud_cover = nasa_data.solar.cloud_cover_percent
        elif wttr_data:
            cloud_cover = wttr_data.get("cloud_cover_percent", 25)
        
        if cloud_cover > 80:
            stability_score -= 10
            primary_risks.append("heavy_cloud_cover")
        
        # Ensure score is within 0-100
        stability_score = max(0, min(100, stability_score))
        
        # Determine risk level
        if stability_score >= 80:
            risk_level = "low"
        elif stability_score >= 60:
            risk_level = "medium"
        elif stability_score >= 40:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        return GridStabilityIndex(
            stability_score=round(stability_score, 1),
            risk_level=risk_level,
            primary_risks=primary_risks,
            recommended_actions=recommended_actions
        )
    
    def _calculate_confidence_score(self, data_sources: List[str]) -> float:
        """
        Calculate overall confidence score based on available data sources
        
        More sources = higher confidence
        """
        base_confidence = 0.7
        source_bonus = len(data_sources) * 0.05
        return min(0.98, base_confidence + source_bonus)
    
    def _update_historical_data(self, unified: UnifiedWeatherData):
        """Update historical data for trend analysis"""
        if unified.solar_data and "ghi_wm2" in unified.solar_data:
            self._historical_solar.append({
                "timestamp": datetime.now().isoformat(),
                "ghi_wm2": unified.solar_data["ghi_wm2"]
            })
        
        if unified.current_weather and "temperature_c" in unified.current_weather:
            self._historical_temp.append({
                "timestamp": datetime.now().isoformat(),
                "temperature_c": unified.current_weather["temperature_c"]
            })
    
    async def get_weather_impact_only(
        self,
        lat: float = 9.0765,
        lon: float = 7.3986
    ) -> WeatherImpact:
        """Get only weather impact assessment (lightweight)"""
        unified = await self.get_unified_weather(lat, lon, use_cache=True)
        return unified.weather_impact
    
    async def get_solar_forecast_only(
        self,
        lat: float = 9.0765,
        lon: float = 7.3986
    ) -> SolarGenerationForecast:
        """Get only solar generation forecast (lightweight)"""
        unified = await self.get_unified_weather(lat, lon, use_cache=True)
        return unified.solar_forecast
    
    async def get_grid_stability_only(
        self,
        lat: float = 9.0765,
        lon: float = 7.3986
    ) -> GridStabilityIndex:
        """Get only grid stability index (lightweight)"""
        unified = await self.get_unified_weather(lat, lon, use_cache=True)
        return unified.grid_stability
    
    async def get_trend_analysis(self) -> Dict[str, Any]:
        """
        Get trend analysis from historical data
        
        Returns:
            Trend analysis with predictions
        """
        # Calculate solar trend
        solar_values = [item["ghi_wm2"] for item in self._historical_solar]
        solar_trend = "stable"
        if len(solar_values) >= 24:
            recent_avg = sum(solar_values[-12:]) / 12
            older_avg = sum(solar_values[-24:-12]) / 12
            if recent_avg > older_avg * 1.1:
                solar_trend = "increasing"
            elif recent_avg < older_avg * 0.9:
                solar_trend = "decreasing"
        
        # Calculate temperature trend
        temp_values = [item["temperature_c"] for item in self._historical_temp]
        temp_trend = "stable"
        if len(temp_values) >= 24:
            recent_avg = sum(temp_values[-12:]) / 12
            older_avg = sum(temp_values[-24:-12]) / 12
            if recent_avg > older_avg * 1.05:
                temp_trend = "warming"
            elif recent_avg < older_avg * 0.95:
                temp_trend = "cooling"
        
        return {
            "solar_trend": solar_trend,
            "temperature_trend": temp_trend,
            "data_points": {
                "solar": len(self._historical_solar),
                "temperature": len(self._historical_temp)
            },
            "latest_solar": solar_values[-1] if solar_values else None,
            "latest_temperature": temp_values[-1] if temp_values else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API calls (for external integrations)"""
        return {
            "X-Weather-Service-Version": "3.1.0",
            "X-Data-Sources": "nasa,openweather,gee,sungrow,wttr.in",
            "X-Unified-Weather": "active"
        }
    
    async def close(self):
        """Close all client connections"""
        if self._nasa_client and hasattr(self._nasa_client, 'close'):
            await self._nasa_client.close()
        if self._weather_client and hasattr(self._weather_client, 'close'):
            await self._weather_client.close()
        if self._gee_client and hasattr(self._gee_client, 'close'):
            await self._gee_client.close()
        if self._sungrow_client and hasattr(self._sungrow_client, 'close'):
            await self._sungrow_client.close()
        if self._wttr_client and hasattr(self._wttr_client, 'close'):
            await self._wttr_client.close()
        logger.info("[WeatherService] All clients closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "redis_available": self._redis_available,
            "nasa_available": NASA_AVAILABLE,
            "openweather_available": OPENWEATHER_AVAILABLE,
            "gee_available": GEE_AVAILABLE,
            "sungrow_available": SUNGROW_AVAILABLE,
            "wttr_available": WTTR_AVAILABLE,
            "historical_data_points": {
                "solar": len(self._historical_solar),
                "temperature": len(self._historical_temp)
            }
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_weather_service: Optional[UnifiedWeatherService] = None
_weather_service_lock = threading.RLock()


def get_weather_service(redis_manager=None, metrics=None) -> UnifiedWeatherService:
    """
    Get or create singleton weather service instance
    
    Args:
        redis_manager: Redis cache manager (optional, will create independent if not provided)
        metrics: Prometheus metrics instance (optional)
    
    Returns:
        UnifiedWeatherService singleton instance
    """
    global _weather_service
    
    if _weather_service is None:
        with _weather_service_lock:
            if _weather_service is None:
                _weather_service = UnifiedWeatherService(redis_manager, metrics)
                logger.info("[WeatherService] Weather Service singleton created")
    
    return _weather_service


def reset_weather_service():
    """Reset the Weather Service singleton (for testing/reload)"""
    global _weather_service
    with _weather_service_lock:
        if _weather_service is not None:
            _weather_service = None
            logger.info("[WeatherService] Weather Service singleton reset")


# ============================================================================
# INITIALIZATION FUNCTION
# ============================================================================

async def initialize_weather_service() -> bool:
    """Initialize Weather Service module (call at app startup)"""
    logger.info("[WeatherService] Initializing...")
    
    # Initialize Redis
    redis_available = await ensure_redis_initialized()
    
    # Initialize service (will lazy load clients as needed)
    service = get_weather_service()
    
    logger.info(f"[WeatherService] ✅ Initialized | Redis: {'available' if redis_available else 'not available'}")
    logger.info(f"[WeatherService] Data sources: NASA={NASA_AVAILABLE}, OpenWeather={OPENWEATHER_AVAILABLE}, GEE={GEE_AVAILABLE}, Sungrow={SUNGROW_AVAILABLE}, WTTR.IN={WTTR_AVAILABLE}")
    
    return True


async def shutdown_weather_service():
    """Shutdown Weather Service module"""
    logger.info("[WeatherService] Shutting down...")
    
    if _weather_service is not None:
        await _weather_service.close()
    
    # Close Redis connection
    manager = get_redis_manager()
    await manager.close()
    
    logger.info("[WeatherService] ✅ Shutdown complete")


# ============================================================================
# HEALTH CHECK FUNCTION
# ============================================================================

async def check_weather_health() -> Dict[str, Any]:
    """Health check for Weather Service"""
    try:
        service = get_weather_service()
        stats = service.get_stats()
        
        # Determine overall status
        if not any([stats.get("nasa_available"), stats.get("openweather_available")]):
            status = "degraded"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "weather_service": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'UnifiedWeatherService',
    'get_weather_service',
    'reset_weather_service',
    'initialize_weather_service',
    'shutdown_weather_service',
    'check_weather_health',
    'WeatherImpact',
    'WeatherImpactLevel',
    'SolarGenerationForecast',
    'GenerationForecast',
    'GridStabilityIndex',
    'UnifiedWeatherData'
]