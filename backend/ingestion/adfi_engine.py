# backend/ingestion/adfi_engine.py - PRODUCTION CLEAN v4.1.0
# Deterministic Physics Data Fabric - Phase 1 Compliant
# Prometheus Metrics Instrumented - ADFI Observability

import asyncio
import logging
import time
import threading
import uuid
import inspect
import math
import os
import random
from typing import Dict, Any, Optional, List, Callable, Union, Awaitable, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque, defaultdict
from functools import wraps

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

try:
    from backend.monitoring.prometheus_metrics import (
        record_adfi_ingestion,
        record_adfi_cycle,
        set_adfi_source_health,
        record_adfi_pipeline_latency,
        set_active_module,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    # Null fallbacks
    def record_adfi_ingestion(*args, **kwargs): pass
    def record_adfi_cycle(*args, **kwargs): pass
    def set_adfi_source_health(*args, **kwargs): pass
    def record_adfi_pipeline_latency(*args, **kwargs): pass
    def set_active_module(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[ADFI] prometheus metrics instrumented")
else:
    logger.debug("[ADFI] prometheus metrics unavailable - running without instrumentation")

# ============================================================================
# ENVIRONMENT VARIABLES FOR PHYSICS MODE
# ============================================================================

def get_env_bool(key: str, default: bool) -> bool:
    """Safely get boolean from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    value_lower = value.lower().strip()
    return value_lower in ("true", "1", "yes", "on", "enabled")


def get_env_int(key: str, default: int, min_val: int = None, max_val: int = None) -> int:
    """Safely get int from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        parsed = int(value)
        if min_val is not None and parsed < min_val:
            return min_val
        if max_val is not None and parsed > max_val:
            return max_val
        return parsed
    except (ValueError, TypeError):
        return default


def get_env_float(key: str, default: float, min_val: float = None, max_val: float = None) -> float:
    """Safely get float from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        parsed = float(value)
        if min_val is not None and parsed < min_val:
            return min_val
        if max_val is not None and parsed > max_val:
            return max_val
        return parsed
    except (ValueError, TypeError):
        return default


def show_banners() -> bool:
    """Determine if banners should be shown (development only)."""
    env = os.getenv("ENVIRONMENT", "production").lower()
    is_dev = env in ["development", "dev", "local"]
    return is_dev and os.getenv("LOG_BANNERS", "false").lower() == "true"


# Physics mode configuration
PHYSICS_MODE_ENABLED = get_env_bool("ADFI_PHYSICS_MODE", True)
HF_DISABLED = get_env_bool("ADFI_DISABLE_HF", True)
DETERMINISTIC_SEED = get_env_int("ADFI_DETERMINISTIC_SEED", 11011, 0, 999999)
DEFAULT_SCENARIO = os.getenv("ADFI_DEFAULT_SCENARIO", "normal")

# Initialize deterministic random seed
random.seed(DETERMINISTIC_SEED)

# Single concise log line - no banner
logger.info(f"[ADFI] deterministic mode active seed={DETERMINISTIC_SEED}")

# ============================================================================
# DATA SOURCE ENUM - Deterministic Physics Classification
# ============================================================================

class DataSource(Enum):
    """Data source types - Deterministic Physics classification."""
    HARDWARE = "hardware"
    API_LIVE = "api_live"
    SYNTHETIC = "synthetic"
    PHYSICS_SIMULATION = "physics_simulation"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    FALLBACK = "fallback"
    MODBUS = "modbus"
    NASA = "nasa"
    OPENWEATHER = "openweather"
    GEE = "gee"
    SUNGROW = "sungrow"
    CACHED = "cached"
    HISTORICAL = "historical"
    ML_PREDICTED = "physics_simulation"  # Legacy alias

    @classmethod
    def from_string(cls, value: str) -> "DataSource":
        """Convert string to DataSource enum safely."""
        if isinstance(value, cls):
            return value
        
        value_lower = value.lower() if isinstance(value, str) else ""
        
        if "ml" in value_lower or "predicted" in value_lower:
            logger.debug(f"[ADFI] legacy ML type mapped to physics_simulation")
            return cls.PHYSICS_SIMULATION
        
        for member in cls:
            if member.value == value_lower or member.name.lower() == value_lower:
                return member
        return cls.DETERMINISTIC_FALLBACK
    
    @classmethod
    def to_enum(cls, source_type: Any) -> "DataSource":
        """Convert any source_type input to DataSource enum."""
        if isinstance(source_type, cls):
            return source_type
        if isinstance(source_type, str):
            return cls.from_string(source_type)
        if hasattr(source_type, 'value'):
            return cls.from_string(str(source_type.value))
        if hasattr(source_type, '__str__'):
            return cls.from_string(str(source_type))
        return cls.DETERMINISTIC_FALLBACK
    
    @classmethod
    def normalize_source_type(cls, source_type: Any) -> str:
        """Normalize any source_type input to valid string."""
        if source_type is None:
            return "deterministic_fallback"
        
        if isinstance(source_type, cls):
            return source_type.value
        
        if isinstance(source_type, str):
            source_str = source_type.lower()
            
            if "ml" in source_str or "predicted" in source_str:
                return "physics_simulation"
            
            mapping = {
                "hardware": "hardware", "modbus": "modbus",
                "api_live": "api_live", "api": "api_live", "live": "api_live",
                "synthetic": "synthetic", "synth": "synthetic", "simulated": "synthetic",
                "physics": "physics_simulation", "physics_simulation": "physics_simulation",
                "deterministic": "deterministic_fallback", "fallback": "fallback",
                "nasa": "nasa", "weather": "openweather", "openweather": "openweather",
                "gee": "gee", "sungrow": "sungrow", "isolarcloud": "sungrow",
                "cached": "cached", "historical": "historical"
            }
            
            result = mapping.get(source_str, source_str)
            
            allowed = ["hardware", "modbus", "api_live", "synthetic", "physics_simulation",
                       "deterministic_fallback", "fallback", "nasa", "openweather", 
                       "gee", "sungrow", "cached", "historical"]
            
            return result if result in allowed else "deterministic_fallback"
        
        if hasattr(source_type, 'value'):
            return cls.normalize_source_type(source_type.value)
        
        if hasattr(source_type, '__str__'):
            return cls.normalize_source_type(str(source_type))
        
        return "deterministic_fallback"


class DataPriority(Enum):
    """Priority levels for data sources."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    FALLBACK = "fallback"


# ============================================================================
# DETERMINISTIC PHYSICS ENGINE
# ============================================================================

class DeterministicPhysicsEngine:
    """Deterministic physics-based telemetry generator."""
    
    def __init__(self, seed: int = DETERMINISTIC_SEED):
        self.seed = seed
        self._history = deque(maxlen=1000)
        self._scenario = DEFAULT_SCENARIO
        self._base_time = datetime.now(timezone.utc)
        self._generation_count = 0
        
        random.seed(seed)
        logger.debug(f"[PhysicsGen] initialized seed={seed}")
    
    def set_scenario(self, scenario: str):
        """Set active scenario for telemetry generation."""
        valid_scenarios = ["normal", "sunny_day", "cloudy_day", "rainy_day", 
                          "grid_stress", "fault_injection", "peak_demand", 
                          "night_time", "solar_surplus"]
        if scenario in valid_scenarios:
            self._scenario = scenario
        else:
            self._scenario = "normal"
    
    def _get_solar_factor(self, hour: float) -> float:
        """Get solar generation factor based on time of day."""
        if "night_time" in self._scenario:
            return 0.0
        
        if "cloudy_day" in self._scenario:
            factor = max(0.0, math.sin(math.pi * (hour - 6) / 12))
            return factor * 0.4
        
        if "rainy_day" in self._scenario:
            factor = max(0.0, math.sin(math.pi * (hour - 6) / 12))
            return factor * 0.15
        
        if 6 <= hour <= 18:
            factor = math.sin(math.pi * (hour - 6) / 12)
            if "solar_surplus" in self._scenario:
                factor = min(1.0, factor * 1.3)
            return factor
        return 0.0
    
    def _get_demand_factor(self, hour: float, weekday: int) -> float:
        """Get demand load factor based on time and day."""
        if "peak_demand" in self._scenario:
            if 7 <= hour <= 9 or 17 <= hour <= 20:
                return 1.6
            return 0.8
        
        if "grid_stress" in self._scenario:
            return 1.5
        
        if 7 <= hour <= 9:
            return 1.3
        elif 17 <= hour <= 20:
            return 1.4
        elif 23 <= hour or hour <= 5:
            return 0.4
        return 0.8
    
    def _get_weather_factor(self, hour: float) -> Dict[str, float]:
        """Get weather impact factors."""
        if "cloudy_day" in self._scenario:
            return {"cloud_cover": 70 + (math.sin(hour * math.pi / 12) * 20), "temp_offset": -3, "wind_factor": 1.5}
        elif "rainy_day" in self._scenario:
            return {"cloud_cover": 95, "temp_offset": -5, "wind_factor": 2.0}
        return {"cloud_cover": 10 + (math.sin(hour * math.pi / 12) * 20), "temp_offset": 0, "wind_factor": 1.0}
    
    def _get_fault_modifiers(self) -> Dict[str, float]:
        """Get fault injection modifiers."""
        if "fault_injection" in self._scenario:
            cycle = (self._generation_count // 10) % 4
            if cycle == 0:
                return {"freq_offset": -0.5, "voltage_offset": -15, "solar_offset": -0.5}
            elif cycle == 1:
                return {"freq_offset": 0.3, "voltage_offset": 10, "solar_offset": 0}
            elif cycle == 2:
                return {"freq_offset": -0.2, "voltage_offset": -5, "solar_offset": -0.3}
        return {"freq_offset": 0, "voltage_offset": 0, "solar_offset": 0}
    
    def generate_telemetry(self, scenario: str = None) -> Dict[str, Any]:
        """Generate deterministic physics-based telemetry."""
        if scenario:
            self.set_scenario(scenario)
        
        generation_start = time.time()
        
        now = datetime.now(timezone.utc)
        hour = now.hour + now.minute / 60
        weekday = now.weekday()
        
        self._generation_count += 1
        
        solar_factor = self._get_solar_factor(hour)
        demand_factor = self._get_demand_factor(hour, weekday)
        weather = self._get_weather_factor(hour)
        fault = self._get_fault_modifiers()
        
        base_solar_kw = 125.0
        solar_output_kw = base_solar_kw * solar_factor
        if "grid_stress" in self._scenario:
            solar_output_kw *= 0.8
        
        base_demand_kw = 500.0
        demand_load_kw = base_demand_kw * demand_factor
        
        supply_demand_balance = solar_output_kw - demand_load_kw + 400
        freq_deviation = - (supply_demand_balance / 1000) * 0.15
        frequency_hz = 50.0 + freq_deviation + fault["freq_offset"]
        frequency_hz = max(49.0, min(51.0, frequency_hz))
        
        voltage_v = 230.0 + (frequency_hz - 50.0) * 10 + fault["voltage_offset"]
        voltage_v = max(210.0, min(250.0, voltage_v))
        
        temperature_c = 25.0 + (solar_factor * 12) + weather["temp_offset"] + (math.sin(hour * math.pi / 12) * 3)
        temperature_c = max(15.0, min(45.0, temperature_c))
        
        irradiance_wm2 = 850.0 * solar_factor
        
        net_power = solar_output_kw - demand_load_kw
        base_soc = 50.0
        if net_power > 0:
            soc_change = min(30, net_power / 20)
        else:
            soc_change = max(-30, net_power / 10)
        
        cycle_mod = (self._generation_count % 60) / 60.0
        battery_soc = base_soc + soc_change + (cycle_mod * 10)
        battery_soc = max(5.0, min(95.0, battery_soc))
        
        risk_factors = [
            abs(50.0 - frequency_hz) / 2.0,
            max(0, (demand_load_kw - 800) / 400) if demand_load_kw > 800 else 0,
            (1.0 - solar_factor) * 0.3 if solar_factor < 0.5 else 0,
        ]
        aece_risk_factor = min(1.0, sum(risk_factors))
        
        quality_score = 0.75 if "fault_injection" in self._scenario else (0.85 if "grid_stress" in self._scenario else 0.95)
        
        source_type = "physics_simulation"
        if "fault_injection" in self._scenario:
            source_type = "physics_simulation_fault"
        elif "grid_stress" in self._scenario:
            source_type = "physics_simulation_stress"
        
        telemetry = {
            "timestamp": now.isoformat(),
            "source": "deterministic_physics",
            "source_type": source_type,
            "quality_score": round(quality_score, 3),
            "grid_frequency_hz": round(frequency_hz, 3),
            "grid_voltage_v": round(voltage_v, 1),
            "active_power_kw": round(demand_load_kw, 1),
            "demand_load_kw": round(demand_load_kw, 1),
            "solar_output_kw": round(solar_output_kw, 1),
            "irradiance_wm2": round(irradiance_wm2, 1),
            "temperature_c": round(temperature_c, 1),
            "cloud_cover_percent": round(weather["cloud_cover"], 1),
            "battery_soc_percent": round(battery_soc, 1),
            "aece_risk_factor": round(aece_risk_factor, 3),
            "data_quality": round(quality_score, 3),
            "scenario": self._scenario,
            "generation_count": self._generation_count,
            "phase": "PHASE_1_PRODUCTION",
            "deterministic_seed": self.seed,
            "hf_dependency": False,
            "physics_mode": True
        }
        
        generation_latency = time.time() - generation_start
        
        # =====================================================================
        # PROMETHEUS: Record ADFI cycle and ingestion metrics
        # =====================================================================
        record_adfi_cycle(source="deterministic_physics", module="physics_engine")
        record_adfi_ingestion(
            source="deterministic_physics",
            packets=1,
            latency_seconds=generation_latency,
            module="physics_engine"
        )
        
        self._history.append(telemetry)
        return telemetry
    
    def generate_batch(self, count: int, scenario: str = None) -> List[Dict[str, Any]]:
        """Generate batch of telemetry data."""
        results = []
        for _ in range(count):
            results.append(self.generate_telemetry(scenario))
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            "generation_count": self._generation_count,
            "current_scenario": self._scenario,
            "history_size": len(self._history),
            "deterministic_seed": self.seed,
            "physics_mode": True,
            "hf_dependency": False
        }


# ============================================================================
# DATA QUALITY ENGINE
# ============================================================================

class DataQualityEngine:
    """Data quality scoring engine."""
    
    SOURCE_RELIABILITY = {
        "hardware": 1.0, "modbus": 0.98, "api_live": 0.95, "nasa": 0.93,
        "openweather": 0.90, "gee": 0.88, "sungrow": 0.92, "cached": 0.85,
        "synthetic": 0.80, "physics_simulation": 0.88, "physics_simulation_fault": 0.75,
        "deterministic_fallback": 0.82, "fallback": 0.70, "historical": 0.78
    }
    
    REQUIRED_FIELDS = [
        "grid_frequency_hz", "grid_voltage_v", "active_power_kw",
        "demand_load_kw", "solar_output_kw", "battery_soc_percent", "aece_risk_factor"
    ]
    
    @classmethod
    def score_telemetry(cls, data: Dict[str, Any], source_type: str = None) -> float:
        """Calculate quality score for telemetry data."""
        base_score = 0.85
        src = source_type or data.get("source_type", "fallback")
        reliability = cls.SOURCE_RELIABILITY.get(src, 0.70)
        
        present_fields = sum(1 for field in cls.REQUIRED_FIELDS if field in data)
        completeness = present_fields / len(cls.REQUIRED_FIELDS)
        
        valid_ranges = 0
        total_checks = 0
        
        if "grid_frequency_hz" in data:
            total_checks += 1
            if 49.0 <= data["grid_frequency_hz"] <= 51.0:
                valid_ranges += 1
        
        if "grid_voltage_v" in data:
            total_checks += 1
            if 210 <= data["grid_voltage_v"] <= 250:
                valid_ranges += 1
        
        if "solar_output_kw" in data:
            total_checks += 1
            if 0 <= data["solar_output_kw"] <= 200:
                valid_ranges += 1
        
        if "battery_soc_percent" in data:
            total_checks += 1
            if 0 <= data["battery_soc_percent"] <= 100:
                valid_ranges += 1
        
        range_score = valid_ranges / max(1, total_checks)
        fallback_penalty = 0.95 if "fallback" not in src else 0.80
        
        quality = base_score * reliability * completeness * range_score * fallback_penalty
        return min(1.0, max(0.0, quality))


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""
    
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure_time = 0
        self._state = "closed"
        self._lock = threading.RLock()
    
    def record_success(self):
        with self._lock:
            self._failures = 0
            if self._state == "half_open":
                self._state = "closed"
    
    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self.failure_threshold and self._state == "closed":
                self._state = "open"
    
    def is_allowed(self) -> bool:
        with self._lock:
            if self._state == "closed":
                return True
            elif self._state == "open":
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = "half_open"
                    return True
                return False
            return True
    
    def get_state(self) -> str:
        return self._state
    
    def reset(self):
        with self._lock:
            self._failures = 0
            self._state = "closed"


# ============================================================================
# HARDWARE FETCHER
# ============================================================================

class HardwareFetcher:
    """Hardware data fetcher with circuit breaker."""
    
    def __init__(self, modbus_bridge):
        self.modbus_bridge = modbus_bridge
        self._circuit_breaker = CircuitBreaker("HardwareFetcher", failure_threshold=3, recovery_timeout=30.0)
        self._last_successful_data = None
        self._last_success_time = 0
        self._fetch_count = 0
        self._success_count = 0
        self._error_count = 0
        self._lock = asyncio.Lock()
        self._max_retries = 2
        self._retry_delay = 0.5
    
    async def fetch(self) -> Optional[Dict[str, Any]]:
        """Fetch telemetry data from hardware."""
        async with self._lock:
            self._fetch_count += 1
            fetch_start = time.time()
            
            if not self._circuit_breaker.is_allowed():
                if self._last_successful_data and (time.time() - self._last_success_time) < 60:
                    # PROMETHEUS: Source health degraded (circuit breaker open)
                    set_adfi_source_health(source="hardware_modbus", healthy=False)
                    return self._last_successful_data
                return None
            
            if not self.modbus_bridge:
                set_adfi_source_health(source="hardware_modbus", healthy=False)
                return None
            
            for attempt in range(self._max_retries + 1):
                try:
                    result = await self._fetch_with_timeout()
                    if result:
                        fetch_latency = time.time() - fetch_start
                        self._success_count += 1
                        self._circuit_breaker.record_success()
                        self._last_successful_data = result
                        self._last_success_time = time.time()
                        
                        # =========================================================
                        # PROMETHEUS: Record hardware ingestion with latency
                        # =========================================================
                        record_adfi_ingestion(
                            source="hardware_modbus",
                            packets=1,
                            latency_seconds=fetch_latency,
                            module="hardware_fetcher"
                        )
                        set_adfi_source_health(source="hardware_modbus", healthy=True)
                        
                        return result
                    
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_delay * (attempt + 1))
                        
                except Exception:
                    pass
            
            self._error_count += 1
            self._circuit_breaker.record_failure()
            
            # PROMETHEUS: Mark source unhealthy after failures
            set_adfi_source_health(source="hardware_modbus", healthy=False)
            
            if self._last_successful_data and (time.time() - self._last_success_time) < 60:
                return self._last_successful_data
            
            return None
    
    async def _fetch_with_timeout(self) -> Optional[Dict[str, Any]]:
        """Fetch with timeout protection."""
        try:
            if hasattr(self.modbus_bridge, 'poll_telemetry'):
                telemetry = await asyncio.wait_for(
                    self.modbus_bridge.poll_telemetry(force_refresh=False),
                    timeout=3.0
                )
            elif hasattr(self.modbus_bridge, 'get_telemetry'):
                telemetry = await asyncio.wait_for(
                    self.modbus_bridge.get_telemetry(),
                    timeout=3.0
                )
            else:
                return None
            
            if telemetry:
                return {
                    "grid_frequency_hz": getattr(telemetry, 'grid_frequency_hz', 50.0),
                    "active_power_kw": getattr(telemetry, 'active_power_kw', 1150.0),
                    "solar_output_kw": getattr(telemetry, 'solar_output_kw', 125.0),
                    "battery_soc_percent": getattr(telemetry, 'battery_soc_percent', 50.0),
                    "temperature_c": getattr(telemetry, 'temperature_c', 28.0),
                    "grid_voltage_v": getattr(telemetry, 'grid_voltage_v', 230.0),
                    "demand_load_kw": getattr(telemetry, 'demand_load_kw', 1124.0),
                    "aece_risk_factor": getattr(telemetry, 'aece_risk_factor', 0.15),
                    "source": "modbus_hardware",
                    "source_type": "hardware"
                }
            return None
        except Exception:
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        success_rate = (self._success_count / max(1, self._fetch_count)) * 100
        return {
            "fetch_count": self._fetch_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "success_rate": round(success_rate, 2),
            "circuit_breaker_state": self._circuit_breaker.get_state(),
            "cached_data_available": self._last_successful_data is not None
        }


# ============================================================================
# API FETCHER
# ============================================================================

class APIFetcher:
    """API data fetcher with physics fallback."""
    
    def __init__(self, nasa_client=None, weather_client=None, gee_client=None, sungrow_client=None):
        self.clients = {"nasa": nasa_client, "weather": weather_client, "gee": gee_client, "sungrow": sungrow_client}
        self._circuit_breakers = {name: CircuitBreaker(f"APIFetcher:{name}", failure_threshold=3, recovery_timeout=30.0) for name in self.clients.keys()}
        self._physics_engine = DeterministicPhysicsEngine()
        self._cache = {}
        self._cache_ttl = 10
        self._fetch_timeout = 3.0
        self._fetch_count = 0
        self._success_count = 0
        self._lock = asyncio.Lock()
        
        available = [name for name, client in self.clients.items() if client is not None]
        logger.debug(f"[APIFetcher] initialized clients={available if available else 'none'}")
    
    async def fetch(self) -> Optional[Dict[str, Any]]:
        """Fetch aggregated data from APIs with physics fallback."""
        async with self._lock:
            self._fetch_count += 1
            now = time.time()
            fetch_start = now
            
            cache_key = "api_telemetry"
            if cache_key in self._cache:
                cached_time, cached_data = self._cache[cache_key]
                if now - cached_time < self._cache_ttl:
                    return cached_data
            
            tasks = []
            for name, client in self.clients.items():
                if client and self._circuit_breakers[name].is_allowed():
                    tasks.append(self._fetch_source(name, client))
            
            aggregated = {}
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        aggregated.update(result)
            
            if not aggregated:
                aggregated = self._physics_engine.generate_telemetry()
                aggregated["source"] = "api_physics_fallback"
                aggregated["source_type"] = "deterministic_fallback"
                self._success_count += 1
                
                # PROMETHEUS: Record fallback ingestion
                record_adfi_ingestion(
                    source="api_physics_fallback",
                    packets=1,
                    latency_seconds=time.time() - fetch_start,
                    module="api_fetcher"
                )
                set_adfi_source_health(source="api_fallback", healthy=True)
            
            defaults = {
                "irradiance_wm2": 850, "temperature_c": 28, "cloud_cover_percent": 25,
                "humidity_percent": 55, "wind_speed_ms": 3.2, "pressure_hpa": 1013,
                "vegetation_index": 0.45, "inverter_power_kw": 12.5, "inverter_efficiency_percent": 94
            }
            for key, default in defaults.items():
                aggregated.setdefault(key, default)
            
            aggregated["source"] = aggregated.get("source", "api_aggregated")
            fetch_latency = time.time() - fetch_start
            aggregated["fetch_time_ms"] = round(fetch_latency * 1000, 2)
            aggregated["quality_score"] = DataQualityEngine.score_telemetry(aggregated)
            
            # PROMETHEUS: Record pipeline latency for API fetch
            source_label = aggregated.get("source", "api_aggregated")
            record_adfi_pipeline_latency(
                source=source_label,
                latency_seconds=fetch_latency,
                module="api_fetcher"
            )
            
            self._cache[cache_key] = (now, aggregated)
            return aggregated
    
    async def _fetch_source(self, name: str, client) -> Optional[Dict[str, Any]]:
        """Fetch from a single API source."""
        try:
            result = await asyncio.wait_for(self._call_client_method(client), timeout=self._fetch_timeout)
            if result:
                self._circuit_breakers[name].record_success()
                set_adfi_source_health(source=f"api_{name}", healthy=True)
                return result
        except Exception:
            pass
        
        self._circuit_breakers[name].record_failure()
        set_adfi_source_health(source=f"api_{name}", healthy=False)
        return None
    
    async def _call_client_method(self, client) -> Optional[Dict[str, Any]]:
        """Call the appropriate method on the client."""
        method_names = ['get_telemetry', 'get_current_weather', 'get_vegetation_data', 'get_inverter_status']
        
        for method_name in method_names:
            if hasattr(client, method_name) and callable(getattr(client, method_name)):
                result = getattr(client, method_name)()
                if inspect.iscoroutine(result):
                    result = await result
                if result:
                    if hasattr(result, 'to_dict'):
                        result = result.to_dict()
                    if isinstance(result, dict):
                        return result
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        success_rate = (self._success_count / max(1, self._fetch_count)) * 100
        return {
            "fetch_count": self._fetch_count,
            "success_count": self._success_count,
            "success_rate": round(success_rate, 2),
            "circuit_breakers": {name: cb.get_state() for name, cb in self._circuit_breakers.items()}
        }


# ============================================================================
# DATA SOURCE CONFIGURATION
# ============================================================================

@dataclass
class DataSourceConfig:
    """Configuration for registered data sources."""
    id: str
    name: str
    source_type: str
    source_type_enum: Optional[DataSource] = None
    fetcher: Callable[[], Awaitable[Optional[Dict[str, Any]]]] = None
    priority: str = "normal"
    timeout: float = 5.0
    retry_count: int = 3
    cache_ttl: float = 10.0
    enabled: bool = True
    last_success: float = 0.0
    last_error: Optional[str] = None
    error_count: int = 0
    success_count: int = 0
    
    def __post_init__(self):
        if self.source_type_enum is None:
            self.source_type_enum = DataSource.to_enum(self.source_type)
        if hasattr(self.source_type, 'value'):
            self.source_type_enum = self.source_type
            self.source_type = self.source_type.value
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "source_type": self.source_type,
            "priority": self.priority, "timeout": self.timeout, "retry_count": self.retry_count,
            "cache_ttl": self.cache_ttl, "enabled": self.enabled,
            "success_count": self.success_count, "error_count": self.error_count,
            "last_error": self.last_error
        }


