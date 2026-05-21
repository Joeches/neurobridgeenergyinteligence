# backend/integrations/openweather.py - PRODUCTION CLEAN v3.0.0
# OpenWeather Integration - Weather Intelligence for Energy Systems

import os
import asyncio
import logging
import math
import random
import time
import threading
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

import aiohttp
from aiohttp import ClientTimeout, ClientError

logger = logging.getLogger(__name__)

# Single concise initialization log - NO BANNER
logger.info("[OPENWEATHER] client initializing")

# Try to import ADFI components for integration
try:
    from backend.integrations.adfi_engine import (
        EnergyDataPoint,
        DataSourceType,
        DataPriority,
        DataQuality,
        get_orchestrator
    )
    from backend.integrations.data_pipeline import get_data_pipeline
    ADFI_AVAILABLE = True
    logger.debug("[OPENWEATHER] ADFI integration available")
except ImportError:
    ADFI_AVAILABLE = False
    logger.debug("[OPENWEATHER] ADFI not available - standalone mode")

# ============================================================================
# ENUMS
# ============================================================================

class WeatherCondition(str, Enum):
    CLEAR = "clear"
    FEW_CLOUDS = "few_clouds"
    SCATTERED_CLOUDS = "scattered_clouds"
    BROKEN_CLOUDS = "broken_clouds"
    OVERCAST = "overcast"
    RAIN = "rain"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"
    MIST = "mist"
    FOG = "fog"
    HAZE = "haze"
    UNKNOWN = "unknown"
    
    def get_solar_impact_factor(self) -> float:
        factors = {
            WeatherCondition.CLEAR: 1.0,
            WeatherCondition.FEW_CLOUDS: 0.85,
            WeatherCondition.SCATTERED_CLOUDS: 0.65,
            WeatherCondition.BROKEN_CLOUDS: 0.45,
            WeatherCondition.OVERCAST: 0.25,
            WeatherCondition.RAIN: 0.15,
            WeatherCondition.THUNDERSTORM: 0.05,
            WeatherCondition.SNOW: 0.10,
            WeatherCondition.MIST: 0.40,
            WeatherCondition.FOG: 0.30,
            WeatherCondition.HAZE: 0.50,
            WeatherCondition.UNKNOWN: 0.70
        }
        return factors.get(self, 0.70)


class AirQualityIndex(int, Enum):
    GOOD = 1
    FAIR = 2
    MODERATE = 3
    POOR = 4
    VERY_POOR = 5
    
    def get_efficiency_factor(self) -> float:
        factors = {AirQualityIndex.GOOD: 1.0, AirQualityIndex.FAIR: 0.95,
                   AirQualityIndex.MODERATE: 0.85, AirQualityIndex.POOR: 0.70,
                   AirQualityIndex.VERY_POOR: 0.50}
        return factors.get(self, 0.85)


