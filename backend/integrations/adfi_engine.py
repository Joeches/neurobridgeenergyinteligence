# backend/integrations/adfi_engine.py - PRODUCTION CLEAN v3.1.1
# ADFI Engine - Data Fabric Integration Layer

import asyncio
import logging
import time
import json
import hashlib
import uuid
import threading
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Union, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque

# ============================================================================
# LOGGING
# ============================================================================

logger = logging.getLogger(__name__)

# Single concise initialization log - NO BANNER
logger.info("[ADFI] engine initializing")

# ============================================================================
# ENUMS WITH SAFE TYPE CONVERSION
# ============================================================================

class DataSourceType(str, Enum):
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    HARDWARE = "hardware"
    API_LIVE = "api_live"
    SYNTHETIC = "synthetic"
    NASA_POWER = "nasa_power"
    OPENWEATHER = "openweather"
    GOOGLE_EARTH = "google_earth"
    REDIS_CACHE = "redis_cache"
    FALLBACK = "fallback"
    
    @classmethod
    def to_enum(cls, source_type: Any) -> "DataSourceType":
        try:
            if isinstance(source_type, cls):
                return source_type
            if isinstance(source_type, str):
                return cls(source_type.lower())
            if hasattr(source_type, 'value'):
                return cls.to_enum(source_type.value)
            return cls.FALLBACK
        except (ValueError, TypeError, AttributeError):
            return cls.FALLBACK


class DataPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BULK = "bulk"
    
    @classmethod
    def to_enum(cls, priority: Any) -> "DataPriority":
        try:
            if isinstance(priority, cls):
                return priority
            if isinstance(priority, str):
                return cls(priority.lower())
            if hasattr(priority, 'value'):
                return cls.to_enum(priority.value)
            return cls.NORMAL
        except (ValueError, TypeError, AttributeError):
            return cls.NORMAL


