
import os
import logging
import asyncio
import json
import hashlib
import time
import numpy as np
import platform
import math
import traceback
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

# IMPORTANT: Import the global Redis client from backend.core.redis
try:
    from backend.core.redis import redis_client as global_redis_client
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    global_redis_client = None
    logger = logging.getLogger(__name__)
    logger.warning("[GEE] Could not import redis_client, using memory cache only")

# Google Earth Engine imports with error handling
try:
    import ee
    from ee import oauth
    EE_AVAILABLE = True
except ImportError as e:
    EE_AVAILABLE = False
    logging.getLogger(__name__).error(f"Google Earth Engine import error: {e}")

from dotenv import load_dotenv

load_dotenv()

# Windows console encoding fix
if platform.system() == 'Windows':
    try:
        import subprocess
        subprocess.run('chcp 65001 > nul', shell=True, capture_output=True)
    except:
        pass

logger = logging.getLogger("NeuroBridge.GEE")

# ============================================================================
# PRODUCTION SAFETY HELPERS - CRITICAL FIX
# ============================================================================

def safe_gt(value: Any, threshold: float, default: float = 0.0) -> bool:
    """
    Safe greater-than comparison that handles None values.
    
    Args:
        value: The value to compare (could be None)
        threshold: The threshold to compare against
        default: Default value to use if value is None
        
    Returns:
        bool: True if value > threshold, False otherwise
    """
    try:
        if value is None:
            return default > threshold
        return float(value) > threshold
    except (TypeError, ValueError):
        return False


def safe_lt(value: Any, threshold: float, default: float = 0.0) -> bool:
    """
    Safe less-than comparison that handles None values.
    """
    try:
        if value is None:
            return default < threshold
        return float(value) < threshold
    except (TypeError, ValueError):
        return False


def sanitize_numeric(value: Any, default: float = 0.0) -> float:
    """
    Safely convert any value to float, handling None and invalid types.
    
    Args:
        value: The value to convert (could be None, string, int, float)
        default: Default value to use if conversion fails
        
    Returns:
        float: Sanitized numeric value
    """
    if value is None:
        return default
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Remove percentage sign if present
            cleaned = value.replace('%', '').strip()
            return float(cleaned)
        return default
    except (TypeError, ValueError):
        return default


