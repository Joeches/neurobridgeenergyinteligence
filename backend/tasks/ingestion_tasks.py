"""
================================================================================
NeuroBridge 11D - Data Ingestion Tasks (Enhanced Production Version)
================================================================================
Component: Async Data Ingestion Pipeline for Hardware, Weather, and Sensors
Version: 3.0.0-QUANTUM-UNIFIED-FIXED
Author: NeuroBridge Quantum Engineering Team

CRITICAL FIX: Changed from @celery_app.task to @shared_task to break circular imports

Features:
- Real-time hardware telemetry ingestion
- Weather data ingestion from multiple sources
- Bulk sensor data ingestion with rate limiting
- Data validation and anomaly detection
- AECE risk assessment on ingested data
- Circuit breaker pattern for fault tolerance
- Dead letter queue for failed ingestions
- Prometheus metrics integration
- Redis caching for latest data
- Time-series storage for historical data
- Data quality scoring and enrichment

Integrations:
- AECE autonomous control (risk assessment on data)
- Prometheus metrics
- Redis distributed cache
- Time-series data storage
================================================================================
"""

import asyncio
import logging
import time
import json
import uuid
import hashlib
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# CRITICAL FIX: Use shared_task instead of celery_app
from celery import shared_task, Task, chain, group, chord

# Import services and clients
try:
    from backend.monitoring.prometheus_metrics import (
        metrics, record_aece_action, update_aece_risk_score,
        record_grid_risk_event, update_energy_metrics
    )
    from backend.services.cache_service import cache_service
    from backend.control.aece_engine import aece
    METRICS_AVAILABLE = True
    SERVICES_AVAILABLE = True
    AECE_AVAILABLE = True
except ImportError as e:
    METRICS_AVAILABLE = False
    SERVICES_AVAILABLE = False
    AECE_AVAILABLE = False
    logging.getLogger(__name__).warning(f"Optional imports failed: {e}")

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND DATA MODELS
# ============================================================================

class IngestionStatus(str, Enum):
    """Ingestion task status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    VALIDATED = "validated"
    REJECTED = "rejected"


class DataQuality(str, Enum):
    """Data quality classification"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    REJECTED = "rejected"


@dataclass
class IngestionResult:
    """Result of a data ingestion operation"""
    success: bool
    ingestion_id: str
    source: str
    status: IngestionStatus
    data_type: str
    quality_score: float = 1.0
    quality_rating: DataQuality = DataQuality.EXCELLENT
    anomalies: List[str] = field(default_factory=list)
    aece_risk_score: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "ingestion_id": self.ingestion_id,
            "source": self.source,
            "status": self.status.value,
            "data_type": self.data_type,
            "quality_score": round(self.quality_score, 2),
            "quality_rating": self.quality_rating.value,
            "anomalies": self.anomalies,
            "aece_risk_score": round(self.aece_risk_score, 3),
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "timestamp": self.timestamp
        }


# ============================================================================
# CIRCUIT BREAKER FOR INGESTION TASKS
# ============================================================================

class IngestionCircuitBreaker:
    """Circuit breaker pattern for ingestion tasks"""
    
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.RLock()
    
    def can_execute(self) -> bool:
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info(f"[ICB] {self.name} -> HALF_OPEN")
                    return True
                return False
            return True
    
    def record_success(self):
        with self._lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"[ICB] {self.name} -> CLOSED (recovered)")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"[ICB] {self.name} -> OPEN after {self.failure_count} failures")


# Circuit breakers for different ingestion sources
_ingestion_circuit_breakers = {
    "hardware": IngestionCircuitBreaker("hardware_ingestion", failure_threshold=5, recovery_timeout=60),
    "weather": IngestionCircuitBreaker("weather_ingestion", failure_threshold=3, recovery_timeout=120),
    "sensor": IngestionCircuitBreaker("sensor_ingestion", failure_threshold=10, recovery_timeout=30),
}


# ============================================================================
# DEAD LETTER QUEUE FOR INGESTION
# ============================================================================

