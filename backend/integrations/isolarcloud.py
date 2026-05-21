# backend/integrations/isolarcloud.py - PRODUCTION CLEAN v3.0.0
# ISolarCloud Integration - Solar Inverter Monitoring

import os
import asyncio
import logging
import hashlib
import hmac
import json
import time
import secrets
import math
import threading
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque

import aiohttp
from aiohttp import ClientTimeout, ClientError

logger = logging.getLogger(__name__)

# Single concise initialization log - NO BANNER
logger.info("[ISOLARCLOUD] client initializing")

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
    logger.debug("[ISOLARCLOUD] ADFI integration available")
except ImportError:
    ADFI_AVAILABLE = False
    logger.debug("[ISOLARCLOUD] ADFI not available - standalone mode")

# ============================================================================
# ENUMS
# ============================================================================

class InverterStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    FAULT = "fault"
    DERATING = "derating"
    MAINTENANCE = "maintenance"
    STANDBY = "standby"
    UNKNOWN = "unknown"


class InverterModel(str, Enum):
    SG125HX = "SG125HX"
    SG110HX = "SG110HX"
    SG100HX = "SG100HX"
    SG75HX = "SG75HX"
    SG50HX = "SG50HX"
    SG30HX = "SG30HX"
    SH5K = "SH5K"
    SH8K = "SH8K"
    SH10K = "SH10K"


class CommandType(str, Enum):
    POWER_LIMIT = "power_limit"
    START = "start"
    STOP = "stop"
    RESET = "reset"
    CLEAR_FAULT = "clear_fault"

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class SolarInverterData:
    inverter_id: str
    power_kw: float
    energy_today_kwh: float
    energy_total_kwh: float
    voltage_dc: float
    current_dc: float
    voltage_ac: float
    current_ac: float
    frequency_hz: float
    temperature_c: float
    efficiency: float
    status: InverterStatus
    timestamp: datetime
    data_quality: float = 0.95
    aece_risk_factor: float = 0.0
    model: Optional[InverterModel] = None
    location: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "inverter_id": self.inverter_id,
            "power_kw": round(self.power_kw, 2),
            "energy_today_kwh": round(self.energy_today_kwh, 2),
            "energy_total_kwh": round(self.energy_total_kwh, 2),
            "voltage_dc": round(self.voltage_dc, 1),
            "current_dc": round(self.current_dc, 2),
            "voltage_ac": round(self.voltage_ac, 1),
            "current_ac": round(self.current_ac, 2),
            "frequency_hz": round(self.frequency_hz, 2),
            "temperature_c": round(self.temperature_c, 1),
            "efficiency": round(self.efficiency, 3),
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "data_quality": round(self.data_quality, 2),
            "aece_risk_factor": round(self.aece_risk_factor, 3)
        }
    
    def to_energy_data_point(self) -> Optional['EnergyDataPoint']:
        if not ADFI_AVAILABLE:
            return None
        return EnergyDataPoint(
            source_type=DataSourceType.SUNGROW_ISOLARCLOUD,
            source_id=self.inverter_id,
            timestamp=self.timestamp.timestamp(),
            active_power_kw=self.power_kw,
            solar_output_kw=self.power_kw,
            grid_frequency_hz=self.frequency_hz,
            grid_voltage_v=self.voltage_ac,
            temperature_c=self.temperature_c,
            efficiency=self.efficiency,
            quality_score=self.data_quality,
            aece_risk_factor=self.aece_risk_factor
        )
    
    def calculate_aece_risk(self) -> float:
        risk = 0.0
        if self.temperature_c > 60:
            risk += 0.3
        elif self.temperature_c > 50:
            risk += 0.15
        if self.efficiency < 0.85:
            risk += 0.25
        elif self.efficiency < 0.90:
            risk += 0.1
        if self.frequency_hz < 49.5 or self.frequency_hz > 50.5:
            risk += 0.2
        if self.status == InverterStatus.FAULT:
            risk += 0.5
        elif self.status == InverterStatus.DERATING:
            risk += 0.2
        elif self.status == InverterStatus.OFFLINE:
            risk += 0.3
        self.aece_risk_factor = min(0.95, risk)
        return self.aece_risk_factor