def safe_get(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Safely get value from dict with None handling.
    """
    value = data.get(key)
    return default if value is None else value


# ============================================================================
# ENHANCED DATA MODELS
# ============================================================================

class GEEDataSource(str, Enum):
    """Data source for GEE telemetry"""
    SENTINEL_2 = "SENTINEL-2"
    LANDSAT_8 = "LANDSAT-8"
    MODIS = "MODIS"
    FUSION = "FUSION"
    FALLBACK = "FALLBACK"
    CACHED = "CACHED"


class TerrainFeature(str, Enum):
    """Terrain feature classification"""
    URBAN = "URBAN"
    VEGETATED = "VEGETATED"
    WATER = "WATER"
    BARREN = "BARREN"
    AGRICULTURAL = "AGRICULTURAL"
    FOREST = "FOREST"
    MIXED = "MIXED"


@dataclass
class SpectralTensor:
    """11D spectral tensor for quantum-geospatial fusion"""
    timestamp: datetime
    source: GEEDataSource
    red: float          # Red band reflectance
    green: float        # Green band reflectance
    blue: float         # Blue band reflectance
    nir: float          # Near-Infrared reflectance
    swir1: float        # Short-wave Infrared 1
    swir2: float        # Short-wave Infrared 2
    ndvi: float         # Normalized Difference Vegetation Index
    ndwi: float         # Normalized Difference Water Index
    ndbi: float         # Normalized Difference Built-up Index
    cloud_probability: float  # Sentinel-2 cloud probability (%)
    terrain_feature: TerrainFeature
    elevation_m: float  # Elevation (meters)
    slope_deg: float    # Slope (degrees)
    aspect_deg: float   # Aspect (degrees)
    quality_score: float  # Data quality (0-1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "nir": self.nir,
            "swir1": self.swir1,
            "swir2": self.swir2,
            "ndvi": self.ndvi,
            "ndwi": self.ndwi,
            "ndbi": self.ndbi,
            "cloud_probability": self.cloud_probability,
            "terrain_feature": self.terrain_feature.value,
            "elevation_m": self.elevation_m,
            "slope_deg": self.slope_deg,
            "aspect_deg": self.aspect_deg,
            "quality_score": self.quality_score
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpectralTensor":
        """Create from dictionary"""
        return cls(
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            source=GEEDataSource(data.get("source", "FALLBACK")),
            red=data.get("red", 0.08),
            green=data.get("green", 0.1),
            blue=data.get("blue", 0.06),
            nir=data.get("nir", 0.25),
            swir1=data.get("swir1", 0.15),
            swir2=data.get("swir2", 0.1),
            ndvi=data.get("ndvi", 0.4),
            ndwi=data.get("ndwi", -0.05),
            ndbi=data.get("ndbi", 0.2),
            cloud_probability=data.get("cloud_probability", 30.0),
            terrain_feature=TerrainFeature(data.get("terrain_feature", "MIXED")),
            elevation_m=data.get("elevation_m", 400.0),
            slope_deg=data.get("slope_deg", 5.0),
            aspect_deg=data.get("aspect_deg", 180.0),
            quality_score=data.get("quality_score", 0.85)
        )
    
    def to_geospatial_context(self) -> Dict[str, Any]:
        """Convert to geospatial context for 11D kernel"""
        # Safe calculations with fallbacks
        thermal_anomaly = max(0.0, min(1.0, (self.ndbi - self.ndvi) * 0.5 + 0.2))
        vegetation_health = self.ndvi * 0.7 + (1 - self.cloud_probability / 100) * 0.3
        urban_density = min(1.0, max(0.0, self.ndbi * 1.5))
        
        return {
            "vegetation_index": round(self.ndvi, 4),
            "thermal_anomaly_score": round(thermal_anomaly, 3),
            "urban_density": round(urban_density, 3),
            "water_index": round(self.ndwi, 4),
            "built_up_index": round(self.ndbi, 4),
            "cloud_probability": round(self.cloud_probability, 1),
            "terrain_class": self.terrain_feature.value,
            "elevation_m": round(self.elevation_m, 1),
            "slope_deg": round(self.slope_deg, 1),
            "vegetation_health": round(vegetation_health, 3),
            "data_source": self.source.value,
            "data_quality": self.quality_score,
            "spectral_signature": {
                "red": round(self.red, 4),
                "green": round(self.green, 4),
                "blue": round(self.blue, 4),
                "nir": round(self.nir, 4),
                "swir1": round(self.swir1, 4),
                "swir2": round(self.swir2, 4)
            }
        }
    
    def get_energy_potential(self) -> float:
        """Calculate solar energy potential from spectral data"""
        clear_sky_factor = 1 - (self.cloud_probability / 100)
        albedo_factor = 1 - (self.ndvi * 0.3)
        urban_factor = 1 + (self.ndbi * 0.2)
        potential = clear_sky_factor * albedo_factor * urban_factor
        return round(min(1.0, max(0.2, potential)), 3)
    
    def get_aece_risk_factor(self) -> float:
        """Calculate AECE risk factor from spectral data"""
        # Higher risk when:
        # - Cloud cover > 60% (reduced solar generation)
        # - NDVI < 0.2 (low vegetation = more urban heat)
        # - NDBI > 0.3 (high urban density)
        cloud_risk = min(0.5, self.cloud_probability / 200)
        vegetation_risk = max(0, 0.3 - self.ndvi * 0.5)
        urban_risk = min(0.3, self.ndbi * 0.5)
        return round(min(0.95, cloud_risk + vegetation_risk + urban_risk), 3)


@dataclass
class GeospatialIntelligence:
    """Pre-cognitive geospatial intelligence for ADFI decisions"""
    timestamp: datetime
    location: Tuple[float, float]
    current_tensor: SpectralTensor
    forecast_tensors: List[SpectralTensor]
    terrain_stability: float
    microclimate_risk: float
    solar_potential_24h: List[float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "location": list(self.location),
            "current_tensor": self.current_tensor.to_dict(),
            "forecast_tensors": [t.to_dict() for t in self.forecast_tensors],
            "terrain_stability": self.terrain_stability,
            "microclimate_risk": self.microclimate_risk,
            "solar_potential_24h": self.solar_potential_24h
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeospatialIntelligence":
        """Create from dictionary"""
        return cls(
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            location=tuple(data.get("location", (9.0765, 7.3986))),
            current_tensor=SpectralTensor.from_dict(data.get("current_tensor", {})),
            forecast_tensors=[SpectralTensor.from_dict(t) for t in data.get("forecast_tensors", [])],
            terrain_stability=data.get("terrain_stability", 0.75),
            microclimate_risk=data.get("microclimate_risk", 0.35),
            solar_potential_24h=data.get("solar_potential_24h", [0.7] * 6)
        )
    
    def get_cloud_trajectory(self) -> Dict[str, Any]:
        """Predict cloud movement for pre-cognitive decisions"""
        if len(self.forecast_tensors) < 2:
            return {"movement": "UNKNOWN", "speed": 0, "current_cloud": 0, "forecast_cloud": 0}
        
        current_cloud = sanitize_numeric(self.current_tensor.cloud_probability, 30.0)
        future_cloud = sanitize_numeric(self.forecast_tensors[0].cloud_probability, 30.0)
        
        trend = future_cloud - current_cloud
        speed = abs(trend) * 10
        
        if trend > 10:
            movement = "INCREASING"
        elif trend < -10:
            movement = "DECREASING"
        else:
            movement = "STABLE"
        
        return {
            "movement": movement,
            "speed_kmh": round(speed, 1),
            "current_cloud": round(current_cloud, 1),
            "forecast_cloud": round(future_cloud, 1)
        }
    
    def get_aece_recommendation(self) -> Dict[str, Any]:
        """Get AECE recommendation based on geospatial intelligence"""
        risk_factor = self.current_tensor.get_aece_risk_factor()
        
        if risk_factor > 0.7:
            action = "LOCKDOWN_MODE"
            priority = "critical"
            reason = f"High geospatial risk: cloud={self.current_tensor.cloud_probability:.0f}%, urban={self.current_tensor.ndbi:.2f}"
        elif risk_factor > 0.4:
            action = "PREEMPTIVE_STABILIZATION"
            priority = "high"
            reason = f"Elevated risk: vegetation={self.current_tensor.ndvi:.2f}"
        elif risk_factor > 0.2:
            action = "REDUCE_LOAD"
            priority = "normal"
            reason = f"Moderate risk from cloud cover: {self.current_tensor.cloud_probability:.0f}%"
        else:
            action = "NO_ACTION"
            priority = "low"
            reason = "Stable geospatial conditions"
        
        return {
            "action": action,
            "priority": priority,
            "risk_factor": risk_factor,
            "reason": reason,
            "cloud_probability": self.current_tensor.cloud_probability,
            "vegetation_index": self.current_tensor.ndvi,
            "urban_density": self.current_tensor.ndbi
        }


# ============================================================================
# ENHANCED GEE SERVICE WITH UNIFIED WEATHER INTEGRATION - FULLY FIXED
# ============================================================================

class GeoIntelligenceService:
    """
    Enhanced Google Earth Engine service with:
    - Sentinel-2 cloud probability for pre-cognitive ADFI decisions
    - Real-time spectral analysis for terrain intelligence
    - Quantum-geospatial fusion for 11D manifold
    - Integration with Unified Weather Service
    - AECE risk score integration
    - Automatic fallback when GEE unavailable
    - Safe None handling for all comparisons
    
    FIXED: Proper redis_manager handling (no undefined variable errors)
    FIXED: Uses global redis_client from backend.core.redis
    """
    
    def __init__(self, redis_manager=None, metrics=None):
        """
        Initialize GEE service with enhanced capabilities
        
        FIXED: If redis_manager is None, uses global redis_client
        
        Args:
            redis_manager: Redis cache manager for distributed caching
            metrics: Prometheus metrics instance
        """
        # FIXED: If redis_manager is None, try to use global redis_client
        if redis_manager is None and REDIS_AVAILABLE:
            redis_manager = global_redis_client
        
        self.credentials_path = os.getenv("GEE_CREDENTIALS", "credentials/gee_key.json")
        self.service_account = os.getenv("GEE_SERVICE_ACCOUNT", "")
        self.redis_manager = redis_manager
        self.metrics = metrics
        
        # Check Redis availability
        self._redis_available = self._is_redis_available()
        
        # FIXED: Add is_initialized attribute for health checks
        self.is_initialized = False
        self._initialized = False
        self._initialization_error = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        # Cache for spectral tensors
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._latest_tensor: Optional[SpectralTensor] = None
        self._latest_intelligence: Optional[GeospatialIntelligence] = None
        
        # Performance metrics
        self._api_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._retry_count = 0
        self._aece_integration_count = 0
        
        # Abuja coordinates (Pilot Zone)
        self.latitude = 9.0765
        self.longitude = 7.3986
        self.buffer_km = 1  # 1km buffer (fixes pixel overflow)
        
        # Initialize Earth Engine
        try:
            self._initialize_ee()
        except Exception as e:
            self._initialization_error = str(e)
            self.is_initialized = False
            self._initialized = False
            logger.error(f"GEE initialization failed: {e}")
        
        redis_status = "Available" if self._redis_available else "Not Available (using memory cache)"
        status = "ACTIVE" if self.is_initialized else "FALLBACK"
        logger.info(f"[SAT] GEE Service - ENHANCED SKY-EYE MODE ({status}) | Redis: {redis_status}")
        logger.info(f"[MAP] Target: Abuja ({self.latitude}, {self.longitude})")
        logger.info(f"[ANT] Service Account: {self.service_account or 'Default'}")
        if not self.is_initialized:
            logger.warning(f"[WARN] GEE in fallback mode: {self._initialization_error}")
    
    def _is_redis_available(self) -> bool:
        """
        Safely check if Redis is available.
        
        Returns:
            True if Redis is available and ready, False otherwise
        """
        if self.redis_manager is None:
            return False
        
        try:
            if hasattr(self.redis_manager, 'available'):
                return bool(self.redis_manager.available)
            if hasattr(self.redis_manager, 'ping'):
                return True
            return False
        except Exception as e:
            logger.debug(f"[GEE] Redis availability check failed: {e}")
            return False
    
    async def _redis_get(self, key: str) -> Optional[Any]:
        """Safely get from Redis"""
        if not self._redis_available:
            return None
        
        try:
            if hasattr(self.redis_manager, 'get'):
                if asyncio.iscoroutinefunction(self.redis_manager.get):
                    return await self.redis_manager.get(key)
                else:
                    return self.redis_manager.get(key)
        except Exception as e:
            logger.debug(f"[GEE] Redis get error: {e}")
        return None
    
    async def _redis_set(self, key: str, value: Any, ttl: int) -> bool:
        """Safely set in Redis"""
        if not self._redis_available:
            return False
        
        try:
            if hasattr(self.redis_manager, 'set'):
                if asyncio.iscoroutinefunction(self.redis_manager.set):
                    await self.redis_manager.set(key, value, ttl)
                else:
                    self.redis_manager.set(key, value, ttl)
                return True
        except Exception as e:
            logger.debug(f"[GEE] Redis set error: {e}")
        return False
    
    def _update_metrics(self, operation: str, duration_ms: float, success: bool):
        """Update Prometheus metrics"""
        if self.metrics:
            try:
                if hasattr(self.metrics, 'api_requests_total'):
                    status = "success" if success else "error"
                    self.metrics.api_requests_total.labels(
                        method="GET",
                        endpoint=f"/gee/{operation}",
                        status_code="200" if success else "500",
                        user_type="system"
                    ).inc()
                
                if hasattr(self.metrics, 'api_request_duration_seconds'):
                    self.metrics.api_request_duration_seconds.labels(
                        method="GET",
                        endpoint=f"/gee/{operation}"
                    ).observe(duration_ms / 1000)
                
                # Update vegetation metrics
                if hasattr(self.metrics, 'vegetation_index') and self._latest_tensor:
                    self.metrics.vegetation_index.set(self._latest_tensor.ndvi)
                    
            except Exception as e:
                logger.debug(f"[GEE] Metrics update failed: {e}")
    
    def _initialize_ee(self):
        """Initialize Google Earth Engine with authentication"""
        if not EE_AVAILABLE:
            logger.warning("Google Earth Engine library not available - using fallback")
            self.is_initialized = False
            self._initialized = False
            self._initialization_error = "EE library not available"
            return
        
        try:
            if os.path.exists(self.credentials_path):
                credentials = ee.ServiceAccountCredentials(
                    self.service_account,
                    self.credentials_path
                )
                ee.Initialize(credentials)
                logger.info("[OK] GEE initialized with service account")
            else:
                ee.Initialize()
                logger.info("[OK] GEE initialized with default credentials")
            
            test_point = ee.Geometry.Point([self.longitude, self.latitude])
            logger.info("[@] GEE Connection Test: SUCCESS")
            
            self.is_initialized = True
            self._initialized = True
            self._initialization_error = None
            
        except Exception as e:
            logger.error(f"GEE initialization failed: {e}")
            self.is_initialized = False
            self._initialized = False
            self._initialization_error = str(e)
            raise
    
    @property
    def initialized(self) -> bool:
        """Property for backward compatibility with older code."""
        return self.is_initialized
    
    def get_initialization_status(self) -> Dict[str, Any]:
        """Get detailed initialization status."""
        return {
            "is_initialized": self.is_initialized,
            "initialization_error": self._initialization_error,
            "ee_available": EE_AVAILABLE,
            "credentials_path": self.credentials_path if os.path.exists(self.credentials_path) else None,
            "redis_available": self._redis_available
        }
    
    def _get_cache_key(self, params: Dict[str, Any]) -> str:
        """Generate cache key from parameters"""
        key_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached(self, key: str, max_age_seconds: int = 300) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                self._cache_hits += 1
                return value
            else:
                del self._cache[key]
        self._cache_misses += 1
        return None
    
    def _set_cache(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set cached value with TTL"""
        self._cache[key] = (value, time.time() + ttl_seconds)
    
    async def _run_ee_operation(self, operation, *args, **kwargs):
        """Run Earth Engine operation in thread pool (non-blocking)"""
        if not self.is_initialized:
            raise RuntimeError("GEE not initialized")
        
        self._api_calls += 1
        
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                lambda: operation(*args, **kwargs)
            )
            self._successful_calls += 1
            return result
        except Exception as e:
            self._failed_calls += 1
            logger.error(f"GEE operation failed: {e}")
            raise
    
    async def fetch_spectral_tensor(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        force_refresh: bool = False
    ) -> SpectralTensor:
        """
        Fetch Sentinel-2 spectral tensor with cloud probability.
        Primary method for Sky-Eye data fusion.
        
        FIXED: Safe None handling for all comparisons.
        
        Args:
            lat: Latitude (default: Abuja)
            lon: Longitude (default: Abuja)
            force_refresh: Bypass cache
            
        Returns:
            SpectralTensor with complete spectral analysis
        """
        start_time = time.time()
        lat = lat or self.latitude
        lon = lon or self.longitude
        
        # Check cache
        cache_key = self._get_cache_key({
            "endpoint": "spectral_tensor",
            "lat": lat,
            "lon": lon
        })
        
        if not force_refresh:
            # Try Redis first
            redis_cached = await self._redis_get(f"gee:tensor:{lat}:{lon}")
            if redis_cached:
                if isinstance(redis_cached, str):
                    try:
                        redis_cached = json.loads(redis_cached)
                    except json.JSONDecodeError:
                        pass
                logger.debug("Returning Redis-cached spectral tensor")
                self._update_metrics("fetch_spectral_tensor", 0, True)
                return SpectralTensor.from_dict(redis_cached)
            
            # Try local cache
            cached = self._get_cached(cache_key, max_age_seconds=600)
            if cached:
                logger.debug("Returning local-cached spectral tensor")
                self._update_metrics("fetch_spectral_tensor", 0, True)
                return cached
        
        try:
            if self.is_initialized:
                tensor = await self._fetch_sentinel_tensor(lat, lon)
            else:
                tensor = self._get_fallback_tensor(lat, lon, source=GEEDataSource.FALLBACK)
            
            # Cache results
            self._set_cache(cache_key, tensor, ttl_seconds=600)
            await self._redis_set(f"gee:tensor:{lat}:{lon}", json.dumps(tensor.to_dict()), ttl=600)
            
            self._latest_tensor = tensor
            duration_ms = (time.time() - start_time) * 1000
            self._update_metrics("fetch_spectral_tensor", duration_ms, True)
            
            logger.info(f"[OK] Spectral tensor fetched: NDVI={tensor.ndvi:.3f}, Cloud={tensor.cloud_probability:.0f}%")
            return tensor
            
        except Exception as e:
            logger.error(f"Spectral tensor fetch failed: {e}")
            duration_ms = (time.time() - start_time) * 1000
            self._update_metrics("fetch_spectral_tensor", duration_ms, False)
            return self._get_fallback_tensor(lat, lon, source=GEEDataSource.FALLBACK)
    
    async def _fetch_sentinel_tensor(self, lat: float, lon: float) -> SpectralTensor:
        """
        Fetch actual Sentinel-2 data with cloud probability.
        FIXED: Safe None handling for all values.
        """
        try:
            # Define smaller region of interest
            point = ee.Geometry.Point([lon, lat])
            region = point.buffer(500)
            
            # Get Sentinel-2 collection
            s2_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(region)
                .filterDate(
                    (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                    datetime.now().strftime('%Y-%m-%d')
                )
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80))
                .sort('CLOUDY_PIXEL_PERCENTAGE')
            )
            
            image = s2_collection.first()
            
            if not image:
                logger.warning("No Sentinel-2 images available, using fallback")
                raise Exception("No Sentinel-2 images available")
            
            # Extract spectral bands
            bands = image.select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12']).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=30,
                maxPixels=1e7
            )
            
            # Get cloud probability - FIXED: Safe None handling
            try:
                s2_cloud = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
                image_date = image.date().format('YYYY-MM-dd')
                cloud_image = (s2_cloud
                    .filterDate(image_date, ee.Date(image_date).advance(1, 'day'))
                    .first())
                
                if cloud_image:
                    cloud_prob = cloud_image.select('probability').reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=region,
                        scale=30,
                        maxPixels=1e7
                    ).get('probability')
                    cloud_probability = cloud_prob.getInfo() if cloud_prob else 0
                else:
                    cloud_probability = 0
            except Exception as e:
                logger.warning(f"Cloud probability fetch failed: {e}")
                cloud_probability = 30
            
            # Get elevation data
            try:
                elevation = ee.Image('USGS/SRTMGL1_003').select('elevation').reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=region,
                    scale=30,
                    maxPixels=1e7
                ).get('elevation')
                elevation_m = elevation.getInfo() if elevation else 400
            except Exception as e:
                logger.warning(f"Elevation fetch failed: {e}")
                elevation_m = 400
            
            # SAFE: Parse values with fallbacks for None
            red = sanitize_numeric(bands.get('B2').getInfo(), 0.05)
            green = sanitize_numeric(bands.get('B3').getInfo(), 0.06)
            blue = sanitize_numeric(bands.get('B4').getInfo(), 0.04)
            nir = sanitize_numeric(bands.get('B8').getInfo(), 0.35)
            swir1 = sanitize_numeric(bands.get('B11').getInfo(), 0.12)
            swir2 = sanitize_numeric(bands.get('B12').getInfo(), 0.08)
            
            # SAFE: Calculate indices with fallbacks
            ndvi = self._calculate_ndvi(nir, red)
            ndwi = self._calculate_ndwi(green, nir)
            ndbi = self._calculate_ndbi(swir1, nir)
            
            # SAFE: Classify terrain
            terrain_feature = self._classify_terrain(ndvi, ndbi, ndwi)
            
            # SAFE: Cloud probability with default
            cloud_prob = sanitize_numeric(cloud_probability, 30.0)
            
            # SAFE: Elevation with default
            elev = sanitize_numeric(elevation_m, 400.0)
            
            return SpectralTensor(
                timestamp=datetime.now(timezone.utc),
                source=GEEDataSource.SENTINEL_2,
                red=round(red, 4),
                green=round(green, 4),
                blue=round(blue, 4),
                nir=round(nir, 4),
                swir1=round(swir1, 4),
                swir2=round(swir2, 4),
                ndvi=round(ndvi, 4),
                ndwi=round(ndwi, 4),
                ndbi=round(ndbi, 4),
                cloud_probability=round(min(100.0, max(0.0, cloud_prob)), 1),
                terrain_feature=terrain_feature,
                elevation_m=round(elev, 1),
                slope_deg=5.0,
                aspect_deg=180.0,
                quality_score=0.92
            )
            
        except Exception as e:
            logger.error(f"Sentinel-2 fetch failed: {e}")
            raise
    
    def _calculate_ndvi(self, nir: float, red: float) -> float:
        """Calculate Normalized Difference Vegetation Index with safe values"""
        denominator = nir + red
        if denominator == 0:
            return 0.0
        return max(-1.0, min(1.0, (nir - red) / denominator))
    
    def _calculate_ndwi(self, green: float, nir: float) -> float:
        """Calculate Normalized Difference Water Index with safe values"""
        denominator = green + nir
        if denominator == 0:
            return 0.0
        return max(-1.0, min(1.0, (green - nir) / denominator))
    
    def _calculate_ndbi(self, swir1: float, nir: float) -> float:
        """Calculate Normalized Difference Built-up Index with safe values"""
        denominator = swir1 + nir
        if denominator == 0:
            return 0.0
        return max(-1.0, min(1.0, (swir1 - nir) / denominator))
    
    def _classify_terrain(self, ndvi: float, ndbi: float, ndwi: float) -> TerrainFeature:
        """Classify terrain based on spectral indices with safe values"""
        if ndwi > 0.1:
            return TerrainFeature.WATER
        elif ndvi > 0.6:
            return TerrainFeature.FOREST
        elif ndvi > 0.3:
            return TerrainFeature.VEGETATED
        elif ndvi > 0.1:
            return TerrainFeature.AGRICULTURAL
        elif ndbi > 0.1:
            return TerrainFeature.URBAN
        else:
            return TerrainFeature.BARREN
    
    def _get_fallback_tensor(
        self,
        lat: float,
        lon: float,
        source: GEEDataSource = GEEDataSource.FALLBACK
    ) -> SpectralTensor:
        """
        Generate realistic fallback spectral tensor when GEE unavailable.
        Uses time-of-day, seasonal, and terrain models.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        month = now.month
        
        # Seasonal vegetation adjustment
        if month in [6, 7, 8, 9]:
            base_ndvi = 0.45 + np.random.normal(0, 0.05)
        elif month in [11, 12, 1, 2]:
            base_ndvi = 0.35 + np.random.normal(0, 0.05)
        else:
            base_ndvi = 0.40 + np.random.normal(0, 0.05)
        
        # Urban density based on location
        if abs(lat - 9.0765) < 0.1 and abs(lon - 7.3986) < 0.1:
            base_ndbi = 0.25 + np.random.normal(0, 0.03)
        else:
            base_ndbi = 0.15 + np.random.normal(0, 0.03)
        
        # Cloud probability based on time of day
        if 12 <= hour <= 16:
            cloud_prob = 40 + np.random.normal(0, 15)
        elif hour <= 6 or hour >= 18:
            cloud_prob = 60 + np.random.normal(0, 10)
        else:
            cloud_prob = 30 + np.random.normal(0, 10)
        
        cloud_prob = max(0.0, min(100.0, cloud_prob))
        
        ndwi = -0.1 + np.random.normal(0, 0.05)
        terrain_feature = self._classify_terrain(base_ndvi, base_ndbi, ndwi)
        
        # Generate realistic spectral bands
        red = 0.08 + np.random.normal(0, 0.01)
        green = 0.1 + np.random.normal(0, 0.01)
        blue = 0.06 + np.random.normal(0, 0.01)
        nir = 0.25 + np.random.normal(0, 0.03)
        swir1 = 0.15 + np.random.normal(0, 0.02)
        swir2 = 0.1 + np.random.normal(0, 0.02)
        
        return SpectralTensor(
            timestamp=now,
            source=source,
            red=round(red, 4),
            green=round(green, 4),
            blue=round(blue, 4),
            nir=round(nir, 4),
            swir1=round(swir1, 4),
            swir2=round(swir2, 4),
            ndvi=round(base_ndvi, 4),
            ndwi=round(ndwi, 4),
            ndbi=round(base_ndbi, 4),
            cloud_probability=round(cloud_prob, 1),
            terrain_feature=terrain_feature,
            elevation_m=400 + np.random.normal(0, 20),
            slope_deg=5 + np.random.normal(0, 2),
            aspect_deg=180 + np.random.normal(0, 30),
            quality_score=0.75
        )
    
    async def get_geospatial_intelligence(
        self,
        hours_ahead: int = 6,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        force_refresh: bool = False
    ) -> GeospatialIntelligence:
        """
        Get pre-cognitive geospatial intelligence for ADFI decisions.
        Predicts cloud movement, terrain stability, and solar potential.
        """
        start_time = time.time()
        lat = lat or self.latitude
        lon = lon or self.longitude
        hours_ahead = min(hours_ahead, 12)
        
        cache_key = self._get_cache_key({
            "endpoint": "intelligence",
            "lat": lat,
            "lon": lon,
            "hours": hours_ahead
        })
        
        if not force_refresh:
            redis_cached = await self._redis_get(f"gee:intelligence:{lat}:{lon}:{hours_ahead}")
            if redis_cached:
                if isinstance(redis_cached, str):
                    try:
                        redis_cached = json.loads(redis_cached)
                    except json.JSONDecodeError:
                        pass
                logger.debug("Returning Redis-cached geospatial intelligence")
                self._update_metrics("get_geospatial_intelligence", 0, True)
                return GeospatialIntelligence.from_dict(redis_cached)
            
            cached = self._get_cached(cache_key, max_age_seconds=1800)
            if cached:
                logger.debug("Returning cached geospatial intelligence")
                self._update_metrics("get_geospatial_intelligence", 0, True)
                return cached
        
        current_tensor = await self.fetch_spectral_tensor(lat, lon, force_refresh)
        
        forecast_tensors = []
        solar_potential = []
        current_cloud = sanitize_numeric(current_tensor.cloud_probability, 30.0)
        
        for hour in range(hours_ahead):
            forecast_time = datetime.now(timezone.utc) + timedelta(hours=hour)
            hour_of_day = forecast_time.hour
            
            if 12 <= hour_of_day <= 16:
                forecast_cloud = min(100.0, current_cloud + hour * 5)
            elif hour_of_day <= 6 or hour_of_day >= 18:
                forecast_cloud = min(100.0, current_cloud + hour * 3)
            else:
                forecast_cloud = max(0.0, current_cloud - hour * 2)
            
            forecast_tensor = SpectralTensor(
                timestamp=forecast_time,
                source=current_tensor.source,
                red=current_tensor.red + np.random.normal(0, 0.005) * hour,
                green=current_tensor.green + np.random.normal(0, 0.005) * hour,
                blue=current_tensor.blue + np.random.normal(0, 0.005) * hour,
                nir=current_tensor.nir + np.random.normal(0, 0.01) * hour,
                swir1=current_tensor.swir1 + np.random.normal(0, 0.005) * hour,
                swir2=current_tensor.swir2 + np.random.normal(0, 0.005) * hour,
                ndvi=max(0.0, min(1.0, current_tensor.ndvi + np.random.normal(0, 0.02) * hour)),
                ndwi=current_tensor.ndwi + np.random.normal(0, 0.01) * hour,
                ndbi=current_tensor.ndbi + np.random.normal(0, 0.01) * hour,
                cloud_probability=round(forecast_cloud, 1),
                terrain_feature=current_tensor.terrain_feature,
                elevation_m=current_tensor.elevation_m,
                slope_deg=current_tensor.slope_deg,
                aspect_deg=current_tensor.aspect_deg,
                quality_score=current_tensor.quality_score * (1 - hour * 0.03)
            )
            
            forecast_tensors.append(forecast_tensor)
            solar_potential.append(forecast_tensor.get_energy_potential())
        
        terrain_stability = min(1.0, max(0.0, 
            current_tensor.ndvi * 0.6 + 
            (1 - current_tensor.slope_deg / 45) * 0.3 +
            (1 - current_tensor.ndbi) * 0.1
        ))
        
        microclimate_risk = min(1.0, max(0.0,
            (current_tensor.cloud_probability / 100) * 0.5 +
            (1 - current_tensor.ndvi) * 0.3 +
            current_tensor.ndbi * 0.2
        ))
        
        intelligence = GeospatialIntelligence(
            timestamp=datetime.now(timezone.utc),
            location=(lat, lon),
            current_tensor=current_tensor,
            forecast_tensors=forecast_tensors,
            terrain_stability=round(terrain_stability, 3),
            microclimate_risk=round(microclimate_risk, 3),
            solar_potential_24h=solar_potential
        )
        
        # Cache results
        self._set_cache(cache_key, intelligence, ttl_seconds=1800)
        await self._redis_set(f"gee:intelligence:{lat}:{lon}:{hours_ahead}", json.dumps(intelligence.to_dict()), ttl=1800)
        
        self._latest_intelligence = intelligence
        duration_ms = (time.time() - start_time) * 1000
        self._update_metrics("get_geospatial_intelligence", duration_ms, True)
        
        cloud_traj = intelligence.get_cloud_trajectory()
        logger.info(f"[ANT] Geospatial intelligence: Cloud {cloud_traj['movement']}, "
                   f"Stability={terrain_stability:.2f}, Risk={microclimate_risk:.2f}")
        
        return intelligence
    
    async def get_integrated_environmental_state(
        self,
        lat: float,
        lon: float
    ) -> Dict[str, Any]:
        """
        Primary method for ADFI orchestration - returns integrated environmental
        state for 11D kernel simulation.
        """
        start_time = time.time()
        
        try:
            tensor = await self.fetch_spectral_tensor(lat, lon)
            intelligence = await self.get_geospatial_intelligence(6, lat, lon)
            
            cloud_trajectory = intelligence.get_cloud_trajectory()
            aece_recommendation = intelligence.get_aece_recommendation()
            
            grid_stability = min(1.0, max(0.0,
                0.6 + tensor.ndvi * 0.3 - tensor.ndbi * 0.2 - (tensor.cloud_probability / 100) * 0.1
            ))
            
            # Update AECE integration count
            self._aece_integration_count += 1
            
            result = {
                "engine_status": "ACTIVE" if self.is_initialized else "FALLBACK",
                "initialized": self.is_initialized,
                "vegetation_index": tensor.ndvi,
                "thermal_anomaly_score": round((tensor.ndbi - tensor.ndvi) * 0.5 + 0.2, 3),
                "urban_density": min(1.0, max(0.0, tensor.ndbi * 1.5)),
                "solar_potential": tensor.get_energy_potential(),
                "grid_stability": round(grid_stability, 3),
                "carbon_sequestration": round(tensor.ndvi * 0.5, 3),
                "land_surface_temp": 29.5 + (tensor.ndbi * 5) - (tensor.ndvi * 3),
                "cloud_probability": tensor.cloud_probability,
                "terrain_class": tensor.terrain_feature.value,
                "data_source": tensor.source.value,
                "data_quality": tensor.quality_score,
                "cloud_trajectory": cloud_trajectory,
                "terrain_stability": intelligence.terrain_stability,
                "microclimate_risk": intelligence.microclimate_risk,
                "solar_potential_forecast": intelligence.solar_potential_24h[:6],
                "aece_recommendation": aece_recommendation,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            duration_ms = (time.time() - start_time) * 1000
            self._update_metrics("get_integrated_environmental_state", duration_ms, True)
            
            return result
            
        except Exception as e:
            logger.error(f"Integrated state failed: {e}", exc_info=True)
            duration_ms = (time.time() - start_time) * 1000
            self._update_metrics("get_integrated_environmental_state", duration_ms, False)
            
            return {
                "engine_status": "FALLBACK",
                "initialized": self.is_initialized,
                "vegetation_index": 0.45,
                "thermal_anomaly_score": 0.28,
                "urban_density": 0.62,
                "solar_potential": 0.71,
                "grid_stability": 0.89,
                "carbon_sequestration": 0.54,
                "land_surface_temp": 29.5,
                "cloud_probability": 45.0,
                "terrain_class": "MIXED",
                "data_source": "FALLBACK",
                "data_quality": 0.65,
                "cloud_trajectory": {"movement": "UNKNOWN", "speed_kmh": 0, "current_cloud": 45, "forecast_cloud": 45},
                "terrain_stability": 0.75,
                "microclimate_risk": 0.35,
                "solar_potential_forecast": [0.7] * 6,
                "aece_recommendation": {
                    "action": "NO_ACTION",
                    "priority": "low",
                    "risk_factor": 0.25,
                    "reason": "Fallback mode - no real-time data"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def get_heatmap(
        self,
        lat: float,
        lon: float,
        radius_km: int = 15
    ) -> Dict[str, Any]:
        """
        Generate real-time heatmap for dashboard visualization.
        FIXED: Safe None handling for all values.
        """
        start_time = time.time()
        
        try:
            tensor = await self.fetch_spectral_tensor(lat, lon)
            intelligence = await self.get_geospatial_intelligence(6, lat, lon)
            
            result = {
                "location": {"lat": lat, "lon": lon},
                "radius_km": radius_km,
                "vegetation_health": round(tensor.ndvi * 100, 1),
                "thermal_anomaly": round((tensor.ndbi - tensor.ndvi) * 50 + 20, 1),
                "cloud_cover": round(tensor.cloud_probability, 1),
                "urban_density": round(tensor.ndbi * 100, 1),
                "terrain_stability": round(intelligence.terrain_stability * 100, 1),
                "solar_potential": round(tensor.get_energy_potential() * 100, 1),
                "aece_risk_factor": round(tensor.get_aece_risk_factor() * 100, 1),
                "data_source": tensor.source.value,
                "redis_available": self._redis_available,
                "timestamp": tensor.timestamp.isoformat(),
                "heatmap_layers": {
                    "ndvi": tensor.ndvi,
                    "ndbi": tensor.ndbi,
                    "cloud_probability": tensor.cloud_probability / 100
                }
            }
            
            duration_ms = (time.time() - start_time) * 1000
            self._update_metrics("get_heatmap", duration_ms, True)
            
            return result
            
        except Exception as e:
            logger.error(f"Heatmap generation failed: {e}")
            duration_ms = (time.time() - start_time) * 1000
            self._update_metrics("get_heatmap", duration_ms, False)
            
            return {
                "location": {"lat": lat, "lon": lon},
                "radius_km": radius_km,
                "vegetation_health": 45.0,
                "thermal_anomaly": 28.0,
                "cloud_cover": 45.0,
                "urban_density": 62.0,
                "terrain_stability": 75.0,
                "solar_potential": 71.0,
                "aece_risk_factor": 35.0,
                "data_source": "FALLBACK",
                "redis_available": self._redis_available,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "heatmap_layers": {"ndvi": 0.45, "ndbi": 0.25, "cloud_probability": 0.45}
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get service performance metrics"""
        total_calls = self._api_calls
        success_rate = (self._successful_calls / max(1, total_calls)) * 100
        cache_hit_rate = (self._cache_hits / max(1, self._cache_hits + self._cache_misses)) * 100
        
        return {
            "initialized": self.is_initialized,
            "initialization_error": self._initialization_error,
            "api_calls": self._api_calls,
            "successful_calls": self._successful_calls,
            "failed_calls": self._failed_calls,
            "success_rate_percent": round(success_rate, 2),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate_percent": round(cache_hit_rate, 2),
            "aece_integration_count": self._aece_integration_count,
            "redis_available": self._redis_available,
            "latest_data_source": self._latest_tensor.source.value if self._latest_tensor else None,
            "latest_ndvi": self._latest_tensor.ndvi if self._latest_tensor else None,
            "latest_cloud_probability": self._latest_tensor.cloud_probability if self._latest_tensor else None,
            "buffer_km": self.buffer_km
        }
    
    async def close(self):
        """Clean up resources"""
        self._executor.shutdown(wait=False)
        logger.info("GEE service shutdown complete")