# ============================================================================
# LOCAL ADFI ENGINE
# ============================================================================

class LocalADFIEngine:
    """Local ADFI Engine - Deterministic physics fallback mode."""
    
    def __init__(self):
        self._initialized = True
        self._telemetry_cache = None
        self._last_fetch_time = 0
        self._fetch_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._registered_sources: Dict[str, DataSourceConfig] = {}
        self._source_order = []
        self._lock = threading.RLock()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._physics_engine = DeterministicPhysicsEngine()
        self._audit_log = deque(maxlen=1000)
        
        logger.info("[ADFI] local engine initialized")
        
        # PROMETHEUS: Set ADFI module as active
        set_active_module(module="adfi_engine", active=True)
    
    def _audit(self, event: str, details: Dict[str, Any]):
        self._audit_log.append({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, "details": details})
    
    def set_scenario(self, scenario: str):
        self._physics_engine.set_scenario(scenario)
    
    def register_fetcher(self, source_type: Union[DataSource, str], fetcher: Callable,
                        source_id: Optional[str] = None, priority: str = "normal") -> bool:
        normalized_source_type = DataSource.normalize_source_type(source_type)
        source_enum = DataSource.to_enum(source_type)
        
        banned_patterns = ["nuclear", "fusion", "quantum", "defense", "missile", "reactor", "weapon"]
        for pattern in banned_patterns:
            if pattern in normalized_source_type.lower():
                return False
        
        if not source_id:
            source_id = f"{normalized_source_type}_{uuid.uuid4().hex[:8]}"
        
        if not callable(fetcher):
            return False
        
        if not asyncio.iscoroutinefunction(fetcher):
            _original = fetcher
            async def async_wrapper():
                result = _original()
                if inspect.iscoroutine(result):
                    return await result
                return result
            fetcher = async_wrapper
        
        try:
            with self._lock:
                config = DataSourceConfig(
                    id=source_id, name=source_id.replace("_", " ").title(),
                    source_type=normalized_source_type, source_type_enum=source_enum,
                    fetcher=fetcher, priority=priority, timeout=5.0,
                    retry_count=3, cache_ttl=10.0, enabled=True
                )
                self._registered_sources[source_id] = config
                self._circuit_breakers[source_id] = CircuitBreaker(source_id, failure_threshold=3)
                self._update_source_order()
                self._audit("source_registered", {"source_id": source_id})
                
                # PROMETHEUS: Initialize source health
                set_adfi_source_health(source=normalized_source_type, healthy=True)
                
                return True
        except Exception:
            return False
    
    def _update_source_order(self):
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3, "fallback": 4}
        self._source_order = sorted(self._registered_sources.values(), key=lambda cfg: priority_order.get(cfg.priority, 2))
    
    def unregister_fetcher(self, source_id: str) -> bool:
        with self._lock:
            if source_id in self._registered_sources:
                config = self._registered_sources[source_id]
                set_adfi_source_health(source=config.source_type, healthy=False)
                del self._registered_sources[source_id]
                if source_id in self._circuit_breakers:
                    del self._circuit_breakers[source_id]
                self._update_source_order()
                return True
            return False
    
    def get_registered_sources(self) -> Dict[str, DataSourceConfig]:
        with self._lock:
            return dict(self._registered_sources)
    
    async def get_telemetry(self) -> Dict[str, Any]:
        self._fetch_count += 1
        now = time.time()
        fetch_start = now
        
        with self._lock:
            sources = list(self._source_order)
        
        for config in sources:
            if not config.enabled:
                continue
            
            cb = self._circuit_breakers.get(config.id)
            if cb and not cb.is_allowed():
                set_adfi_source_health(source=config.source_type, healthy=False)
                continue
            
            try:
                result = await asyncio.wait_for(config.fetcher(), timeout=config.timeout)
                if result and isinstance(result, dict):
                    fetch_latency = time.time() - fetch_start
                    self._success_count += 1
                    if cb:
                        cb.record_success()
                    self._telemetry_cache = result
                    self._last_fetch_time = now
                    config.success_count += 1
                    config.last_success = now
                    result["quality_score"] = DataQualityEngine.score_telemetry(result)
                    
                    # =========================================================
                    # PROMETHEUS: Record successful telemetry fetch
                    # =========================================================
                    source_label = result.get("source", config.source_type)
                    record_adfi_ingestion(
                        source=source_label,
                        packets=1,
                        latency_seconds=fetch_latency,
                        module="local_adfi_engine"
                    )
                    set_adfi_source_health(source=config.source_type, healthy=True)
                    
                    return result
            except Exception:
                pass
            
            if cb:
                cb.record_failure()
            config.error_count += 1
            set_adfi_source_health(source=config.source_type, healthy=False)
        
        self._failure_count += 1
        fallback_start = time.time()
        fallback = self._physics_engine.generate_telemetry()
        fallback["source"] = "deterministic_fallback"
        fallback["quality_score"] = DataQualityEngine.score_telemetry(fallback, "deterministic_fallback")
        
        # PROMETHEUS: Record fallback
        fallback_latency = time.time() - fallback_start
        record_adfi_ingestion(
            source="deterministic_fallback",
            packets=1,
            latency_seconds=fallback_latency,
            module="local_adfi_engine"
        )
        
        return fallback
    
    def get_statistics(self) -> Dict[str, Any]:
        success_rate = (self._success_count / max(1, self._fetch_count)) * 100
        stats = {
            "status": "active", "mode": "local_deterministic", "phase": "PHASE_1_PRODUCTION",
            "fetch_count": self._fetch_count, "success_count": self._success_count,
            "failure_count": self._failure_count, "success_rate_percent": round(success_rate, 2),
            "registered_sources": len(self._registered_sources),
            "physics_engine": self._physics_engine.get_statistics(),
            "audit_log_size": len(self._audit_log), "hf_dependency": False, "deterministic_mode": True
        }
        
        # PROMETHEUS: Update source health for all registered sources
        with self._lock:
            for source_id, config in self._registered_sources.items():
                healthy = (config.error_count < 3) and config.enabled
                set_adfi_source_health(source=config.source_type, healthy=healthy)
        
        return stats
    
    def get_physics_status(self) -> Dict[str, Any]:
        return self._physics_engine.get_statistics()
    
    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._audit_log)[-limit:]