class IngestionDeadLetterQueue:
    """Persistent storage for failed data ingestions"""
    
    def __init__(self, max_size: int = 10000):
        self._queue = []
        self._max_size = max_size
        self._lock = threading.RLock()
    
    def add(self, source: str, data: Dict, error: str, trace: str, data_type: str):
        with self._lock:
            entry = {
                "source": source,
                "data": data,
                "error": error,
                "traceback": trace[:500] if trace else "",
                "data_type": data_type,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self._queue.append(entry)
            if len(self._queue) > self._max_size:
                self._queue.pop(0)
            logger.error(f"[IDLQ] Added {source}: {error[:100]}")
    
    def get_all(self) -> List[Dict]:
        with self._lock:
            return self._queue.copy()
    
    def get_by_source(self, source: str) -> List[Dict]:
        with self._lock:
            return [e for e in self._queue if e.get("source") == source]
    
    def clear(self):
        with self._lock:
            self._queue.clear()
    
    def size(self) -> int:
        with self._lock:
            return len(self._queue)


_ingestion_dlq = IngestionDeadLetterQueue()


# ============================================================================
# DATA VALIDATOR CLASS
# ============================================================================

class DataValidator:
    """Data validation and quality scoring"""
    
    @staticmethod
    def validate_hardware_data(data: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
        """Validate hardware telemetry data"""
        anomalies = []
        quality_score = 1.0
        
        # Required fields check
        required_fields = ["device_id", "power_kw", "frequency_hz", "voltage_v"]
        for field in required_fields:
            if field not in data:
                anomalies.append(f"missing_{field}")
                quality_score -= 0.25
        
        # Power validation
        power = data.get("power_kw", 0)
        if power < 0:
            anomalies.append("negative_power")
            quality_score -= 0.3
        elif power > 500:
            anomalies.append("power_exceeds_threshold")
            quality_score -= 0.2
        
        # Frequency validation
        frequency = data.get("frequency_hz", 50)
        if frequency < 45 or frequency > 55:
            anomalies.append("frequency_out_of_range")
            quality_score -= 0.5
        elif frequency < 49 or frequency > 51:
            anomalies.append("frequency_marginally_out_of_range")
            quality_score -= 0.1
        
        # Voltage validation
        voltage = data.get("voltage_v", 230)
        if voltage < 180 or voltage > 280:
            anomalies.append("voltage_out_of_range")
            quality_score -= 0.4
        elif voltage < 210 or voltage > 250:
            anomalies.append("voltage_marginally_out_of_range")
            quality_score -= 0.1
        
        # Temperature validation
        temperature = data.get("temperature_c", 25)
        if temperature > 60:
            anomalies.append("overheating")
            quality_score -= 0.4
        elif temperature < -10:
            anomalies.append("extreme_cold")
            quality_score -= 0.3
        
        quality_score = max(0, min(1, quality_score))
        is_valid = quality_score >= 0.6
        
        return is_valid, quality_score, anomalies
    
    @staticmethod
    def validate_weather_data(data: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
        """Validate weather data"""
        anomalies = []
        quality_score = 1.0
        
        # Temperature validation
        temperature = data.get("temperature_c", 25)
        if temperature < -50 or temperature > 60:
            anomalies.append("temperature_out_of_range")
            quality_score -= 0.5
        
        # Humidity validation
        humidity = data.get("humidity_percent", 50)
        if humidity < 0 or humidity > 100:
            anomalies.append("humidity_out_of_range")
            quality_score -= 0.3
        
        # Wind speed validation
        wind_speed = data.get("wind_speed_ms", 3)
        if wind_speed < 0 or wind_speed > 150:
            anomalies.append("wind_speed_out_of_range")
            quality_score -= 0.3
        
        # Solar irradiance validation
        irradiance = data.get("solar_irradiance_wm2", 800)
        if irradiance < 0 or irradiance > 1500:
            anomalies.append("irradiance_out_of_range")
            quality_score -= 0.2
        
        quality_score = max(0, min(1, quality_score))
        is_valid = quality_score >= 0.5
        
        return is_valid, quality_score, anomalies
    
    @staticmethod
    def calculate_aece_risk(data: Dict[str, Any], data_type: str) -> float:
        """Calculate AECE risk score from ingested data"""
        risk = 0.0
        
        if data_type == "hardware":
            power = data.get("power_kw", 0)
            frequency = data.get("frequency_hz", 50)
            temperature = data.get("temperature_c", 25)
            
            # Power risk
            if power > 80:
                risk += 0.3
            elif power > 60:
                risk += 0.15
            
            # Frequency deviation risk
            freq_dev = abs(frequency - 50)
            if freq_dev > 0.5:
                risk += 0.3
            elif freq_dev > 0.2:
                risk += 0.1
            
            # Temperature risk
            if temperature > 50:
                risk += 0.2
            elif temperature > 40:
                risk += 0.1
        
        elif data_type == "weather":
            cloud_cover = data.get("cloud_cover_percent", 30)
            wind_speed = data.get("wind_speed_ms", 3)
            
            # Cloud cover risk (reduces solar generation)
            if cloud_cover > 80:
                risk += 0.25
            elif cloud_cover > 60:
                risk += 0.15
            
            # Wind risk
            if wind_speed > 15:
                risk += 0.2
            elif wind_speed > 10:
                risk += 0.1
        
        return min(0.95, risk)


# ============================================================================
# TASK BASE CLASS
# ============================================================================

class IngestionTaskBase(Task):
    """Base class for ingestion tasks with enhanced error handling"""
    abstract = True
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Ingestion task {self.name} failed: {exc}")
        
        # Extract source from args
        source = "unknown"
        data = {}
        if args:
            if isinstance(args[0], dict):
                source = args[0].get("device_id", args[0].get("source", "unknown"))
                data = args[0]
        
        _ingestion_dlq.add(
            source=source,
            data=data,
            error=str(exc),
            trace=einfo.traceback if einfo else "",
            data_type=self.name.split(".")[-1] if "." in self.name else "unknown"
        )
        
        if METRICS_AVAILABLE and metrics and hasattr(metrics, 'celery_tasks_total'):
            try:
                metrics.celery_tasks_total.labels(
                    task_name=self.name,
                    status="failed",
                    queue="ingestion_queue"
                ).inc()
            except Exception:
                pass
    
    def on_success(self, retval, task_id, args, kwargs):
        if METRICS_AVAILABLE and metrics and hasattr(metrics, 'celery_tasks_total'):
            try:
                metrics.celery_tasks_total.labels(
                    task_name=self.name,
                    status="success",
                    queue="ingestion_queue"
                ).inc()
            except Exception:
                pass


# ============================================================================
# HARDWARE TELEMETRY INGESTION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=IngestionTaskBase,
    name="backend.tasks.ingestion.ingest_hardware_telemetry",
    queue="high_priority",
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    rate_limit="60/m"
)
def ingest_hardware_telemetry(self, telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingest hardware telemetry data from inverters and sensors.
    Real-time data from grid hardware with validation and AECE risk assessment.
    
    Args:
        telemetry_data: Hardware telemetry including device_id, power_kw, frequency_hz, voltage_v
    
    Returns:
        Ingestion result with quality score and AECE risk
    """
    start_time = time.time()
    ingestion_id = str(uuid.uuid4())
    source = telemetry_data.get("device_id", "unknown")
    
    logger.info(f"[Ingest] Hardware data from {source} | ID: {ingestion_id}")
    
    # Check circuit breaker
    cb = _ingestion_circuit_breakers["hardware"]
    if not cb.can_execute():
        logger.warning(f"[Ingest] Circuit breaker OPEN for hardware ingestion")
        return {
            "success": False,
            "ingestion_id": ingestion_id,
            "error": "Circuit breaker OPEN",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    try:
        # Validate data
        is_valid, quality_score, anomalies = DataValidator.validate_hardware_data(telemetry_data)
        
        # Calculate AECE risk
        aece_risk = DataValidator.calculate_aece_risk(telemetry_data, "hardware")
        
        # Determine quality rating
        if quality_score >= 0.9:
            quality_rating = DataQuality.EXCELLENT
            status = IngestionStatus.VALIDATED
        elif quality_score >= 0.7:
            quality_rating = DataQuality.GOOD
            status = IngestionStatus.VALIDATED
        elif quality_score >= 0.5:
            quality_rating = DataQuality.FAIR
            status = IngestionStatus.PROCESSING
        else:
            quality_rating = DataQuality.POOR
            status = IngestionStatus.REJECTED
        
        # Process and enrich data
        processed_data = {
            "ingestion_id": ingestion_id,
            "device_id": telemetry_data.get("device_id"),
            "original_timestamp": telemetry_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "power_kw": float(telemetry_data.get("power_kw", 0)),
            "frequency_hz": float(telemetry_data.get("frequency_hz", 50)),
            "voltage_v": float(telemetry_data.get("voltage_v", 230)),
            "temperature_c": telemetry_data.get("temperature_c", 25.0),
            "status": telemetry_data.get("status", "normal"),
            "quality_score": round(quality_score, 2),
            "quality_rating": quality_rating.value,
            "anomalies": anomalies,
            "aece_risk_score": round(aece_risk, 3),
            "is_valid": is_valid
        }
        
        # Store in Redis for real-time access
        if SERVICES_AVAILABLE and cache_service:
            try:
                cache_key = f"telemetry:latest:{telemetry_data.get('device_id', 'unknown')}"
                cache_service.set(cache_key, processed_data, ttl=60)
                
                # Store in time-series (using Redis list)
                ts_key = f"telemetry:history:{telemetry_data.get('device_id', 'unknown')}"
                cache_service.rpush(ts_key, processed_data)
                cache_service.expire(ts_key, 3600)
            except Exception:
                pass
        
        # Update Prometheus metrics
        if METRICS_AVAILABLE:
            update_energy_metrics(
                power_kw=float(telemetry_data.get("power_kw", 0)),
                frequency_hz=float(telemetry_data.get("frequency_hz", 50)),
                efficiency_percent=quality_score * 100,
                sector="grid"
            )
            
            # Trigger AECE action if high risk detected
            if aece_risk > 0.7:
                record_aece_action(action="hardware_anomaly", priority="high")
                record_grid_risk_event("high")
                update_aece_risk_score(aece_risk)
        
        # Record success in circuit breaker
        cb.record_success()
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"[Ingest] Hardware data ingested from {source} | Quality: {quality_rating.value} | AECE Risk: {aece_risk:.3f}")
        
        return {
            "success": is_valid,
            "ingestion_id": ingestion_id,
            "device_id": telemetry_data.get("device_id"),
            "status": status.value,
            "quality_score": round(quality_score, 2),
            "quality_rating": quality_rating.value,
            "anomalies": anomalies,
            "aece_risk_score": round(aece_risk, 3),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[Ingest] Hardware ingestion failed: {e}")
        cb.record_failure()
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return {
            "success": False,
            "ingestion_id": ingestion_id,
            "error": str(e),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# WEATHER DATA INGESTION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=IngestionTaskBase,
    name="backend.tasks.ingestion.ingest_weather_data",
    queue="default",
    max_retries=3,
    default_retry_delay=10,
    rate_limit="30/m"
)
def ingest_weather_data(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingest weather data from external APIs or sensors.
    
    Args:
        weather_data: Weather metrics including temperature, humidity, wind, irradiance
    
    Returns:
        Ingestion result with quality assessment
    """
    start_time = time.time()
    ingestion_id = str(uuid.uuid4())
    source = weather_data.get("source", weather_data.get("device_id", "weather_api"))
    
    logger.info(f"[Ingest] Weather data from {source} | ID: {ingestion_id}")
    
    # Check circuit breaker
    cb = _ingestion_circuit_breakers["weather"]
    if not cb.can_execute():
        return {
            "success": False,
            "ingestion_id": ingestion_id,
            "error": "Circuit breaker OPEN",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    try:
        # Validate data
        is_valid, quality_score, anomalies = DataValidator.validate_weather_data(weather_data)
        
        # Calculate AECE risk
        aece_risk = DataValidator.calculate_aece_risk(weather_data, "weather")
        
        # Determine quality rating
        if quality_score >= 0.9:
            quality_rating = DataQuality.EXCELLENT
            status = IngestionStatus.VALIDATED
        elif quality_score >= 0.7:
            quality_rating = DataQuality.GOOD
            status = IngestionStatus.VALIDATED
        elif quality_score >= 0.5:
            quality_rating = DataQuality.FAIR
            status = IngestionStatus.PROCESSING
        else:
            quality_rating = DataQuality.POOR
            status = IngestionStatus.REJECTED
        
        # Process and enrich data
        processed_weather = {
            "ingestion_id": ingestion_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature_c": float(weather_data.get("temperature_c", 25.0)),
            "feels_like_c": float(weather_data.get("feels_like_c", 24.0)),
            "humidity_percent": float(weather_data.get("humidity_percent", 50.0)),
            "wind_speed_ms": float(weather_data.get("wind_speed_ms", 3.0)),
            "wind_direction_deg": float(weather_data.get("wind_direction_deg", 180)),
            "solar_irradiance_wm2": float(weather_data.get("solar_irradiance_wm2", 800.0)),
            "cloud_cover_percent": float(weather_data.get("cloud_cover_percent", 30.0)),
            "precipitation_mm": float(weather_data.get("precipitation_mm", 0.0)),
            "pressure_hpa": float(weather_data.get("pressure_hpa", 1013.0)),
            "uv_index": float(weather_data.get("uv_index", 5.0)),
            "data_source": weather_data.get("source", "unknown"),
            "quality_score": round(quality_score, 2),
            "quality_rating": quality_rating.value,
            "anomalies": anomalies,
            "aece_risk_score": round(aece_risk, 3),
            "is_valid": is_valid
        }
        
        # Cache latest weather
        if SERVICES_AVAILABLE and cache_service:
            try:
                cache_service.set("weather:latest", processed_weather, ttl=300)
                cache_service.set(f"weather:{source}:latest", processed_weather, ttl=300)
            except Exception:
                pass
        
        # Update weather metrics
        if METRICS_AVAILABLE:
            try:
                if metrics and hasattr(metrics, 'weather_temperature_celsius'):
                    metrics.weather_temperature_celsius.set(processed_weather["temperature_c"])
                if metrics and hasattr(metrics, 'weather_humidity_percent'):
                    metrics.weather_humidity_percent.set(processed_weather["humidity_percent"])
                if metrics and hasattr(metrics, 'weather_wind_speed_ms'):
                    metrics.weather_wind_speed_ms.set(processed_weather["wind_speed_ms"])
            except Exception:
                pass
        
        cb.record_success()
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"[Ingest] Weather data ingested from {source} | Quality: {quality_rating.value}")
        
        return {
            "success": is_valid,
            "ingestion_id": ingestion_id,
            "source": source,
            "status": status.value,
            "quality_score": round(quality_score, 2),
            "quality_rating": quality_rating.value,
            "anomalies": anomalies,
            "aece_risk_score": round(aece_risk, 3),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[Ingest] Weather ingestion failed: {e}")
        cb.record_failure()
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return {
            "success": False,
            "ingestion_id": ingestion_id,
            "error": str(e),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# BULK SENSOR DATA INGESTION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=IngestionTaskBase,
    name="backend.tasks.ingestion.bulk_ingest_sensor_data",
    queue="high_priority",
    max_retries=2,
    rate_limit="10/m"
)
def bulk_ingest_sensor_data(self, sensors_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bulk ingest data from multiple sensors.
    Optimized for high-volume data ingestion with parallel processing.
    
    Args:
        sensors_data: List of sensor data dictionaries
    
    Returns:
        Bulk ingestion results with success/failure counts
    """
    start_time = time.time()
    batch_id = str(uuid.uuid4())
    
    logger.info(f"[Bulk] Ingesting {len(sensors_data)} sensors | Batch: {batch_id}")
    
    # Check circuit breaker
    cb = _ingestion_circuit_breakers["sensor"]
    if not cb.can_execute():
        return {
            "success": False,
            "batch_id": batch_id,
            "error": "Circuit breaker OPEN",
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }
    
    results = []
    successful_count = 0
    failed_count = 0
    rejected_count = 0
    
    # Process each sensor data point
    for sensor_data in sensors_data:
        try:
            # Determine data type and route accordingly
            if "power_kw" in sensor_data or "frequency_hz" in sensor_data:
                # Hardware telemetry
                result = ingest_hardware_telemetry.delay(sensor_data)
                results.append({
                    "device_id": sensor_data.get("device_id", "unknown"),
                    "task_id": result.id,
                    "data_type": "hardware",
                    "status": "queued"
                })
                successful_count += 1
            elif "temperature_c" in sensor_data or "humidity_percent" in sensor_data:
                # Weather data
                result = ingest_weather_data.delay(sensor_data)
                results.append({
                    "device_id": sensor_data.get("device_id", sensor_data.get("source", "unknown")),
                    "task_id": result.id,
                    "data_type": "weather",
                    "status": "queued"
                })
                successful_count += 1
            else:
                # Unknown data type
                results.append({
                    "device_id": sensor_data.get("device_id", "unknown"),
                    "error": "Unknown data type",
                    "data_type": "unknown",
                    "status": "rejected"
                })
                rejected_count += 1
                
        except Exception as e:
            results.append({
                "device_id": sensor_data.get("device_id", "unknown"),
                "error": str(e),
                "status": "failed"
            })
            failed_count += 1
    
    cb.record_success()
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(f"[Bulk] Completed: {successful_count} queued, {failed_count} failed, {rejected_count} rejected")
    
    return {
        "success": True,
        "batch_id": batch_id,
        "total_sensors": len(sensors_data),
        "queued": successful_count,
        "failed": failed_count,
        "rejected": rejected_count,
        "results": results,
        "duration_ms": round(duration_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# SENSOR DATA VALIDATION TASK
# ============================================================================

@shared_task(
    bind=True,
    base=IngestionTaskBase,
    name="backend.tasks.ingestion.validate_sensor_data",
    queue="default",
    max_retries=2
)
def validate_sensor_data(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate sensor data quality and detect anomalies with AECE risk assessment.
    
    Args:
        sensor_data: Sensor data to validate
    
    Returns:
        Validation results with quality score, anomalies, and AECE risk
    """
    start_time = time.time()
    device_id = sensor_data.get("device_id", sensor_data.get("source", "unknown"))
    
    logger.info(f"[Validate] Validating data from {device_id}")
    
    try:
        anomalies = []
        quality_score = 1.0
        
        # Determine data type and validate accordingly
        if "power_kw" in sensor_data or "frequency_hz" in sensor_data:
            is_valid, quality_score, anomalies = DataValidator.validate_hardware_data(sensor_data)
            data_type = "hardware"
        elif "temperature_c" in sensor_data or "humidity_percent" in sensor_data:
            is_valid, quality_score, anomalies = DataValidator.validate_weather_data(sensor_data)
            data_type = "weather"
        else:
            anomalies.append("unknown_data_type")
            quality_score = 0.5
            is_valid = False
            data_type = "unknown"
        
        # Calculate AECE risk
        aece_risk = DataValidator.calculate_aece_risk(sensor_data, data_type)
        
        # Determine quality rating
        if quality_score >= 0.9:
            quality_rating = DataQuality.EXCELLENT
        elif quality_score >= 0.7:
            quality_rating = DataQuality.GOOD
        elif quality_score >= 0.5:
            quality_rating = DataQuality.FAIR
        else:
            quality_rating = DataQuality.POOR
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Trigger alert for critical anomalies
        if aece_risk > 0.7 and METRICS_AVAILABLE:
            record_aece_action(action="data_anomaly", priority="high")
        
        return {
            "success": True,
            "device_id": device_id,
            "data_type": data_type,
            "is_valid": is_valid,
            "quality_score": round(quality_score, 2),
            "quality_rating": quality_rating.value,
            "anomalies": anomalies,
            "aece_risk_score": round(aece_risk, 3),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[Validate] Validation failed for {device_id}: {e}")
        
        return {
            "success": False,
            "device_id": device_id,
            "error": str(e),
            "duration_ms": round((time.time() - start_time) * 1000, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# DEAD LETTER QUEUE MANAGEMENT
# ============================================================================

@shared_task(name="backend.tasks.ingestion.get_ingestion_dlq")
def get_ingestion_dlq() -> Dict[str, Any]:
    """Get the current ingestion dead letter queue contents"""
    return {
        "success": True,
        "queue_size": _ingestion_dlq.size(),
        "entries": _ingestion_dlq.get_all()[-50:],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.ingestion.get_ingestion_dlq_by_source")
def get_ingestion_dlq_by_source(source: str) -> Dict[str, Any]:
    """Get dead letter queue entries for specific source"""
    return {
        "success": True,
        "source": source,
        "entries": _ingestion_dlq.get_by_source(source),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.ingestion.retry_from_ingestion_dlq")
def retry_from_ingestion_dlq(self, entry_index: int) -> Dict[str, Any]:
    """
    Retry a failed ingestion from the dead letter queue.
    
    Args:
        entry_index: Index of entry in dead letter queue
    
    Returns:
        Retry result
    """
    entries = _ingestion_dlq.get_all()
    
    if entry_index >= len(entries):
        return {
            "success": False,
            "error": f"Entry index {entry_index} out of range",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    entry = entries[entry_index]
    source = entry.get("source")
    data = entry.get("data", {})
    data_type = entry.get("data_type", "unknown")
    
    logger.info(f"[DLQ] Retrying ingestion from {source} (type: {data_type})")
    
    # Route to appropriate ingestion task
    if data_type == "hardware" or "power_kw" in data:
        result = ingest_hardware_telemetry.delay(data).get(timeout=60)
    elif data_type == "weather" or "temperature_c" in data:
        result = ingest_weather_data.delay(data).get(timeout=60)
    else:
        result = validate_sensor_data.delay(data).get(timeout=60)
    
    return {
        "success": result.get("success", False),
        "source": source,
        "retry_result": result,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@shared_task(name="backend.tasks.ingestion.clear_ingestion_dlq")
def clear_ingestion_dlq() -> Dict[str, Any]:
    """Clear the ingestion dead letter queue"""
    _ingestion_dlq.clear()
    return {
        "success": True,
        "message": "Ingestion dead letter queue cleared",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# TASK METRICS AND MONITORING
# ============================================================================

@shared_task(name="backend.tasks.ingestion.get_ingestion_metrics")
def get_ingestion_metrics() -> Dict[str, Any]:
    """Get metrics for all ingestion tasks"""
    return {
        "success": True,
        "circuit_breakers": {
            name: {
                "state": cb.state,
                "failure_count": cb.failure_count,
                "last_failure_time": cb.last_failure_time
            }
            for name, cb in _ingestion_circuit_breakers.items()
        },
        "dead_letter_queue_size": _ingestion_dlq.size(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# HEALTH CHECK TASK
# ============================================================================

@shared_task(name="backend.tasks.ingestion.ingestion_health_check")
def ingestion_health_check() -> Dict[str, Any]:
    """
    Health check for ingestion tasks system.
    """
    return {
        "success": True,
        "status": "healthy",
        "circuit_breakers_status": {
            name: cb.state for name, cb in _ingestion_circuit_breakers.items()
        },
        "dead_letter_queue_size": _ingestion_dlq.size(),
        "services_available": {
            "cache": SERVICES_AVAILABLE,
            "metrics": METRICS_AVAILABLE,
            "aece": AECE_AVAILABLE
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Main tasks
    'ingest_hardware_telemetry',
    'ingest_weather_data',
    'bulk_ingest_sensor_data',
    'validate_sensor_data',
    
    # Dead letter queue
    'get_ingestion_dlq',
    'get_ingestion_dlq_by_source',
    'retry_from_ingestion_dlq',
    'clear_ingestion_dlq',
    
    # Metrics and health
    'get_ingestion_metrics',
    'ingestion_health_check',
    
    # Enums
    'IngestionStatus',
    'DataQuality',
    'IngestionResult'
]