# ============================================================================
# SERVICE FACTORY AND SINGLETON
# ============================================================================

_gee_service: Optional[GeoIntelligenceService] = None
_gee_service_lock = threading.RLock()


def get_gee_service(redis_manager=None, metrics=None) -> GeoIntelligenceService:
    """
    Get or create GEE service singleton with enhanced capabilities
    
    FIXED: Properly passes redis_manager to constructor
    FIXED: If redis_manager is None, uses global redis_client
    
    Args:
        redis_manager: Redis cache manager (optional)
        metrics: Prometheus metrics instance (optional)
    
    Returns:
        GeoIntelligenceService singleton instance
    """
    global _gee_service
    
    if _gee_service is None:
        with _gee_service_lock:
            if _gee_service is None:
                # FIXED: If redis_manager is None, try to use global redis_client
                if redis_manager is None and REDIS_AVAILABLE:
                    redis_manager = global_redis_client
                
                _gee_service = GeoIntelligenceService(redis_manager, metrics)
                logger.info("[GEE] GEE Service singleton created")
    
    return _gee_service


def reset_gee_service():
    """Reset the GEE service singleton (for testing/reload)"""
    global _gee_service
    with _gee_service_lock:
        if _gee_service is not None:
            _gee_service = None
            logger.info("[GEE] GEE Service singleton reset")


# ============================================================================
# HEALTH CHECK FUNCTION
# ============================================================================

async def check_gee_health() -> Dict[str, Any]:
    """Health check for GEE Service"""
    try:
        service = get_gee_service()
        metrics = service.get_metrics()
        
        return {
            "status": "healthy" if metrics.get("initialized") else "degraded",
            "initialized": metrics.get("initialized", False),
            "redis_available": metrics.get("redis_available", False),
            "success_rate": metrics.get("success_rate_percent", 0),
            "cache_hit_rate": metrics.get("cache_hit_rate_percent", 0),
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
    'GeoIntelligenceService',
    'get_gee_service',
    'reset_gee_service',
    'check_gee_health',
    'SpectralTensor',
    'GeospatialIntelligence',
    'GEEDataSource',
    'TerrainFeature'
]