# ============================================================================
# ADVANCED ADFI WRAPPER (unchanged structure, inherits instrumentation)
# ============================================================================

ADVANCED_ADFI_AVAILABLE = False
_advanced_orchestrator = None

if not HF_DISABLED:
    try:
        from backend.integrations.adfi_engine import get_orchestrator as get_advanced_orchestrator
        from backend.integrations.data_pipeline import get_data_pipeline as get_unified_pipeline
        ADVANCED_ADFI_AVAILABLE = True
        _advanced_orchestrator = get_advanced_orchestrator()
    except ImportError:
        pass
    except Exception:
        pass


class AdvancedADFIWrapper:
    """Wrapper for advanced ADFI."""
    
    def __init__(self):
        self._orchestrator = _advanced_orchestrator
        self._initialized = ADVANCED_ADFI_AVAILABLE and self._orchestrator is not None
        self._local_fallback = LocalADFIEngine()
        
        if self._initialized:
            try:
                logger.debug("[ADFI] advanced orchestrator connected")
                set_active_module(module="adfi_advanced", active=True)
            except Exception:
                pass
    
    def register_fetcher(self, source_type: Union[DataSource, str], fetcher: Callable,
                        source_id: Optional[str] = None, priority: str = "normal") -> bool:
        return self._local_fallback.register_fetcher(source_type, fetcher, source_id, priority)
    
    def unregister_fetcher(self, source_id: str) -> bool:
        return self._local_fallback.unregister_fetcher(source_id)
    
    def get_registered_sources(self) -> Dict[str, DataSourceConfig]:
        return self._local_fallback.get_registered_sources()
    
    async def get_telemetry(self) -> Dict[str, Any]:
        return await self._local_fallback.get_telemetry()
    
    def get_statistics(self) -> Dict[str, Any]:
        stats = self._local_fallback.get_statistics()
        stats["mode"] = "deterministic_wrapper"
        stats["advanced_available"] = self._initialized
        return stats