@dataclass
class InverterFleetSummary:
    total_inverters: int
    online_count: int
    offline_count: int
    fault_count: int
    total_power_kw: float
    total_energy_today_kwh: float
    total_energy_total_kwh: float
    avg_efficiency: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_inverters": self.total_inverters,
            "online_count": self.online_count,
            "offline_count": self.offline_count,
            "fault_count": self.fault_count,
            "total_power_kw": round(self.total_power_kw, 2),
            "total_energy_today_kwh": round(self.total_energy_today_kwh, 2),
            "total_energy_total_kwh": round(self.total_energy_total_kwh, 2),
            "avg_efficiency": round(self.avg_efficiency, 3),
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_energy_data_point(self) -> Optional['EnergyDataPoint']:
        if not ADFI_AVAILABLE:
            return None
        return EnergyDataPoint(
            source_type=DataSourceType.SUNGROW_ISOLARCLOUD,
            source_id="fleet_aggregate",
            timestamp=self.timestamp.timestamp(),
            active_power_kw=self.total_power_kw,
            solar_output_kw=self.total_power_kw,
            quality_score=0.95
        )


@dataclass
class CommandResult:
    success: bool
    command_type: CommandType
    inverter_id: str
    value: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "command_type": self.command_type.value,
            "inverter_id": self.inverter_id,
            "value": self.value,
            "error": self.error,
            "timestamp": self.timestamp.isoformat()
        }

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
# ISOLARCLOUD CLIENT
# ============================================================================