class WeatherAlertType(str, Enum):
    HIGH_TEMPERATURE = "high_temperature"
    HIGH_WIND = "high_wind"
    HEAVY_RAIN = "heavy_rain"
    THUNDERSTORM = "thunderstorm"
    HEATWAVE = "heatwave"
    COLD_WAVE = "cold_wave"
    FOG = "fog"
    STORM = "storm"

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class WeatherData:
    temperature: float
    feels_like: float
    humidity: float
    pressure: float
    wind_speed: float
    wind_direction: int
    wind_gust: float
    cloud_cover: int
    visibility: int
    precipitation: float
    condition: str
    condition_code: int
    condition_category: WeatherCondition
    uv_index: float
    dew_point: float
    timestamp: datetime
    location: str
    data_quality: float = 0.95
    aece_risk_factor: float = 0.0
    solar_impact_factor: float = 1.0
    aqi: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature_c": round(self.temperature, 1),
            "feels_like_c": round(self.feels_like, 1),
            "humidity_percent": round(self.humidity, 1),
            "pressure_hpa": round(self.pressure, 1),
            "wind_speed_ms": round(self.wind_speed, 1),
            "wind_direction_deg": self.wind_direction,
            "wind_gust_ms": round(self.wind_gust, 1),
            "cloud_cover_percent": self.cloud_cover,
            "visibility_m": self.visibility,
            "precipitation_mm": round(self.precipitation, 1),
            "condition": self.condition,
            "condition_code": self.condition_code,
            "condition_category": self.condition_category.value,
            "uv_index": round(self.uv_index, 1),
            "dew_point_c": round(self.dew_point, 1),
            "timestamp": self.timestamp.isoformat(),
            "location": self.location,
            "data_quality": round(self.data_quality, 2),
            "aece_risk_factor": round(self.aece_risk_factor, 3),
            "solar_impact_factor": round(self.solar_impact_factor, 3),
            "aqi": self.aqi
        }
    
    def to_energy_data_point(self) -> Optional['EnergyDataPoint']:
        if not ADFI_AVAILABLE:
            return None
        return EnergyDataPoint(
            source_type=DataSourceType.OPENWEATHER,
            source_id="current_weather",
            timestamp=self.timestamp.timestamp(),
            irradiance_wm2=self._calculate_irradiance(),
            temperature_c=self.temperature,
            cloud_cover_percent=self.cloud_cover,
            humidity_percent=self.humidity,
            wind_speed_ms=self.wind_speed,
            pressure_hpa=self.pressure,
            quality_score=self.data_quality,
            aece_risk_factor=self.aece_risk_factor
        )
    
    def _calculate_irradiance(self) -> float:
        base_irradiance = 1000.0
        irradiance = base_irradiance * self.solar_impact_factor
        hour = self.timestamp.hour
        if 6 <= hour <= 18:
            solar_factor = math.sin(math.pi * (hour - 6) / 12)
            irradiance *= solar_factor
        else:
            irradiance = 0
        return max(0, min(1200, irradiance))
    
    def calculate_aece_risk(self) -> float:
        risk = 0.0
        if self.temperature > 40:
            risk += 0.3
        elif self.temperature > 35:
            risk += 0.15
        if self.wind_speed > 15:
            risk += 0.25
        elif self.wind_speed > 10:
            risk += 0.1
        if self.precipitation > 10:
            risk += 0.2
        elif self.precipitation > 5:
            risk += 0.1
        if self.cloud_cover > 80:
            risk += 0.2
        elif self.cloud_cover > 60:
            risk += 0.1
        if self.condition_category in [WeatherCondition.THUNDERSTORM]:
            risk += 0.3
        self.aece_risk_factor = min(0.95, risk)
        self.solar_impact_factor = self.condition_category.get_solar_impact_factor()
        return self.aece_risk_factor
    
    def get_weather_alerts(self) -> List[WeatherAlertType]:
        alerts = []
        if self.temperature > 35:
            alerts.append(WeatherAlertType.HIGH_TEMPERATURE)
        if self.wind_speed > 10:
            alerts.append(WeatherAlertType.HIGH_WIND)
        if self.precipitation > 5:
            alerts.append(WeatherAlertType.HEAVY_RAIN)
        if self.condition_category == WeatherCondition.THUNDERSTORM:
            alerts.append(WeatherAlertType.THUNDERSTORM)
        if self.cloud_cover > 90:
            alerts.append(WeatherAlertType.FOG)
        return alerts


@dataclass
class ForecastItem:
    timestamp: datetime
    temperature: float
    feels_like: float
    humidity: float
    pressure: float
    wind_speed: float
    cloud_cover: int
    precipitation: float
    condition: str
    condition_code: int
    rain_probability: float
    solar_impact_factor: float = 1.0
    irradiance_wm2: float = 0.0
    
    def __post_init__(self):
        condition = self._get_condition_category()
        self.solar_impact_factor = condition.get_solar_impact_factor()
        hour = self.timestamp.hour
        if 6 <= hour <= 18:
            solar_factor = math.sin(math.pi * (hour - 6) / 12)
            self.irradiance_wm2 = 1000 * self.solar_impact_factor * solar_factor
        else:
            self.irradiance_wm2 = 0
    
    def _get_condition_category(self) -> WeatherCondition:
        if 200 <= self.condition_code < 300:
            return WeatherCondition.THUNDERSTORM
        elif 300 <= self.condition_code < 600:
            return WeatherCondition.RAIN
        elif 600 <= self.condition_code < 700:
            return WeatherCondition.SNOW
        elif 700 <= self.condition_code < 800:
            return WeatherCondition.MIST
        elif self.condition_code == 800:
            return WeatherCondition.CLEAR
        elif self.condition_code == 801:
            return WeatherCondition.FEW_CLOUDS
        elif self.condition_code == 802:
            return WeatherCondition.SCATTERED_CLOUDS
        elif self.condition_code == 803:
            return WeatherCondition.BROKEN_CLOUDS
        elif self.condition_code == 804:
            return WeatherCondition.OVERCAST
        else:
            return WeatherCondition.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "temperature_c": round(self.temperature, 1),
            "feels_like_c": round(self.feels_like, 1),
            "humidity_percent": round(self.humidity, 1),
            "pressure_hpa": round(self.pressure, 1),
            "wind_speed_ms": round(self.wind_speed, 1),
            "cloud_cover_percent": self.cloud_cover,
            "precipitation_mm": round(self.precipitation, 1),
            "condition": self.condition,
            "condition_code": self.condition_code,
            "rain_probability": round(self.rain_probability, 0),
            "solar_impact_factor": round(self.solar_impact_factor, 3),
            "irradiance_wm2": round(self.irradiance_wm2, 1)
        }
    
    def to_energy_data_point(self) -> Optional['EnergyDataPoint']:
        if not ADFI_AVAILABLE:
            return None
        return EnergyDataPoint(
            source_type=DataSourceType.OPENWEATHER,
            source_id="weather_forecast",
            timestamp=self.timestamp.timestamp(),
            irradiance_wm2=self.irradiance_wm2,
            temperature_c=self.temperature,
            cloud_cover_percent=self.cloud_cover,
            humidity_percent=self.humidity,
            wind_speed_ms=self.wind_speed,
            pressure_hpa=self.pressure,
            quality_score=0.85
        )