# ============================================================================
# UNIFIED ADFI ENGINE - SINGLETON
# ============================================================================

class ADFIEngine:
    """Unified ADFI Engine - Deterministic Physics Data Fabric."""
    
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
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._initialize_engine()
    
    def _initialize_engine(self):
        try:
            self._engine = LocalADFIEngine()
            self._mode = "deterministic_physics"
            logger.info("[ADFI] engine initialized mode=deterministic_physics")
            
            # PROMETHEUS: Mark ADFI module active on init
            set_active_module(module="adfi_engine", active=True)
        except Exception as e:
            logger.error(f"[ADFI] initialization failed: {e}")
            self._engine = None
            self._mode = "error"
            set_active_module(module="adfi_engine", active=False)
    
    def register_fetcher(self, source_type: Union[DataSource, str], fetcher: Callable,
                        source_id: Optional[str] = None, priority: str = "normal") -> bool:
        return self._engine.register_fetcher(source_type, fetcher, source_id, priority) if self._engine else False
    
    def unregister_fetcher(self, source_id: str) -> bool:
        return self._engine.unregister_fetcher(source_id) if self._engine else False
    
    def get_registered_sources(self) -> Dict[str, Any]:
        if not self._engine:
            return {}
        sources = self._engine.get_registered_sources()
        if hasattr(sources, 'values'):
            return {sid: cfg.to_dict() if hasattr(cfg, 'to_dict') else cfg for sid, cfg in sources.items()}
        return sources
    
    async def get_telemetry(self) -> Dict[str, Any]:
        if not self._engine:
            return self._get_error_telemetry()
        try:
            return await self._engine.get_telemetry()
        except Exception:
            return self._get_error_telemetry()
    
    def _get_error_telemetry(self) -> Dict[str, Any]:
        physics = DeterministicPhysicsEngine()
        telemetry = physics.generate_telemetry()
        telemetry["source"] = "adfi_emergency_fallback"
        telemetry["quality_score"] = 0.70
        
        # PROMETHEUS: Record emergency fallback
        record_adfi_ingestion(
            source="emergency_fallback",
            packets=1,
            latency_seconds=0.0,
            module="adfi_engine"
        )
        set_adfi_source_health(source="adfi_engine", healthy=False)
        
        return telemetry
    
    def get_statistics(self) -> Dict[str, Any]:
        if not self._engine:
            return {"status": "degraded", "mode": "uninitialized", "phase": "PHASE_1_PRODUCTION"}
        stats = self._engine.get_statistics()
        stats["version"] = "4.1.0"
        stats["hf_dependency"] = False
        stats["deterministic_mode"] = True
        stats["metrics_instrumented"] = _METRICS_AVAILABLE
        return stats
    
    def get_mode(self) -> str:
        return self._mode or "unknown"
    
    def set_scenario(self, scenario: str):
        if self._engine and hasattr(self._engine, 'set_scenario'):
            self._engine.set_scenario(scenario)
    
    def get_physics_status(self) -> Dict[str, Any]:
        if self._engine and hasattr(self._engine, 'get_physics_status'):
            return self._engine.get_physics_status()
        return {"physics_mode": True, "hf_dependency": False}
    
    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self._engine and hasattr(self._engine, 'get_audit_log'):
            return self._engine.get_audit_log(limit)
        return []
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            telemetry = await self.get_telemetry()
            return {
                "status": "healthy", "mode": self._mode, "deterministic": True,
                "hf_dependency": False, "telemetry_quality": telemetry.get("quality_score", 0.5),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "degraded", "mode": self._mode, "deterministic": True,
                "warning": str(e), "timestamp": datetime.now(timezone.utc).isoformat()
            }