class ISolarCloudClient:
    BASE_URL = "https://www.isolarcloud.com/api/v1"
    AUTH_ENDPOINT = "/auth/login"
    REFRESH_ENDPOINT = "/auth/refresh"
    INVERTER_LIST_ENDPOINT = "/inverters"
    REALTIME_ENDPOINT = "/inverters/{inverter_id}/realtime"
    HISTORY_ENDPOINT = "/inverters/{inverter_id}/history"
    POWER_LIMIT_ENDPOINT = "/inverters/{inverter_id}/power-limit"
    COMMAND_ENDPOINT = "/inverters/{inverter_id}/command"
    
    def __init__(self, username: str = None, password: str = None, api_key: str = None,
                 redis_manager=None, metrics=None):
        self.username = username or os.getenv("ISOLARCLOUD_USERNAME", "")
        self.password = password or os.getenv("ISOLARCLOUD_PASSWORD", "")
        self.api_key = api_key or os.getenv("ISOLARCLOUD_API_KEY", "")
        self.redis_manager = redis_manager
        self.metrics = metrics
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._circuit_breaker = CircuitBreaker("isolarcloud", failure_threshold=3, recovery_timeout=60)
        self._inverter_cache: Dict[str, SolarInverterData] = {}
        self._command_history: deque = deque(maxlen=100)
        self._api_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._avg_response_time_ms = 0
        
        self.mock_mode = not all([self.username, self.password, self.api_key])
        
        if self.mock_mode:
            logger.info("[ISOLARCLOUD] mock mode active")
        else:
            logger.info("[ISOLARCLOUD] production mode active")
        
        if ADFI_AVAILABLE:
            self._register_with_adfi()
    
    def _register_with_adfi(self):
        try:
            orchestrator = get_orchestrator()
            
            async def inverter_fetcher():
                inverters = await self.get_inverter_list()
                if inverters:
                    inverter_id = inverters[0].get("inverterId", "INV-001")
                    data = await self.get_realtime_data(inverter_id)
                    if data:
                        return data.to_dict()
                return self._mock_inverter_data("default").to_dict()
            
            orchestrator.register_source(
                source_id="isolarcloud_inverters",
                source_type=DataSourceType.SUNGROW_ISOLARCLOUD,
                fetcher=inverter_fetcher,
                priority=DataPriority.HIGH,
                rate_limit=10.0
            )
            logger.debug("[ISOLARCLOUD] registered with ADFI orchestrator")
        except Exception as e:
            logger.debug(f"[ISOLARCLOUD] ADFI registration failed: {e}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30, connect=10, sock_read=20)
            connector = aiohttp.TCPConnector(limit=20, limit_per_host=10)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": "NeuroBridge/3.0.0", "Accept": "application/json"}
            )
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _authenticate(self) -> bool:
        if self.mock_mode:
            self._token = "mock_token_" + secrets.token_hex(16)
            self._token_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
            return True
        
        if self._token and self._token_expiry and self._token_expiry > datetime.now(timezone.utc):
            return True
        
        if not self._circuit_breaker.can_execute():
            return False
        
        start_time = time.time()
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{self.AUTH_ENDPOINT}"
            payload = {"username": self.username, "password": self.password, "apiKey": self.api_key}
            
            async with session.post(url, json=payload) as response:
                duration_ms = (time.time() - start_time) * 1000
                self._api_calls += 1
                
                if response.status == 200:
                    data = await response.json()
                    self._token = data.get("token")
                    self._refresh_token = data.get("refreshToken")
                    expires_in = data.get("expiresIn", 7200)
                    self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    self._circuit_breaker.record_success()
                    self._successful_calls += 1
                    return True
                else:
                    self._circuit_breaker.record_failure()
                    self._failed_calls += 1
                    return False
        except Exception:
            self._circuit_breaker.record_failure()
            self._failed_calls += 1
            return False
    
    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                           data: Optional[Dict] = None, retry_count: int = 0) -> Optional[Dict]:
        if not await self._authenticate():
            return None
        if not self._circuit_breaker.can_execute():
            return None
        
        url = f"{self.BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self._token}"}
        start_time = time.time()
        self._api_calls += 1
        
        try:
            session = await self._get_session()
            async with session.request(method, url, params=params, json=data, headers=headers) as response:
                duration_ms = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    result = await response.json()
                    self._successful_calls += 1
                    self._circuit_breaker.record_success()
                    return result
                elif response.status == 401 and retry_count < 2:
                    if await self._refresh_token():
                        return await self._make_request(method, endpoint, params, data, retry_count + 1)
                elif response.status == 429 and retry_count < 3:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    await asyncio.sleep(retry_after)
                    return await self._make_request(method, endpoint, params, data, retry_count + 1)
                elif response.status >= 500 and retry_count < 2:
                    await asyncio.sleep(2 ** retry_count)
                    return await self._make_request(method, endpoint, params, data, retry_count + 1)
                
                self._failed_calls += 1
                self._circuit_breaker.record_failure()
                return None
        except Exception:
            self._failed_calls += 1
            self._circuit_breaker.record_failure()
            return None
    
    async def _refresh_token(self) -> bool:
        if not self._refresh_token:
            return await self._authenticate()
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{self.REFRESH_ENDPOINT}"
            payload = {"refreshToken": self._refresh_token}
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    self._token = data.get("token")
                    self._refresh_token = data.get("refreshToken")
                    expires_in = data.get("expiresIn", 7200)
                    self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    return True
                return await self._authenticate()
        except Exception:
            return await self._authenticate()
    
    async def get_inverter_list(self) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return self._mock_inverter_list()
        cache_key = "isolarcloud:inverters"
        if self.redis_manager:
            cached = await self.redis_manager.get(cache_key)
            if cached:
                self._cache_hits += 1
                return cached
        self._cache_misses += 1
        result = await self._make_request("GET", self.INVERTER_LIST_ENDPOINT)
        if result:
            inverters = result.get("inverters", [])
            if self.redis_manager:
                await self.redis_manager.set(cache_key, inverters, ttl=300)
            return inverters
        return []
    
    async def get_realtime_data(self, inverter_id: str) -> Optional[SolarInverterData]:
        if self.mock_mode:
            return self._mock_inverter_data(inverter_id)
        
        cache_key = f"isolarcloud:realtime:{inverter_id}"
        if self.redis_manager:
            cached = await self.redis_manager.get(cache_key)
            if cached:
                self._cache_hits += 1
                return self._dict_to_inverter_data(cached, inverter_id)
        
        self._cache_misses += 1
        endpoint = self.REALTIME_ENDPOINT.format(inverter_id=inverter_id)
        result = await self._make_request("GET", endpoint)
        
        if result:
            inverter_data = self._parse_inverter_data(result, inverter_id)
            if self.redis_manager:
                await self.redis_manager.set(cache_key, inverter_data.to_dict(), ttl=5)
            self._inverter_cache[inverter_id] = inverter_data
            
            if ADFI_AVAILABLE:
                try:
                    pipeline = get_data_pipeline()
                    energy_point = inverter_data.to_energy_data_point()
                    if energy_point:
                        await pipeline.ingest(
                            data=energy_point,
                            source_type=DataSourceType.SUNGROW_ISOLARCLOUD,
                            source_id=inverter_id
                        )
                except Exception:
                    pass
            return inverter_data
        return self._inverter_cache.get(inverter_id)
    
    async def set_power_limit(self, inverter_id: str, power_limit_percent: float,
                             reason: str = "autonomous_control") -> CommandResult:
        power_limit_percent = max(0, min(100, power_limit_percent))
        if self.mock_mode:
            result = CommandResult(success=True, command_type=CommandType.POWER_LIMIT,
                                   inverter_id=inverter_id, value=power_limit_percent)
            self._command_history.append(result)
            return result
        
        endpoint = self.POWER_LIMIT_ENDPOINT.format(inverter_id=inverter_id)
        data = {"powerLimit": power_limit_percent, "reason": reason}
        result = await self._make_request("POST", endpoint, data=data)
        
        if result and result.get("code") == 0:
            cmd_result = CommandResult(success=True, command_type=CommandType.POWER_LIMIT,
                                       inverter_id=inverter_id, value=power_limit_percent)
            self._command_history.append(cmd_result)
            return cmd_result
        
        error_msg = result.get("message", "API request failed") if result else "API request failed"
        cmd_result = CommandResult(success=False, command_type=CommandType.POWER_LIMIT,
                                   inverter_id=inverter_id, error=error_msg)
        self._command_history.append(cmd_result)
        return cmd_result
    
    async def get_fleet_summary(self) -> InverterFleetSummary:
        inverters = await self.get_inverter_list()
        if not inverters:
            return InverterFleetSummary(0, 0, 0, 0, 0, 0, 0, 0)
        
        total_power = 0
        total_energy_today = 0
        total_energy_total = 0
        total_efficiency = 0
        online_count = 0
        offline_count = 0
        fault_count = 0
        
        for inv in inverters:
            inv_id = inv.get("inverterId")
            if inv_id:
                data = await self.get_realtime_data(inv_id)
                if data:
                    total_power += data.power_kw
                    total_energy_today += data.energy_today_kwh
                    total_energy_total += data.energy_total_kwh
                    total_efficiency += data.efficiency
                    if data.status == InverterStatus.ONLINE:
                        online_count += 1
                    elif data.status == InverterStatus.OFFLINE:
                        offline_count += 1
                    elif data.status == InverterStatus.FAULT:
                        fault_count += 1
        
        avg_efficiency = total_efficiency / len(inverters) if inverters else 0
        return InverterFleetSummary(
            total_inverters=len(inverters), online_count=online_count,
            offline_count=offline_count, fault_count=fault_count,
            total_power_kw=total_power, total_energy_today_kwh=total_energy_today,
            total_energy_total_kwh=total_energy_total, avg_efficiency=avg_efficiency
        )
    
    def _parse_inverter_data(self, data: Dict, inverter_id: str) -> SolarInverterData:
        status_map = {"1": InverterStatus.ONLINE, "0": InverterStatus.OFFLINE,
                     "2": InverterStatus.FAULT, "3": InverterStatus.DERATING}
        status_code = str(data.get("status", "0"))
        inverter_data = SolarInverterData(
            inverter_id=inverter_id, power_kw=data.get("power", 0) / 1000,
            energy_today_kwh=data.get("energy_today", 0),
            energy_total_kwh=data.get("energy_total", 0),
            voltage_dc=data.get("pv_voltage", 0), current_dc=data.get("pv_current", 0),
            voltage_ac=data.get("grid_voltage", 0), current_ac=data.get("grid_current", 0),
            frequency_hz=data.get("grid_frequency", 50), temperature_c=data.get("temperature", 25),
            efficiency=data.get("efficiency", 0.95),
            status=status_map.get(status_code, InverterStatus.UNKNOWN),
            timestamp=datetime.now(timezone.utc)
        )
        inverter_data.calculate_aece_risk()
        return inverter_data
    
    def _dict_to_inverter_data(self, data: Dict, inverter_id: str) -> SolarInverterData:
        status_map = {"online": InverterStatus.ONLINE, "offline": InverterStatus.OFFLINE,
                     "fault": InverterStatus.FAULT, "derating": InverterStatus.DERATING}
        return SolarInverterData(
            inverter_id=inverter_id, power_kw=data.get("power_kw", 0),
            energy_today_kwh=data.get("energy_today_kwh", 0),
            energy_total_kwh=data.get("energy_total_kwh", 0),
            voltage_dc=data.get("voltage_dc", 0), current_dc=data.get("current_dc", 0),
            voltage_ac=data.get("voltage_ac", 0), current_ac=data.get("current_ac", 0),
            frequency_hz=data.get("frequency_hz", 50), temperature_c=data.get("temperature_c", 25),
            efficiency=data.get("efficiency", 0.95),
            status=status_map.get(data.get("status", "unknown"), InverterStatus.UNKNOWN),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            data_quality=data.get("data_quality", 0.95),
            aece_risk_factor=data.get("aece_risk_factor", 0)
        )
    
    def _mock_inverter_list(self) -> List[Dict[str, Any]]:
        return [{"inverterId": "INV-001", "model": "SG125HX", "location": "Site A", "status": "online"},
                {"inverterId": "INV-002", "model": "SG100HX", "location": "Site B", "status": "online"}]
    
    def _mock_inverter_data(self, inverter_id: str) -> SolarInverterData:
        hour = datetime.now().hour
        if 6 <= hour <= 18:
            solar_factor = math.sin(math.pi * (hour - 6) / 12)
            power = 50 + (solar_factor * 50)
        else:
            power = 2
        power = max(0, min(150, power))
        return SolarInverterData(
            inverter_id=inverter_id, power_kw=power, energy_today_kwh=45.2,
            energy_total_kwh=1250.5, voltage_dc=400, current_dc=power * 1000 / 400,
            voltage_ac=230, current_ac=power * 1000 / 230, frequency_hz=50.0,
            temperature_c=45, efficiency=0.94, status=InverterStatus.ONLINE,
            timestamp=datetime.now(timezone.utc)
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
            auth_success = await self._authenticate()
            inverters = await self.get_inverter_list()
            return {"status": "healthy" if auth_success else "degraded",
                    "authenticated": auth_success, "inverters_accessible": len(inverters) > 0,
                    "mock_mode": self.mock_mode, "adfi_integrated": ADFI_AVAILABLE}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


_isolarcloud_client = None
_client_lock = threading.RLock()


def get_isolarcloud_client(redis_manager=None, metrics=None) -> ISolarCloudClient:
    global _isolarcloud_client
    if _isolarcloud_client is None:
        with _client_lock:
            if _isolarcloud_client is None:
                _isolarcloud_client = ISolarCloudClient(redis_manager=redis_manager, metrics=metrics)
                logger.info("[ISOLARCLOUD] configured")
    return _isolarcloud_client


__all__ = [
    'ISolarCloudClient', 'get_isolarcloud_client', 'SolarInverterData',
    'InverterFleetSummary', 'InverterStatus', 'InverterModel', 'CommandType', 'CommandResult'
]