class DataQuality(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    DEGRADED = "degraded"
    UNRELIABLE = "unreliable"
    INVALID = "invalid"


class StreamStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNSTABLE = "unstable"
    OFFLINE = "offline"
    RECOVERING = "recovering"


class DataTransformation(str, Enum):
    NONE = "none"
    NORMALIZE = "normalize"
    STANDARDIZE = "standardize"
    SMOOTH = "smooth"
    INTERPOLATE = "interpolate"
    DETREND = "detrend"
    RESAMPLE = "resample"
    FOURIER = "fourier"
    WAVELET = "wavelet"
    ENRICH = "enrich"
    SCALE = "scale"
    FILTER = "filter"
    AGGREGATE = "aggregate"
    
    @classmethod
    def to_enum(cls, transform: Any) -> "DataTransformation":
        try:
            if isinstance(transform, cls):
                return transform
            if isinstance(transform, str):
                return cls(transform.lower())
            if hasattr(transform, 'value'):
                return cls.to_enum(transform.value)
            return cls.NONE
        except (ValueError, TypeError, AttributeError):
            return cls.NONE
    
    def apply(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        try:
            if self == DataTransformation.ENRICH:
                result = data.copy()
                if 'active_power_kw' in result and 'solar_output_kw' in result:
                    result['net_power_kw'] = result['active_power_kw'] - result['solar_output_kw']
                if 'grid_frequency_hz' in result:
                    result['frequency_deviation_hz'] = abs(result['grid_frequency_hz'] - 50.0)
                return result
            return data
        except Exception:
            return data

# ============================================================================
# ENERGY DATA POINT
# ============================================================================

@dataclass
class EnergyDataPoint:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source_type: DataSourceType = DataSourceType.FALLBACK
    source_id: str = ""
    quality_score: float = 0.85
    quality_flags: List[str] = field(default_factory=list)
    validation_passed: bool = True
    grid_frequency_hz: Optional[float] = None
    grid_voltage_v: Optional[float] = None
    active_power_kw: Optional[float] = None
    solar_output_kw: Optional[float] = None
    irradiance_wm2: Optional[float] = None
    battery_soc_percent: Optional[float] = None
    temperature_c: Optional[float] = None
    cloud_cover_percent: Optional[float] = None
    aece_risk_factor: Optional[float] = None
    processing_latency_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        try:
            return {k: v.value if isinstance(v, Enum) else v for k, v in asdict(self).items() if v is not None}
        except Exception:
            return {}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["EnergyDataPoint"]:
        try:
            if 'source_type' in data:
                data['source_type'] = DataSourceType.to_enum(data['source_type'])
            return cls(**data)
        except Exception:
            return None
    
    def validate(self) -> Tuple[bool, List[str]]:
        errors = []
        if self.grid_frequency_hz is not None and not (45 <= self.grid_frequency_hz <= 65):
            errors.append(f"Frequency out of range: {self.grid_frequency_hz}")
        if self.irradiance_wm2 is not None and not (0 <= self.irradiance_wm2 <= 1200):
            errors.append(f"Irradiance out of range: {self.irradiance_wm2}")
        self.validation_passed = len(errors) == 0
        self.quality_flags = errors
        return self.validation_passed, errors
    
    def transform(self, transformation: Union[DataTransformation, str], **kwargs) -> "EnergyDataPoint":
        try:
            transform_enum = DataTransformation.to_enum(transformation)
            if transform_enum == DataTransformation.NONE:
                return self
            data_dict = self.to_dict()
            transformed_data = transform_enum.apply(data_dict, **kwargs)
            return EnergyDataPoint(
                id=self.id, timestamp=transformed_data.get('timestamp', self.timestamp),
                source_type=self.source_type, source_id=self.source_id,
                quality_score=self.quality_score, quality_flags=self.quality_flags.copy(),
                validation_passed=self.validation_passed,
                grid_frequency_hz=transformed_data.get('grid_frequency_hz', self.grid_frequency_hz),
                grid_voltage_v=transformed_data.get('grid_voltage_v', self.grid_voltage_v),
                active_power_kw=transformed_data.get('active_power_kw', self.active_power_kw),
                solar_output_kw=transformed_data.get('solar_output_kw', self.solar_output_kw),
                irradiance_wm2=transformed_data.get('irradiance_wm2', self.irradiance_wm2),
                battery_soc_percent=transformed_data.get('battery_soc_percent', self.battery_soc_percent),
                temperature_c=transformed_data.get('temperature_c', self.temperature_c),
                cloud_cover_percent=transformed_data.get('cloud_cover_percent', self.cloud_cover_percent),
                aece_risk_factor=transformed_data.get('aece_risk_factor', self.aece_risk_factor),
                processing_latency_ms=self.processing_latency_ms
            )
        except Exception:
            return self

# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0, success_threshold: int = 2):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._successes = 0
        self._last_failure_time = 0
        self._lock = threading.RLock()
    
    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            return self._state
    
    def record_success(self) -> bool:
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.success_threshold:
                    self._state = CircuitBreakerState.CLOSED
                    self._failures = 0
                    self._successes = 0
            elif self._state == CircuitBreakerState.CLOSED:
                self._failures = 0
            return self._state == CircuitBreakerState.CLOSED
    
    def record_failure(self) -> bool:
        with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    self._last_failure_time = time.time()
            elif self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                self._last_failure_time = time.time()
                self._successes = 0
            return self._state == CircuitBreakerState.CLOSED
    
    def is_allowed(self) -> bool:
        with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return True
            if self._state == CircuitBreakerState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._successes = 0
                    return True
                return False
            return True

# ============================================================================
# UNIVERSAL DATA CONVERTER
# ============================================================================

class UniversalDataConverter:
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._converters: Dict[str, Callable] = {}
        self._register_converters()
        logger.debug("[ADFI] Universal Data Converter initialized")
    
    def _register_converters(self):
        self._converters["modbus"] = self._convert_modbus
        self._converters["json_api"] = self._convert_json_api
        self._converters["hardware"] = self._convert_hardware
        self._converters["synthetic"] = self._convert_synthetic
    
    def convert(self, data: Any, source_format: str, source_type: DataSourceType) -> Optional[EnergyDataPoint]:
        try:
            converter = self._converters.get(source_format.lower() if source_format else "json_api")
            if not converter:
                return self._create_fallback_data_point(source_type)
            result = converter(data, source_type)
            if result and isinstance(result, EnergyDataPoint):
                return result
            return self._create_fallback_data_point(source_type)
        except Exception:
            return self._create_fallback_data_point(source_type)
    
    def _create_fallback_data_point(self, source_type: DataSourceType) -> EnergyDataPoint:
        return EnergyDataPoint(source_type=source_type, quality_score=0.5, quality_flags=["conversion_fallback"])
    
    def _convert_modbus(self, data: Dict, source_type: DataSourceType) -> Optional[EnergyDataPoint]:
        try:
            if not isinstance(data, dict):
                return None
            return EnergyDataPoint(
                source_type=source_type, timestamp=data.get('timestamp', time.time()),
                grid_frequency_hz=data.get('frequency', data.get('grid_frequency_hz')),
                grid_voltage_v=data.get('voltage', data.get('grid_voltage_v')),
                active_power_kw=data.get('power', data.get('active_power_kw')),
                solar_output_kw=data.get('pv_power', data.get('solar_output_kw')),
                quality_score=0.95
            )
        except Exception:
            return None
    
    def _convert_json_api(self, data: Dict, source_type: DataSourceType) -> Optional[EnergyDataPoint]:
        try:
            if not isinstance(data, dict):
                return None
            return EnergyDataPoint(
                source_type=source_type, timestamp=data.get('timestamp', time.time()),
                irradiance_wm2=data.get('ghi_wm2', data.get('irradiance')),
                temperature_c=data.get('temperature_c', data.get('temp')),
                cloud_cover_percent=data.get('cloud_cover_percent', data.get('cloud_cover')),
                quality_score=0.85
            )
        except Exception:
            return None
    
    def _convert_hardware(self, data: Dict, source_type: DataSourceType) -> Optional[EnergyDataPoint]:
        try:
            if not isinstance(data, dict):
                return None
            return EnergyDataPoint(
                source_type=source_type, timestamp=data.get('timestamp', time.time()),
                grid_frequency_hz=data.get('grid_frequency_hz'),
                grid_voltage_v=data.get('grid_voltage_v'),
                active_power_kw=data.get('active_power_kw'),
                temperature_c=data.get('temperature_c'),
                quality_score=0.98
            )
        except Exception:
            return None
    
    def _convert_synthetic(self, data: Dict, source_type: DataSourceType) -> Optional[EnergyDataPoint]:
        try:
            return EnergyDataPoint(
                source_type=source_type, timestamp=data.get('timestamp', time.time()),
                grid_frequency_hz=data.get('grid_frequency_hz', 50.0),
                active_power_kw=data.get('active_power_kw', 500.0),
                quality_score=data.get('quality_score', 0.85)
            )
        except Exception:
            return None

# ============================================================================
# PREDICTIVE CACHE
# ============================================================================

class PredictiveCache:
    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        self._cache: Dict[str, Tuple[EnergyDataPoint, float, float]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._hit_count = 0
        self._miss_count = 0
        logger.debug(f"[ADFI] PredictiveCache initialized max_size={max_size}")
    
    def _get_key(self, source_type: DataSourceType, params: Dict = None) -> str:
        try:
            key = source_type.value if isinstance(source_type, DataSourceType) else str(source_type)
            if params:
                params_str = json.dumps(params, sort_keys=True)
                key = f"{key}:{hashlib.md5(params_str.encode()).hexdigest()[:16]}"
            return key
        except Exception:
            return str(source_type)
    
    def get(self, source_type: DataSourceType, params: Dict = None) -> Optional[EnergyDataPoint]:
        try:
            key = self._get_key(source_type, params)
            now = time.time()
            with self._lock:
                if key in self._cache:
                    data, expiry, _ = self._cache[key]
                    if now < expiry:
                        self._hit_count += 1
                        return data
                    else:
                        del self._cache[key]
            self._miss_count += 1
            return None
        except Exception:
            self._miss_count += 1
            return None
    
    def set(self, source_type: DataSourceType, data: EnergyDataPoint, ttl: int = None, params: Dict = None) -> bool:
        try:
            if not data:
                return False
            key = self._get_key(source_type, params)
            ttl_val = ttl or self._default_ttl
            now = time.time()
            with self._lock:
                if len(self._cache) >= self._max_size:
                    oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][2])
                    del self._cache[oldest_key]
                self._cache[key] = (data, now + ttl_val, now)
                return True
        except Exception:
            return False

# ============================================================================
# ADAPTIVE RATE LIMITER
# ============================================================================

class AdaptiveRateLimiter:
    def __init__(self, default_rate: float = 10.0):
        self._rates: Dict[str, float] = {}
        self._tokens: Dict[str, float] = {}
        self._last_update: Dict[str, float] = {}
        self._default_rate = default_rate
        self._lock = threading.RLock()
    
    def set_rate(self, source_id: str, rate: float) -> bool:
        with self._lock:
            self._rates[source_id] = max(0.1, min(rate, 100.0))
            self._tokens[source_id] = self._rates[source_id]
            self._last_update[source_id] = time.time()
            return True
    
    async def acquire(self, source_id: str) -> bool:
        with self._lock:
            rate = self._rates.get(source_id, self._default_rate)
            now = time.time()
            last = self._last_update.get(source_id, now)
            elapsed = now - last
            new_tokens = elapsed * rate
            current = self._tokens.get(source_id, rate)
            self._tokens[source_id] = min(rate, current + new_tokens)
            self._last_update[source_id] = now
            if self._tokens[source_id] >= 1.0:
                self._tokens[source_id] -= 1.0
                return True
        await asyncio.sleep(min(1.0 / rate, 5.0))
        return await self.acquire(source_id)

# ============================================================================
# ADFI ORCHESTRATOR
# ============================================================================

class ADFIOrchestrator:
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.converter = UniversalDataConverter()
        self.cache = PredictiveCache()
        self.rate_limiter = AdaptiveRateLimiter()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._health_status: Dict[str, StreamStatus] = {}
        self._dead_letter_queue: deque = deque(maxlen=1000)
        self._stats = {"total_requests": 0, "successful_requests": 0, "failed_requests": 0, "startup_time": time.time()}
        logger.info("[ADFI] orchestrator initialized")
    
    def register_source(self, source_id: str, source_type: Union[DataSourceType, str], fetcher: Callable,
                        priority: Union[DataPriority, str] = DataPriority.NORMAL, rate_limit: float = 10.0) -> bool:
        if not source_id or not callable(fetcher):
            return False
        
        source_type_enum = DataSourceType.to_enum(source_type)
        priority_enum = DataPriority.to_enum(priority)
        
        try:
            self._circuit_breakers[source_id] = CircuitBreaker(f"Source:{source_id}", failure_threshold=3, recovery_timeout=30.0)
            self._sources[source_id] = {
                "type": source_type_enum, "fetcher": fetcher, "priority": priority_enum,
                "rate_limit": rate_limit, "registered_at": time.time(),
                "last_success": None, "last_failure": None, "success_count": 0, "failure_count": 0
            }
            self.rate_limiter.set_rate(source_id, rate_limit)
            self._health_status[source_id] = StreamStatus.HEALTHY
            logger.debug(f"[ADFI] registered source={source_id} type={source_type_enum.value}")
            return True
        except Exception:
            return False
    
    async def fetch(self, source_id: str, force_refresh: bool = False) -> Optional[EnergyDataPoint]:
        start_time = time.time()
        self._stats["total_requests"] += 1
        
        try:
            source = self._sources.get(source_id)
            if not source:
                self._stats["failed_requests"] += 1
                return None
            
            cb = self._circuit_breakers.get(source_id)
            if cb and not cb.is_allowed():
                self._stats["failed_requests"] += 1
                return None
            
            if not force_refresh:
                cached = self.cache.get(source["type"])
                if cached:
                    self._stats["successful_requests"] += 1
                    cached.processing_latency_ms = (time.time() - start_time) * 1000
                    return cached
            
            if not await self.rate_limiter.acquire(source_id):
                self._stats["failed_requests"] += 1
                return None
            
            try:
                data = await asyncio.wait_for(source["fetcher"](), timeout=3.0)
                if data:
                    if not isinstance(data, EnergyDataPoint):
                        data = self.converter.convert(data, source["type"].value, source["type"])
                    if data and isinstance(data, EnergyDataPoint):
                        source["success_count"] += 1
                        source["last_success"] = time.time()
                        self._health_status[source_id] = StreamStatus.HEALTHY
                        if cb:
                            cb.record_success()
                        data.processing_latency_ms = (time.time() - start_time) * 1000
                        self.cache.set(source["type"], data)
                        self._stats["successful_requests"] += 1
                        return data
            except (asyncio.TimeoutError, Exception):
                pass
            
            source["failure_count"] += 1
            source["last_failure"] = time.time()
            self._stats["failed_requests"] += 1
            if cb:
                cb.record_failure()
            
            if source["failure_count"] > 10:
                self._health_status[source_id] = StreamStatus.OFFLINE
            elif source["failure_count"] > 5:
                self._health_status[source_id] = StreamStatus.UNSTABLE
            elif source["failure_count"] > 2:
                self._health_status[source_id] = StreamStatus.DEGRADED
            
            return await self._get_fallback_data()
        except Exception:
            self._stats["failed_requests"] += 1
            return await self._get_fallback_data()
    
    async def _get_fallback_data(self) -> Optional[EnergyDataPoint]:
        for source in self._sources.values():
            cached = self.cache.get(source["type"])
            if cached:
                cached.quality_score = 0.6
                return cached
        return EnergyDataPoint(source_type=DataSourceType.FALLBACK, quality_score=0.5,
                              quality_flags=["emergency_fallback"], grid_frequency_hz=50.0, active_power_kw=500.0)
    
    async def orchestrate(self) -> Optional[EnergyDataPoint]:
        start_time = time.time()
        try:
            if not self._sources:
                return EnergyDataPoint(source_type=DataSourceType.FALLBACK, quality_score=0.5,
                                       quality_flags=["orchestration_fallback"], grid_frequency_hz=50.0, active_power_kw=500.0)
            
            scored_sources = []
            for source_id, source in self._sources.items():
                health = self._health_status.get(source_id, StreamStatus.HEALTHY)
                if health == StreamStatus.OFFLINE:
                    continue
                priority_scores = {DataPriority.CRITICAL: 100, DataPriority.HIGH: 80, DataPriority.NORMAL: 60}
                priority_score = priority_scores.get(source["priority"], 50)
                total_attempts = source["success_count"] + source["failure_count"]
                reliability_score = (source["success_count"] / max(1, total_attempts)) * 100
                health_scores = {StreamStatus.HEALTHY: 100, StreamStatus.DEGRADED: 70, StreamStatus.UNSTABLE: 40}
                health_score = health_scores.get(health, 50)
                total_score = priority_score * 0.5 + reliability_score * 0.3 + health_score * 0.2
                scored_sources.append((total_score, source_id))
            
            scored_sources.sort(reverse=True, key=lambda x: x[0])
            for _, source_id in scored_sources:
                data = await self.fetch(source_id, force_refresh=True)
                if data:
                    data.processing_latency_ms = (time.time() - start_time) * 1000
                    return data
            return None
        except Exception:
            return None
    
    def get_status(self) -> Dict[str, Any]:
        try:
            success_rate = round(self._stats["successful_requests"] / max(1, self._stats["total_requests"]) * 100, 1)
            return {
                "success": True, "initialized": self._initialized, "version": "3.1.1",
                "phase": "PHASE_1_PRODUCTION",
                "orchestrator_stats": {"total_requests": self._stats["total_requests"],
                                       "successful_requests": self._stats["successful_requests"],
                                       "failed_requests": self._stats["failed_requests"],
                                       "success_rate": success_rate},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e), "phase": "PHASE_1_PRODUCTION"}
    
    async def transform_data(self, data: EnergyDataPoint, transformation: Union[DataTransformation, str], **kwargs) -> EnergyDataPoint:
        try:
            transform_enum = DataTransformation.to_enum(transformation)
            return data.transform(transform_enum, **kwargs)
        except Exception:
            return data


_orchestrator = None
_orchestrator_lock = threading.RLock()


def get_orchestrator() -> ADFIOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = ADFIOrchestrator()
                logger.info("[ADFI] orchestrator ready")
    return _orchestrator


__all__ = [
    'ADFIOrchestrator', 'EnergyDataPoint', 'DataSourceType', 'DataPriority',
    'DataQuality', 'StreamStatus', 'DataTransformation', 'UniversalDataConverter',
    'PredictiveCache', 'AdaptiveRateLimiter', 'CircuitBreaker', 'get_orchestrator'
]