# ============================================================================
# SINGLETON ACCESSOR FUNCTIONS
# ============================================================================

_adfi_engine: Optional[ADFIEngine] = None
_engine_lock = threading.RLock()


def get_adfi_engine() -> ADFIEngine:
    global _adfi_engine
    if _adfi_engine is None:
        with _engine_lock:
            if _adfi_engine is None:
                _adfi_engine = ADFIEngine()
                logger.info("[ADFI] singleton engine created")
    return _adfi_engine


def reset_adfi_engine():
    global _adfi_engine
    with _engine_lock:
        _adfi_engine = None


def get_physics_status() -> Dict[str, Any]:
    return get_adfi_engine().get_physics_status()


def get_audit_log(limit: int = 50) -> List[Dict[str, Any]]:
    return get_adfi_engine().get_audit_log(limit)


async def initialize_adfi():
    engine = get_adfi_engine()
    try:
        telemetry = await engine.get_telemetry()
        logger.info(f"[ADFI] initialization complete mode={engine.get_mode()} quality={telemetry.get('quality_score', 0)}")
        
        # PROMETHEUS: Confirm ADFI module active after init
        set_active_module(module="adfi_engine", active=True)
    except Exception as e:
        logger.error(f"[ADFI] initialization warning: {e}")
        set_active_module(module="adfi_engine", active=False)
    return engine