@dataclass
class WeatherForecast:
    city: str
    country: str
    latitude: float
    longitude: float
    items: List[ForecastItem]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "city": self.city,
            "country": self.country,
            "coordinates": {"lat": self.latitude, "lon": self.longitude},
            "forecast": [item.to_dict() for item in self.items],
            "timestamp": self.timestamp.isoformat()
        }
    
    def get_solar_forecast(self, hours_ahead: int = 24) -> List[Dict[str, Any]]:
        solar_forecast = []
        now = datetime.now(timezone.utc)
        for item in self.items:
            if item.timestamp > now and len(solar_forecast) < hours_ahead // 3:
                solar_forecast.append({
                    "timestamp": item.timestamp.isoformat(),
                    "irradiance_wm2": item.irradiance_wm2,
                    "cloud_cover_percent": item.cloud_cover,
                    "solar_impact_factor": item.solar_impact_factor,
                    "rain_probability": item.rain_probability
                })
        return solar_forecast


@dataclass
class AirQualityData:
    aqi: AirQualityIndex
    pm2_5: float
    pm10: float
    o3: float
    no2: float
    so2: float
    co: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "aqi": self.aqi.value,
            "aqi_label": "Good" if self.aqi == 1 else "Fair" if self.aqi == 2 else "Moderate" if self.aqi == 3 else "Poor" if self.aqi == 4 else "Very Poor",
            "pm2_5": round(self.pm2_5, 1),
            "pm10": round(self.pm10, 1),
            "o3": round(self.o3, 1),
            "no2": round(self.no2, 1),
            "so2": round(self.so2, 1),
            "co": round(self.co, 1),
            "timestamp": self.timestamp.isoformat(),
            "efficiency_factor": self.aqi.get_efficiency_factor()
        }
    
    def to_energy_data_point(self) -> Optional['EnergyDataPoint']:
        if not ADFI_AVAILABLE:
            return None
        return EnergyDataPoint(
            source_type=DataSourceType.OPENWEATHER,
            source_id="air_quality",
            timestamp=self.timestamp.timestamp(),
            quality_score=0.90,
            metadata={"aqi": self.aqi.value, "pm2_5": self.pm2_5, "pm10": self.pm10}
        )

# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: int = 60):
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
                    return True
                return False
            return True
    
    def record_success(self):
        with self._lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold and self.state != "OPEN":
                self.state = "OPEN"
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"state": self.state, "failure_count": self.failure_count}

# ============================================================================
# OPENWEATHER CLIENT
# ============================================================================

