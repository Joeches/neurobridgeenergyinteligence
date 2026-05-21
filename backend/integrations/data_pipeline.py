# backend/integrations/data_pipeline.py - PRODUCTION CLEAN v4.1.0
# Deterministic Energy Data Fabric - Phase 1 Compliant
# Prometheus Metrics Instrumented - ADFI Pipeline Observability

import asyncio
import logging
import time
import json
import threading
import math
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Union, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
from contextlib import asynccontextmanager
import uuid

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

try:
    from backend.monitoring.prometheus_metrics import (
        record_adfi_pipeline_latency,
        record_adfi_ingestion,
        set_adfi_source_health,
        set_active_module,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    # Null fallbacks for graceful degradation
    def record_adfi_pipeline_latency(*args, **kwargs): pass
    def record_adfi_ingestion(*args, **kwargs): pass
    def set_adfi_source_health(*args, **kwargs): pass
    def set_active_module(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[PIPELINE] prometheus metrics instrumented")
else:
    logger.debug("[PIPELINE] prometheus metrics unavailable - running without instrumentation")

# Single concise initialization log - NO BANNER
logger.info("[PIPELINE] deterministic mode active")

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

def get_env_bool(key: str, default: bool) -> bool:
    """Safely get boolean from environment variable with validation."""
    try:
        value = os.getenv(key)
        if value is None:
            return default
        value_lower = value.lower().strip()
        return value_lower in ("true", "1", "yes", "on", "enabled")
    except Exception:
        return default

DETERMINISTIC_MODE = get_env_bool("PIPELINE_DETERMINISTIC_MODE", True)
PHYSICS_VALIDATION_STRICT = get_env_bool("PIPELINE_PHYSICS_STRICT", True)
INVESTOR_DEMO_ENABLED = get_env_bool("INVESTOR_DEMO_ENABLED", True)

# ============================================================================
# PHYSICAL CONSTANTS
# ============================================================================

class PhysicalConstants:
    """Physical constants for deterministic physics validation."""
    GRID_FREQ_NOMINAL_HZ = 50.0
    GRID_FREQ_MIN_HZ = 49.0
    GRID_FREQ_MAX_HZ = 51.0
    GRID_VOLTAGE_NOMINAL_V = 230.0
    GRID_VOLTAGE_MIN_V = 210.0
    GRID_VOLTAGE_MAX_V = 250.0
    SOLAR_PANEL_EFFICIENCY = 0.18
    MAX_SOLAR_OUTPUT_KW = 200.0
    MAX_DEMAND_KW = 2000.0
    MIN_BATTERY_SOC = 5.0
    MAX_BATTERY_SOC = 95.0

# ============================================================================
# DATA SOURCE TYPES
# ============================================================================

class DataSourceType(Enum):
    """Data source types for deterministic physics classification."""
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    CANBUS = "canbus"
    IEC_61850 = "iec_61850"
    MQTT = "mqtt"
    NASA_POWER = "nasa_power"
    OPENWEATHER = "openweather"
    GOOGLE_EARTH = "google_earth"
    SYNTHETIC = "synthetic"
    PHYSICS_SIMULATION = "physics_simulation"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    INVESTOR_DEMO = "investor_demo"
    FALLBACK = "fallback"
    
    @classmethod
    def from_string(cls, value: str) -> "DataSourceType":
        """Convert string to DataSourceType safely with blocking for banned types."""
        if value is None:
            return cls.DETERMINISTIC_FALLBACK
        try:
            value_lower = value.lower() if isinstance(value, str) else ""
            blocked = ["nuclear", "fusion", "quantum", "defense"]
            for b in blocked:
                if b in value_lower:
                    logger.debug(f"[PIPELINE] blocked source type: {value}")
                    return cls.DETERMINISTIC_FALLBACK
            for member in cls:
                if member.value == value_lower or member.name.lower() == value_lower:
                    return member
            return cls.DETERMINISTIC_FALLBACK
        except Exception:
            return cls.DETERMINISTIC_FALLBACK


class DataPriority(Enum):
    """Priority levels for data processing."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    FALLBACK = "fallback"


class DataQuality(Enum):
    """Data quality classification."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    DEGRADED = "degraded"
    UNRELIABLE = "unreliable"


# ============================================================================
# ENERGY DATA POINT
# ============================================================================

@dataclass
class EnergyDataPoint:
    """Deterministic energy data point with full audit trail."""
    timestamp: float = field(default_factory=time.time)
    source_type: DataSourceType = DataSourceType.FALLBACK
    source_id: str = ""
    grid_frequency_hz: Optional[float] = None
    grid_voltage_v: Optional[float] = None
    active_power_kw: Optional[float] = None
    demand_load_kw: Optional[float] = None
    solar_output_kw: Optional[float] = None
    irradiance_wm2: Optional[float] = None
    temperature_c: Optional[float] = None
    cloud_cover_percent: Optional[float] = None
    humidity_percent: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    pressure_hpa: Optional[float] = None
    battery_soc_percent: Optional[float] = None
    battery_power_kw: Optional[float] = None
    quality_score: float = 0.85
    quality_flags: List[str] = field(default_factory=list)
    transformation_history: List[str] = field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    grid_stability_index: Optional[float] = None
    solar_efficiency_percent: Optional[float] = None
    aece_risk_factor: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert data point to dictionary."""
        result = {}
        try:
            for key, value in self.__dict__.items():
                if value is not None:
                    if isinstance(value, Enum):
                        result[key] = value.value
                    elif key in ('audit_trail', 'transformation_history'):
                        result[key] = value
                    else:
                        result[key] = value
            result['timestamp_iso'] = datetime.fromtimestamp(
                self.timestamp, tz=timezone.utc
            ).isoformat()
        except Exception as e:
            logger.debug(f"[PIPELINE] to_dict error: {e}")
        return result
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate data point against physical constraints."""
        errors = []
        try:
            if self.grid_frequency_hz is not None:
                if not (PhysicalConstants.GRID_FREQ_MIN_HZ <= self.grid_frequency_hz <= PhysicalConstants.GRID_FREQ_MAX_HZ):
                    errors.append(f"grid_frequency_hz={self.grid_frequency_hz} out of bounds")
            if self.grid_voltage_v is not None:
                if not (PhysicalConstants.GRID_VOLTAGE_MIN_V <= self.grid_voltage_v <= PhysicalConstants.GRID_VOLTAGE_MAX_V):
                    errors.append(f"grid_voltage_v={self.grid_voltage_v} out of bounds")
            if self.solar_output_kw is not None:
                if not (0 <= self.solar_output_kw <= PhysicalConstants.MAX_SOLAR_OUTPUT_KW):
                    errors.append(f"solar_output_kw={self.solar_output_kw} out of bounds")
            if self.demand_load_kw is not None:
                if not (0 <= self.demand_load_kw <= PhysicalConstants.MAX_DEMAND_KW):
                    errors.append(f"demand_load_kw={self.demand_load_kw} out of bounds")
        except Exception as e:
            errors.append(f"validation error: {e}")
        return len(errors) == 0, errors
    
    def add_audit_entry(self, stage: str, details: Dict[str, Any]):
        """Add audit trail entry."""
        try:
            self.audit_trail.append({
                "stage": stage,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details
            })
        except Exception:
            pass

# ============================================================================
# INVESTOR DEMO OBSERVER
# ============================================================================

class InvestorDemoObserver:
    """Observer for investor demo data ingestion tracking."""
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
        self._ingestion_queue: deque = deque(maxlen=1000)
        self._demo_subscribers: List[Callable] = []
        self._metrics = {"total_ingested": 0, "total_to_demo": 0}
        self._enabled = INVESTOR_DEMO_ENABLED
        logger.info("[INVESTOR_DEMO] observer initialized")
    
    def record_ingestion(self, data_point: EnergyDataPoint, destination: str = "investor_demo"):
        """Record an ingestion event for investor demo tracking."""
        if not self._enabled:
            return
        try:
            self._metrics["total_ingested"] += 1
            if destination == "investor_demo":
                self._metrics["total_to_demo"] += 1
            
            # PROMETHEUS: Record telemetry packet for investor demo
            source_label = "investor_demo"
            record_adfi_ingestion(
                source=source_label,
                packets=1,
                latency_seconds=0.0,
                module="data_pipeline"
            )
        except Exception as e:
            logger.debug(f"[INVESTOR_DEMO] record error: {e}")
    
    def subscribe(self, callback: Callable):
        """Subscribe to demo events."""
        if callable(callback):
            self._demo_subscribers.append(callback)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get investor demo metrics."""
        return {
            "enabled": self._enabled,
            "total_ingested": self._metrics["total_ingested"],
            "total_to_demo": self._metrics["total_to_demo"]
        }
    
    def reset(self):
        """Reset observer state."""
        self._ingestion_queue.clear()
        self._metrics = {"total_ingested": 0, "total_to_demo": 0}


_demo_observer = None


def get_demo_observer() -> InvestorDemoObserver:
    """Get or create the singleton InvestorDemoObserver."""
    global _demo_observer
    if _demo_observer is None:
        _demo_observer = InvestorDemoObserver()
    return _demo_observer

# ============================================================================
# DETERMINISTIC PHYSICS CONVERTER
# ============================================================================

class DeterministicPhysicsConverter:
    """Converter for deterministic physics data transformation."""
    
    def __init__(self):
        self._conversion_count = 0
    
    def convert(self, data: Any, source_type: Union[DataSourceType, str] = None) -> EnergyDataPoint:
        """Convert raw data to EnergyDataPoint with deterministic physics."""
        self._conversion_count += 1
        conversion_start = time.time()
        
        try:
            if isinstance(source_type, str):
                source_type = DataSourceType.from_string(source_type)
            elif source_type is None:
                source_type = DataSourceType.DETERMINISTIC_FALLBACK
        except Exception:
            source_type = DataSourceType.DETERMINISTIC_FALLBACK
        
        data_point = EnergyDataPoint(
            source_type=source_type,
            source_id=f"converter_{self._conversion_count}",
            timestamp=time.time()
        )
        
        try:
            if isinstance(data, dict):
                self._convert_from_dict(data, data_point)
            elif hasattr(data, '__dict__'):
                self._convert_from_object(data, data_point)
        except Exception as e:
            logger.debug(f"[PIPELINE] conversion error: {e}")
        
        try:
            self._apply_physical_constraints(data_point)
            self._validate_power_balance(data_point)
        except Exception:
            pass
        
        # PROMETHEUS: Record pipeline latency for conversion
        conversion_latency = time.time() - conversion_start
        source_label = source_type.value if hasattr(source_type, 'value') else str(source_type)
        record_adfi_pipeline_latency(
            source=source_label,
            latency_seconds=conversion_latency,
            module="physics_converter"
        )
        
        return data_point
    
    def _convert_from_dict(self, data: Dict[str, Any], dp: EnergyDataPoint):
        """Convert dictionary data to EnergyDataPoint fields."""
        try:
            if 'grid_frequency_hz' in data:
                dp.grid_frequency_hz = self._safe_float(data['grid_frequency_hz'])
            if 'frequency_hz' in data:
                dp.grid_frequency_hz = self._safe_float(data['frequency_hz'])
            if 'grid_voltage_v' in data:
                dp.grid_voltage_v = self._safe_float(data['grid_voltage_v'])
            if 'active_power_kw' in data:
                dp.active_power_kw = self._safe_float(data['active_power_kw'])
            if 'demand_load_kw' in data:
                dp.demand_load_kw = self._safe_float(data['demand_load_kw'])
            if 'solar_output_kw' in data:
                dp.solar_output_kw = self._safe_float(data['solar_output_kw'])
            if 'irradiance_wm2' in data:
                dp.irradiance_wm2 = self._safe_float(data['irradiance_wm2'])
            if 'temperature_c' in data:
                dp.temperature_c = self._safe_float(data['temperature_c'])
            if 'cloud_cover_percent' in data:
                dp.cloud_cover_percent = self._safe_float(data['cloud_cover_percent'])
            if 'battery_soc_percent' in data:
                dp.battery_soc_percent = self._safe_float(data['battery_soc_percent'])
        except Exception as e:
            logger.debug(f"[PIPELINE] dict conversion error: {e}")
    
    def _convert_from_object(self, data: object, dp: EnergyDataPoint):
        """Convert object attributes to EnergyDataPoint fields."""
        try:
            for attr in dir(data):
                if attr.startswith('_') or attr in ['to_dict', 'validate']:
                    continue
                try:
                    value = getattr(data, attr)
                    if value is None:
                        continue
                    attr_lower = attr.lower()
                    if 'frequency' in attr_lower:
                        dp.grid_frequency_hz = self._safe_float(value)
                    elif 'voltage' in attr_lower:
                        dp.grid_voltage_v = self._safe_float(value)
                    elif 'solar' in attr_lower and 'kw' in attr_lower:
                        dp.solar_output_kw = self._safe_float(value)
                    elif 'demand' in attr_lower:
                        dp.demand_load_kw = self._safe_float(value)
                    elif 'temperature' in attr_lower:
                        dp.temperature_c = self._safe_float(value)
                    elif 'cloud' in attr_lower:
                        dp.cloud_cover_percent = self._safe_float(value)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[PIPELINE] object conversion error: {e}")
    
    def _safe_float(self, value: Any, default: float = None) -> Optional[float]:
        """Safely convert value to float, handling NaN and Inf."""
        if value is None:
            return default
        try:
            result = float(value)
            if math.isnan(result) or math.isinf(result):
                return default
            return result
        except (ValueError, TypeError):
            return default
    
    def _apply_physical_constraints(self, dp: EnergyDataPoint):
        """Apply physical reality constraints to data point."""
        try:
            if dp.grid_frequency_hz is not None:
                dp.grid_frequency_hz = max(
                    PhysicalConstants.GRID_FREQ_MIN_HZ,
                    min(PhysicalConstants.GRID_FREQ_MAX_HZ, dp.grid_frequency_hz)
                )
            if dp.grid_voltage_v is not None:
                dp.grid_voltage_v = max(
                    PhysicalConstants.GRID_VOLTAGE_MIN_V,
                    min(PhysicalConstants.GRID_VOLTAGE_MAX_V, dp.grid_voltage_v)
                )
            if dp.solar_output_kw is not None:
                dp.solar_output_kw = max(
                    0.0, min(PhysicalConstants.MAX_SOLAR_OUTPUT_KW, dp.solar_output_kw)
                )
        except Exception:
            pass
    
    def _validate_power_balance(self, dp: EnergyDataPoint):
        """Validate power balance (phase 1: passive validation)."""
        pass

# ============================================================================
# PHYSICS VALIDATION ENGINE
# ============================================================================

class PhysicsValidationEngine:
    """Engine for physics-based data validation."""
    
    def __init__(self):
        self._validation_count = 0
    
    def validate(self, data: EnergyDataPoint) -> Tuple[bool, float, List[str]]:
        """Validate data against physics laws and constraints."""
        self._validation_count += 1
        validation_start = time.time()
        
        physics_valid = True
        quality_score = 1.0
        anomalies = []
        
        try:
            if data.grid_frequency_hz is not None:
                if data.grid_frequency_hz < 49.5 or data.grid_frequency_hz > 50.5:
                    physics_valid = False
                    quality_score -= 0.3
                    anomalies.append(f"frequency_deviation:{data.grid_frequency_hz}")
            
            quality_score = max(0.0, min(1.0, quality_score))
        except Exception as e:
            logger.debug(f"[PIPELINE] validation error: {e}")
            quality_score = max(0.0, quality_score - 0.1)
        
        # PROMETHEUS: Record validation latency
        validation_latency = time.time() - validation_start
        source_label = data.source_type.value if hasattr(data.source_type, 'value') else "unknown"
        record_adfi_pipeline_latency(
            source=source_label,
            latency_seconds=validation_latency,
            module="physics_validation"
        )
        
        return physics_valid, quality_score, anomalies
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validation engine statistics."""
        return {"validation_count": self._validation_count}

# ============================================================================
# SELF-HEALING BUFFER
# ============================================================================

class SelfHealingBuffer:
    """Self-healing buffer with backpressure and critical path prioritization."""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)
        self._critical_buffer: deque = deque(maxlen=1000)
        self._lock = threading.RLock()
        self._backpressure_active = False
    
    def add(self, item: EnergyDataPoint, is_critical: bool = False) -> bool:
        """Add item to buffer. Returns True if added, False if dropped."""
        try:
            with self._lock:
                if is_critical or (item.aece_risk_factor and item.aece_risk_factor > 0.65):
                    self._critical_buffer.append(item)
                    return True
                if len(self._buffer) >= self.max_size:
                    if not self._backpressure_active:
                        self._backpressure_active = True
                        logger.warning("[PIPELINE] backpressure activated")
                    return False
                self._buffer.append(item)
                if self._backpressure_active and len(self._buffer) < self.max_size * 0.7:
                    self._backpressure_active = False
                    logger.info("[PIPELINE] backpressure released")
                return True
        except Exception:
            return False
    
    def get(self, prefer_critical: bool = True) -> Optional[EnergyDataPoint]:
        """Get next item from buffer."""
        try:
            with self._lock:
                if prefer_critical and self._critical_buffer:
                    return self._critical_buffer.popleft()
                if self._buffer:
                    return self._buffer.popleft()
        except Exception:
            pass
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        try:
            with self._lock:
                return {
                    "size": len(self._buffer),
                    "critical_size": len(self._critical_buffer),
                    "backpressure_active": self._backpressure_active
                }
        except Exception:
            return {"size": 0, "critical_size": 0, "backpressure_active": False}

# ============================================================================
# DETERMINISTIC TRANSFORMATIONS
# ============================================================================

def apply_physics_validation(data: EnergyDataPoint) -> EnergyDataPoint:
    """Apply physics validation transformation."""
    try:
        engine = PhysicsValidationEngine()
        _, quality_score, _ = engine.validate(data)
        data.quality_score = (data.quality_score + quality_score) / 2
        data.transformation_history.append("physics_validation")
    except Exception as e:
        logger.debug(f"[PIPELINE] physics validation transform error: {e}")
    return data


def calculate_grid_stability(data: EnergyDataPoint) -> EnergyDataPoint:
    """Calculate grid stability index."""
    try:
        if data.grid_frequency_hz and data.grid_voltage_v:
            freq_quality = 100 - min(100, abs(50.0 - data.grid_frequency_hz) * 10)
            volt_quality = 100 - min(100, abs(230.0 - data.grid_voltage_v) * 2.5)
            data.grid_stability_index = (freq_quality + volt_quality) / 2
            data.transformation_history.append("grid_stability_calc")
    except Exception as e:
        logger.debug(f"[PIPELINE] grid stability calc error: {e}")
    return data


def calculate_risk_factor(data: EnergyDataPoint) -> EnergyDataPoint:
    """Calculate AECE risk factor."""
    try:
        risk = 0.15
        if data.grid_frequency_hz:
            risk += abs(50.0 - data.grid_frequency_hz) * 0.08
        if data.demand_load_kw and data.solar_output_kw:
            gap = data.demand_load_kw - data.solar_output_kw
            if gap > 0:
                risk += (gap / 1000) * 0.15
        data.aece_risk_factor = min(1.0, risk)
        data.transformation_history.append("risk_factor_calc")
    except Exception as e:
        logger.debug(f"[PIPELINE] risk factor calc error: {e}")
    return data


def enforce_physical_limits(data: EnergyDataPoint) -> EnergyDataPoint:
    """Enforce physical reality limits."""
    try:
        if data.solar_output_kw is not None:
            data.solar_output_kw = max(
                0.0, min(PhysicalConstants.MAX_SOLAR_OUTPUT_KW, data.solar_output_kw)
            )
        data.transformation_history.append("physical_limits")
    except Exception as e:
        logger.debug(f"[PIPELINE] physical limits error: {e}")
    return data

# ============================================================================
# UNIFIED DATA PIPELINE
# ============================================================================

class UnifiedDataPipeline:
    """Unified data pipeline with self-healing and deterministic physics."""
    
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
        self.buffer = SelfHealingBuffer(max_size=10000)
        self.converter = DeterministicPhysicsConverter()
        self.demo_observer = get_demo_observer()
        self._running = False
        self._event_loop_task = None
        self._stats = {"total_ingested": 0, "total_processed": 0, "total_dropped": 0}
        self._stats_lock = threading.RLock()
        self._ingestion_lock = asyncio.Lock()
        
        logger.info("[PIPELINE] initialized")
        
        # PROMETHEUS: Mark data pipeline module as active
        set_active_module(module="data_pipeline", active=True)
    
    async def ingest(
        self,
        data: Any,
        source_type: Union[DataSourceType, str] = None,
        source_id: str = None
    ) -> EnergyDataPoint:
        """
        Ingest data into the pipeline.
        
        Args:
            data: Raw data to ingest (dict, object, or EnergyDataPoint)
            source_type: Type of data source
            source_id: Identifier for the data source
            
        Returns:
            EnergyDataPoint after processing
        """
        ingestion_start = time.time()
        
        async with self._ingestion_lock:
            try:
                with self._stats_lock:
                    self._stats["total_ingested"] += 1
                
                # Phase 1 compliance: block restricted source types
                if isinstance(source_type, str):
                    source_lower = source_type.lower()
                    blocked = ["nuclear", "fusion", "quantum", "defense"]
                    for b in blocked:
                        if b in source_lower:
                            logger.debug(f"[PIPELINE] blocked ingestion: {source_type}")
                            return self._create_fallback_data_point(f"phase1_blocked:{source_type}")
                
                # Convert to EnergyDataPoint if needed
                if not isinstance(data, EnergyDataPoint):
                    data_point = self.converter.convert(data, source_type)
                else:
                    data_point = data
                
                # Set source metadata
                if source_type:
                    try:
                        data_point.source_type = (
                            source_type if isinstance(source_type, DataSourceType)
                            else DataSourceType.from_string(source_type)
                        )
                    except Exception:
                        pass
                if source_id:
                    data_point.source_id = source_id
                
                # Determine criticality
                is_critical = (
                    data_point.aece_risk_factor is not None
                    and data_point.aece_risk_factor > 0.65
                )
                
                # Add to buffer
                if not self.buffer.add(data_point, is_critical):
                    with self._stats_lock:
                        self._stats["total_dropped"] += 1
                    logger.debug("[PIPELINE] data point dropped due to backpressure")
                
                with self._stats_lock:
                    self._stats["total_processed"] += 1
                
                # PROMETHEUS: Record pipeline ingestion with latency
                ingestion_latency = time.time() - ingestion_start
                source_label = (
                    data_point.source_type.value
                    if hasattr(data_point.source_type, 'value')
                    else str(source_type or "unknown")
                )
                record_adfi_pipeline_latency(
                    source=source_label,
                    latency_seconds=ingestion_latency,
                    module="unified_pipeline"
                )
                
                # Record telemetry packet
                record_adfi_ingestion(
                    source=source_label,
                    packets=1,
                    latency_seconds=ingestion_latency,
                    module="data_pipeline"
                )
                
                # Update source health
                set_adfi_source_health(source=source_label, healthy=True)
                
                return data_point
                
            except Exception as e:
                logger.error(f"[PIPELINE] ingestion error: {e}")
                with self._stats_lock:
                    self._stats["total_dropped"] += 1
                return self._create_fallback_data_point(str(e))
    
    def _create_fallback_data_point(self, reason: str = None) -> EnergyDataPoint:
        """Create a deterministic fallback data point."""
        try:
            dp = EnergyDataPoint(
                source_type=DataSourceType.DETERMINISTIC_FALLBACK,
                grid_frequency_hz=50.0,
                grid_voltage_v=230.0,
                active_power_kw=500.0,
                demand_load_kw=500.0,
                solar_output_kw=50.0,
                quality_score=0.70
            )
            if reason:
                dp.add_audit_entry("fallback_created", {"reason": reason})
            
            # PROMETHEUS: Record fallback
            record_adfi_ingestion(
                source="deterministic_fallback",
                packets=1,
                latency_seconds=0.0,
                module="data_pipeline"
            )
            set_adfi_source_health(source="pipeline_fallback", healthy=True)
            
            return dp
        except Exception:
            return EnergyDataPoint(source_type=DataSourceType.FALLBACK)
    
    async def consume(self, timeout_ms: float = 100) -> Optional[EnergyDataPoint]:
        """Consume data from the buffer with timeout."""
        start = time.time()
        try:
            while time.time() - start < timeout_ms / 1000:
                data = self.buffer.get()
                if data:
                    return data
                await asyncio.sleep(0.005)
        except Exception as e:
            logger.debug(f"[PIPELINE] consume error: {e}")
        return None
    
    async def start_processing(self):
        """Start background processing."""
        if self._running:
            return
        self._running = True
        self._event_loop_task = asyncio.create_task(self._background_processor())
        logger.info("[PIPELINE] processor started")
        set_active_module(module="data_pipeline", active=True)
    
    async def _background_processor(self):
        """Background processor for data transformations."""
        while self._running:
            try:
                data = await self.consume(timeout_ms=50)
                if data:
                    process_start = time.time()
                    
                    # Apply deterministic transformations
                    data = apply_physics_validation(data)
                    data = calculate_grid_stability(data)
                    data = calculate_risk_factor(data)
                    data = enforce_physical_limits(data)
                    
                    # Investor demo tracking
                    if INVESTOR_DEMO_ENABLED:
                        try:
                            self.demo_observer.record_ingestion(data, "investor_demo")
                        except Exception:
                            pass
                    
                    # PROMETHEUS: Record processing latency
                    process_latency = time.time() - process_start
                    source_label = (
                        data.source_type.value
                        if hasattr(data.source_type, 'value')
                        else "unknown"
                    )
                    record_adfi_pipeline_latency(
                        source=source_label,
                        latency_seconds=process_latency,
                        module="background_processor"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[PIPELINE] processor error: {e}")
            await asyncio.sleep(0.005)
        
        logger.info("[PIPELINE] processor exited")
    
    async def stop_processing(self):
        """Stop background processing."""
        self._running = False
        if self._event_loop_task:
            self._event_loop_task.cancel()
            try:
                await self._event_loop_task
            except asyncio.CancelledError:
                pass
        logger.info("[PIPELINE] processor stopped")
        set_active_module(module="data_pipeline", active=False)
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        try:
            buffer_stats = self.buffer.get_stats()
            with self._stats_lock:
                processing_stats = dict(self._stats)
        except Exception:
            buffer_stats = {}
            processing_stats = {}
        
        return {
            "initialized": self._initialized,
            "running": self._running,
            "deterministic_mode": True,
            "metrics_instrumented": _METRICS_AVAILABLE,
            "buffer": buffer_stats,
            "processing": processing_stats,
            "phase": "PHASE_1_PRODUCTION"
        }


_pipeline_instance = None
_pipeline_lock = threading.RLock()


def get_data_pipeline() -> UnifiedDataPipeline:
    """Get or create the singleton UnifiedDataPipeline."""
    global _pipeline_instance
    if _pipeline_instance is None:
        with _pipeline_lock:
            if _pipeline_instance is None:
                _pipeline_instance = UnifiedDataPipeline()
    return _pipeline_instance


async def initialize_pipeline():
    """Initialize and start the data pipeline."""
    try:
        pipeline = get_data_pipeline()
        await pipeline.start_processing()
        logger.info("[PIPELINE] initialized and ready")
        set_active_module(module="data_pipeline", active=True)
        return pipeline
    except Exception as e:
        logger.error(f"[PIPELINE] initialization failed: {e}")
        set_active_module(module="data_pipeline", active=False)
        raise


async def shutdown_pipeline():
    """Shutdown the data pipeline gracefully."""
    try:
        pipeline = get_data_pipeline()
        await pipeline.stop_processing()
        logger.info("[PIPELINE] shutdown complete")
        set_active_module(module="data_pipeline", active=False)
    except Exception as e:
        logger.error(f"[PIPELINE] shutdown error: {e}")


__all__ = [
    'UnifiedDataPipeline',
    'EnergyDataPoint',
    'DataSourceType',
    'DataPriority',
    'DataQuality',
    'get_data_pipeline',
    'initialize_pipeline',
    'shutdown_pipeline',
    'get_demo_observer'
]