async def shutdown_adfi():
    global _adfi_engine
    logger.info("[ADFI] shutdown")
    
    # PROMETHEUS: Mark module inactive on shutdown
    set_active_module(module="adfi_engine", active=False)
    
    _adfi_engine = None


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def get_grid_metrics() -> Dict[str, float]:
    telemetry = await get_adfi_engine().get_telemetry()
    return {
        "frequency_hz": telemetry.get("grid_frequency_hz", 50.0),
        "voltage_v": telemetry.get("grid_voltage_v", 230.0),
        "active_power_kw": telemetry.get("active_power_kw", 500.0),
        "demand_kw": telemetry.get("demand_load_kw", 500.0)
    }


async def get_solar_metrics() -> Dict[str, float]:
    telemetry = await get_adfi_engine().get_telemetry()
    return {
        "output_kw": telemetry.get("solar_output_kw", 50.0),
        "irradiance_wm2": telemetry.get("irradiance_wm2", 500.0),
        "temperature_c": telemetry.get("temperature_c", 25.0),
        "cloud_cover_percent": telemetry.get("cloud_cover_percent", 50.0)
    }


async def get_aece_risk() -> float:
    telemetry = await get_adfi_engine().get_telemetry()
    return telemetry.get("aece_risk_factor", 0.15)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'ADFIEngine', 'get_adfi_engine', 'reset_adfi_engine', 'initialize_adfi', 'shutdown_adfi',
    'get_grid_metrics', 'get_solar_metrics', 'get_aece_risk',
    'HardwareFetcher', 'APIFetcher', 'DataSource', 'DataPriority', 'DataSourceConfig',
    'CircuitBreaker', 'DeterministicPhysicsEngine', 'DataQualityEngine',
    'get_physics_status', 'get_audit_log'
]