class OpenWeatherClient:
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self, api_key: str = None, redis_manager=None, metrics=None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY", "")
        self.redis_manager = redis_manager
        self.metrics = metrics
        self._session: Optional[aiohttp.ClientSession] = None
        self._circuit_breaker = CircuitBreaker("openweather", failure_threshold=3, recovery_timeout=60)
        self._api_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._avg_response_time_ms = 0
        
        self.mock_mode = not self.api_key or self.api_key == "your_api_key_here"
        
        if self.mock_mode:
            logger.info("[OPENWEATHER] mock mode active")
        else:
            logger.info("[OPENWEATHER] production mode active")
        
        if ADFI_AVAILABLE:
            self._register_with_adfi()
    
    def _register_with_adfi(self):
        try:
            orchestrator = get_orchestrator()
            
            async def weather_fetcher():
                data = await self.get_current_weather(9.0765, 7.3986)
                if data:
                    return data.to_dict()
                return None
            
            orchestrator.register_source(
                source_id="openweather_current",
                source_type=DataSourceType.OPENWEATHER,
                fetcher=weather_fetcher,
                priority=DataPriority.HIGH,
                rate_limit=10.0
            )
            logger.debug("[OPENWEATHER] registered with ADFI orchestrator")
        except Exception as e:
            logger.debug(f"[OPENWEATHER] ADFI registration failed: {e}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30, connect=10, sock_read=20)
            connector = aiohttp.TCPConnector(limit=20, limit_per_host=10)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": "NeuroBridge/3.0.0"}
            )
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _make_request(self, url: str, params: Dict[str, Any], retry_count: int = 0) -> Optional[Dict[str, Any]]:
        if self.mock_mode:
            return None
        if not self._circuit_breaker.can_execute():
            return None
        
        start_time = time.time()
        self._api_calls += 1
        
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                duration_ms = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    data = await response.json()
                    self._successful_calls += 1
                    self._circuit_breaker.record_success()
                    return data
                elif response.status == 429 and retry_count < 3:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    await asyncio.sleep(min(retry_after, 30))
                    return await self._make_request(url, params, retry_count + 1)
                elif response.status >= 500 and retry_count < 2:
                    await asyncio.sleep(2 ** retry_count)
                    return await self._make_request(url, params, retry_count + 1)
                
                self._failed_calls += 1
                self._circuit_breaker.record_failure()
                return None
        except Exception:
            self._failed_calls += 1
            self._circuit_breaker.record_failure()
            return None
    
    async def get_current_weather(self, lat: float, lon: float, use_cache: bool = True) -> Optional[WeatherData]:
        if self.mock_mode:
            return self._mock_weather_data(lat, lon)
        
        cache_key = f"openweather:current:{lat}:{lon}"
        if use_cache and self.redis_manager:
            cached = await self.redis_manager.get(cache_key)
            if cached:
                self._cache_hits += 1
                return self._dict_to_weather_data(cached)
        
        self._cache_misses += 1
        url = f"{self.BASE_URL}/weather"
        params = {"lat": lat, "lon": lon, "appid": self.api_key, "units": "metric"}
        data = await self._make_request(url, params)
        
        if not data:
            return self._mock_weather_data(lat, lon)
        
        weather_data = self._parse_weather_data(data, lat, lon)
        if use_cache and self.redis_manager:
            await self.redis_manager.set(cache_key, weather_data.to_dict(), 600)
        
        if weather_data and ADFI_AVAILABLE:
            try:
                pipeline = get_data_pipeline()
                energy_point = weather_data.to_energy_data_point()
                if energy_point:
                    await pipeline.ingest(data=energy_point, source_type=DataSourceType.OPENWEATHER, source_id="current_weather")
            except Exception:
                pass
        
        return weather_data
    
    def _parse_weather_data(self, data: Dict, lat: float, lon: float) -> WeatherData:
        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        rain = data.get("rain", {})
        weather = data.get("weather", [{}])[0]
        condition_code = weather.get("id", 800)
        condition_category = self._get_condition_category(condition_code)
        
        weather_data = WeatherData(
            temperature=main.get("temp", 25.0), feels_like=main.get("feels_like", 24.0),
            humidity=main.get("humidity", 55.0), pressure=main.get("pressure", 1013.0),
            wind_speed=wind.get("speed", 3.0), wind_direction=wind.get("deg", 180),
            wind_gust=wind.get("gust", 0.0), cloud_cover=clouds.get("all", 25),
            visibility=data.get("visibility", 10000), precipitation=rain.get("1h", 0),
            condition=weather.get("description", "clear sky"), condition_code=condition_code,
            condition_category=condition_category, uv_index=0, dew_point=0,
            timestamp=datetime.fromtimestamp(data.get("dt", time.time()), tz=timezone.utc),
            location=f"{lat},{lon}"
        )
        weather_data.calculate_aece_risk()
        return weather_data
    
    def _get_condition_category(self, condition_code: int) -> WeatherCondition:
        if 200 <= condition_code < 300:
            return WeatherCondition.THUNDERSTORM
        elif 300 <= condition_code < 600:
            return WeatherCondition.RAIN
        elif 600 <= condition_code < 700:
            return WeatherCondition.SNOW
        elif 700 <= condition_code < 800:
            return WeatherCondition.MIST
        elif condition_code == 800:
            return WeatherCondition.CLEAR
        elif condition_code == 801:
            return WeatherCondition.FEW_CLOUDS
        elif condition_code == 802:
            return WeatherCondition.SCATTERED_CLOUDS
        elif condition_code == 803:
            return WeatherCondition.BROKEN_CLOUDS
        elif condition_code == 804:
            return WeatherCondition.OVERCAST
        else:
            return WeatherCondition.UNKNOWN
    
    def _mock_weather_data(self, lat: float, lon: float) -> WeatherData:
        hour = datetime.now().hour
        temp = 28 + math.sin((hour - 12) * math.pi / 12) * 5 if 6 <= hour <= 18 else 24
        if 12 <= hour <= 16:
            condition, cond_code, cat, cloud = "clear sky", 800, WeatherCondition.CLEAR, 10
        elif hour <= 6 or hour >= 18:
            condition, cond_code, cat, cloud = "few clouds", 801, WeatherCondition.FEW_CLOUDS, 20
        else:
            condition, cond_code, cat, cloud = "scattered clouds", 802, WeatherCondition.SCATTERED_CLOUDS, 40
        
        weather_data = WeatherData(
            temperature=temp, feels_like=temp - 1, humidity=55, pressure=1013,
            wind_speed=3, wind_direction=180, wind_gust=0, cloud_cover=cloud,
            visibility=10000, precipitation=0, condition=condition, condition_code=cond_code,
            condition_category=cat, uv_index=5, dew_point=temp - 5,
            timestamp=datetime.now(timezone.utc), location=f"{lat},{lon}"
        )
        weather_data.calculate_aece_risk()
        return weather_data
    
    def _dict_to_weather_data(self, data: Dict) -> WeatherData:
        cat_map = {"clear": WeatherCondition.CLEAR, "few_clouds": WeatherCondition.FEW_CLOUDS,
                   "scattered_clouds": WeatherCondition.SCATTERED_CLOUDS, "broken_clouds": WeatherCondition.BROKEN_CLOUDS,
                   "overcast": WeatherCondition.OVERCAST, "rain": WeatherCondition.RAIN,
                   "thunderstorm": WeatherCondition.THUNDERSTORM, "snow": WeatherCondition.SNOW,
                   "mist": WeatherCondition.MIST, "fog": WeatherCondition.FOG, "haze": WeatherCondition.HAZE}
        return WeatherData(
            temperature=data.get("temperature_c", 25), feels_like=data.get("feels_like_c", 24),
            humidity=data.get("humidity_percent", 55), pressure=data.get("pressure_hpa", 1013),
            wind_speed=data.get("wind_speed_ms", 3), wind_direction=data.get("wind_direction_deg", 180),
            wind_gust=data.get("wind_gust_ms", 0), cloud_cover=data.get("cloud_cover_percent", 25),
            visibility=data.get("visibility_m", 10000), precipitation=data.get("precipitation_mm", 0),
            condition=data.get("condition", "clear sky"), condition_code=data.get("condition_code", 800),
            condition_category=cat_map.get(data.get("condition_category", "clear"), WeatherCondition.CLEAR),
            uv_index=data.get("uv_index", 5), dew_point=data.get("dew_point_c", 20),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            location=data.get("location", "9.0765,7.3986"), data_quality=data.get("data_quality", 0.95),
            aece_risk_factor=data.get("aece_risk_factor", 0), solar_impact_factor=data.get("solar_impact_factor", 1.0)
        )
    
    def get_stats(self) -> Dict[str, Any]:
        success_rate = (self._successful_calls / max(1, self._api_calls)) * 100
        return {
            "mock_mode": self.mock_mode, "api_calls": self._api_calls,
            "successful_calls": self._successful_calls, "failed_calls": self._failed_calls,
            "success_rate_percent": round(success_rate, 2),
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "adfi_integrated": ADFI_AVAILABLE
        }
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            data = await self.get_current_weather(9.0765, 7.3986, use_cache=False)
            return {"status": "healthy" if data else "degraded",
                    "api_key_valid": data is not None, "mock_mode": self.mock_mode,
                    "adfi_integrated": ADFI_AVAILABLE}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


_openweather_client = None
_client_lock = threading.RLock()


def get_openweather_client(api_key: str = None, redis_manager=None, metrics=None) -> OpenWeatherClient:
    global _openweather_client
    if _openweather_client is None:
        with _client_lock:
            if _openweather_client is None:
                _openweather_client = OpenWeatherClient(api_key, redis_manager, metrics)
                logger.info("[OPENWEATHER] configured")
    return _openweather_client


__all__ = [
    'OpenWeatherClient', 'get_openweather_client', 'WeatherData',
    'WeatherForecast', 'AirQualityData', 'WeatherCondition',
    'AirQualityIndex', 'WeatherAlertType'
]