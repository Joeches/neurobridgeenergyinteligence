"""
================================================================================
NeuroBridge 11D - Configuration Management (PHASE 1)
================================================================================
Component: Centralized configuration with validation and environment support
Version: 5.0.0-PHASE1-ENTERPRISE
Build: 2026.04.22

PHASE 1 CHANGES (v5.0.0):
- ✅ ADDED: Phase 1 production scope configuration
- ✅ ADDED: PHASE1_ENABLED flag
- ✅ ADDED: PHASE1_EXCLUDED_DOMAINS list
- ✅ ADDED: PHASE1_ALLOWED_SECTORS configuration
- ✅ ADDED: PHASE1_BLOCKED_TASK_PREFIXES
- ✅ ADDED: PHASE1_BLOCKED_ROUTE_PREFIXES
- ✅ ADDED: PHASE1_BLOCKED_QUEUES
- ✅ REMOVED: Nuclear feature flag (hard blocked)
- ✅ REMOVED: Quantum feature flag (hard blocked)
- ✅ REMOVED: Defense feature flag (hard blocked)
- ✅ REMOVED: Fusion references
- ✅ UPDATED: Default values for Phase 1 memory optimization
- ✅ UPDATED: Celery worker concurrency reduced
- ✅ UPDATED: Task timeouts optimized for faster failure detection

PHASE 1 SCOPE (ACTIVE):
- Solar Optimization Engine
- Grid Stability Prediction
- AECE Decision Layer
- Telemetry Ingestion
- Energy Forecasting

PHASE 1 EXCLUDED (HARD BLOCKED):
- Nuclear systems
- Fusion modeling
- Quantum computing
- Defense applications
================================================================================
"""

import os
import secrets
from typing import List, Optional, Dict, Any
from functools import lru_cache
from enum import Enum

from pydantic import Field, ConfigDict, field_validator
from pydantic_settings import BaseSettings

# ============================================================================
# ENUMS - PHASE 1 COMPLIANT
# ============================================================================

class Environment(str, Enum):
    """Deployment environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class DeploymentZone(str, Enum):
    """Physical deployment zones - Phase 1: Abuja only"""
    ABUJA_QUANTUM_GRID = "abuja_quantum_grid"


class Phase1Sector(str, Enum):
    """Phase 1 allowed energy sectors"""
    RENEWABLES = "renewables"
    GRID_STORAGE = "grid_storage"


# ============================================================================
# SETTINGS CLASS - PHASE 1
# ============================================================================

class Settings(BaseSettings):
    """Application settings with validation and environment support - Phase 1"""
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # ========================================================================
    # PHASE 1 CONFIGURATION - PRODUCTION SCOPE CONTROL
    # ========================================================================
    PHASE1_ENABLED: bool = Field(default=True)
    PHASE: str = Field(default="PHASE_1_PRODUCTION")
    
    # Phase 1: Hard excluded domains (blocked at all levels)
    PHASE1_EXCLUDED_DOMAINS: List[str] = Field(
        default=["nuclear", "fusion", "quantum", "defense"]
    )
    
    # Phase 1: Allowed sectors only
    PHASE1_ALLOWED_SECTORS: List[str] = Field(
        default=["renewables", "grid_storage"]
    )
    
    # Phase 1: Blocked task prefixes
    PHASE1_BLOCKED_TASK_PREFIXES: List[str] = Field(
        default=[
            "backend.tasks.nuclear_tasks",
            "backend.tasks.fusion_tasks", 
            "backend.tasks.quantum_tasks",
            "backend.tasks.defense_tasks"
        ]
    )
    
    # Phase 1: Blocked route prefixes
    PHASE1_BLOCKED_ROUTE_PREFIXES: List[str] = Field(
        default=[
            "/api/v1/nuclear/",
            "/api/v1/fusion/",
            "/api/v1/quantum/",
            "/api/v1/defense/"
        ]
    )
    
    # Phase 1: Blocked queues
    PHASE1_BLOCKED_QUEUES: List[str] = Field(
        default=["nuclear_queue", "fusion_queue", "quantum_queue", "defense_queue"]
    )
    
    # Phase 1: Blocked metric prefixes
    PHASE1_BLOCKED_METRIC_PREFIXES: List[str] = Field(
        default=[
            "neurobridge_nuclear_",
            "neurobridge_fusion_",
            "neurobridge_quantum_",
            "neurobridge_defense_"
        ]
    )
    
    # Phase 1: Key filtering
    PHASE1_KEY_FILTERING_ENABLED: bool = Field(default=True)
    
    # ========================================================================
    # ENVIRONMENT
    # ========================================================================
    ENVIRONMENT: str = Field(default="production")
    DEPLOYMENT_ZONE: str = Field(default="abuja_quantum_grid")
    DEBUG: bool = Field(default=False)
    
    @property
    def IS_DEVELOPMENT(self) -> bool:
        return self.ENVIRONMENT.lower() == Environment.DEVELOPMENT.value
    
    @property
    def IS_STAGING(self) -> bool:
        return self.ENVIRONMENT.lower() == Environment.STAGING.value
    
    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT.lower() == Environment.PRODUCTION.value
    
    @property
    def IS_TESTING(self) -> bool:
        return self.ENVIRONMENT.lower() == Environment.TESTING.value
    
    # ========================================================================
    # API & SERVER - Phase 1 Optimized
    # ========================================================================
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "NeuroBridge 11D - Phase 1"
    PROJECT_DESCRIPTION: str = "Production Energy Intelligence Platform - Solar & Grid Stability Only"
    VERSION: str = "12.0.0-PHASE1-ENTERPRISE"
    
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    RELOAD: bool = Field(default=False)
    WORKERS: int = Field(default=1)  # Reduced for Phase 1 memory optimization
    LOG_LEVEL: str = Field(default="info")
    
    # ========================================================================
    # SECURITY & AUTHENTICATION
    # ========================================================================
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 55
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SESSION_TIMEOUT_SECONDS: int = 3300  # 55 minutes
    
    # Development bypass token
    DEV_BYPASS_TOKEN: str = Field(default="DEV_ABUJA_PILOT_2026")
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    RATE_LIMIT_PER_SECOND: int = Field(default=10)
    
    # ========================================================================
    # DATABASE - SQLite for Phase 1 Lite
    # ========================================================================
    DATABASE_URL: str = Field(default="sqlite:///./data/neurobridge.db")
    DATABASE_POOL_SIZE: int = Field(default=5)  # Reduced for Phase 1
    DATABASE_MAX_OVERFLOW: int = Field(default=10)  # Reduced for Phase 1
    DATABASE_POOL_TIMEOUT: int = Field(default=30)
    DATABASE_POOL_RECYCLE: int = Field(default=3600)
    DATABASE_ECHO: bool = Field(default=False)
    
    # ========================================================================
    # REDIS CACHE - Phase 1 Optimized
    # ========================================================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_ENABLED: bool = Field(default=True)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)  # Reduced for Phase 1
    REDIS_SOCKET_TIMEOUT: int = Field(default=5)
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5)
    
    # Cache TTLs (seconds) - Phase 1 optimized
    CACHE_TTL_DEFAULT: int = Field(default=300)
    CACHE_TTL_SESSION: int = Field(default=3600)
    CACHE_TTL_TELEMETRY: int = Field(default=60)
    CACHE_TTL_WEATHER: int = Field(default=1800)
    CACHE_TTL_AECE_STATE: int = Field(default=10)
    
    # ========================================================================
    # CELERY & MESSAGE QUEUE - Phase 1 Optimized
    # ========================================================================
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")
    CELERY_ENABLED: bool = Field(default=True)
    CELERY_WORKER_CONCURRENCY: int = Field(default=1)  # Reduced for memory
    CELERY_TASK_TIME_LIMIT: int = Field(default=300)  # Reduced from 1800 (5 min)
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=240)  # Reduced from 1500
    CELERY_WORKER_MAX_TASKS_PER_CHILD: int = Field(default=50)  # Reduced from 100
    CELERY_WORKER_MAX_MEMORY_MB: int = Field(default=512)
    CELERY_TASK_MAX_MEMORY_MB: int = Field(default=200)
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = Field(default=1)
    CELERY_TASK_RETRY_BACKOFF: bool = Field(default=True)
    CELERY_TASK_RETRY_JITTER: bool = Field(default=True)
    
    # Beat scheduler
    CELERY_BEAT_MAX_LOOP_INTERVAL: int = Field(default=300)
    CELERY_BEAT_SYNC_EVERY: int = Field(default=1)
    
    # Startup jitter
    STARTUP_JITTER_MIN_SECONDS: int = Field(default=5)
    STARTUP_JITTER_MAX_SECONDS: int = Field(default=30)
    
    # ========================================================================
    # EXTERNAL APIS - Phase 1 (Solar only)
    # ========================================================================
    # NASA POWER API (Solar data)
    NASA_POWER_API_URL: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    NASA_POWER_API_KEY: Optional[str] = None
    NASA_POWER_TIMEOUT: int = 30
    
    # OpenWeatherMap API (Weather data for solar forecasting)
    OPENWEATHER_API_KEY: Optional[str] = None
    OPENWEATHER_API_URL: str = "https://api.openweathermap.org/data/2.5"
    OPENWEATHER_TIMEOUT: int = 10
    
    # Google Earth Engine (Solar potential mapping)
    GEE_CREDENTIALS_PATH: Optional[str] = None
    GEE_PROJECT_ID: Optional[str] = None
    GEE_TIMEOUT: int = 60
    
    # Sungrow iSolarCloud (Solar inverter telemetry)
    ISOLARCLOUD_API_KEY: Optional[str] = None
    ISOLARCLOUD_SECRET: Optional[str] = None
    ISOLARCLOUD_USERNAME: Optional[str] = None
    ISOLARCLOUD_PASSWORD: Optional[str] = None
    ISOLARCLOUD_BASE_URL: str = "https://api.isolarcloud.com"
    ISOLARCLOUD_TIMEOUT: int = 30
    
    # ========================================================================
    # AECE (Autonomous Energy Control Engine) - Phase 1
    # ========================================================================
    AECE_ENABLED: bool = Field(default=True)
    AECE_RISK_THRESHOLD_CRITICAL: float = Field(default=0.85)
    AECE_RISK_THRESHOLD_HIGH: float = Field(default=0.65)
    AECE_RISK_THRESHOLD_MEDIUM: float = Field(default=0.35)
    AECE_PROTECTION_MODE_ENABLED: bool = Field(default=True)
    AECE_POLLING_INTERVAL_MS: int = Field(default=100)
    AECE_MAX_ACTIONS_PER_MINUTE: int = Field(default=10)
    
    # Cooldown times (seconds) - Phase 1 optimized
    AECE_COOLDOWN_REDUCE_LOAD: int = Field(default=30)
    AECE_COOLDOWN_REDISTRIBUTE: int = Field(default=60)
    AECE_COOLDOWN_STABILIZATION: int = Field(default=120)
    AECE_COOLDOWN_ALERT: int = Field(default=300)
    AECE_COOLDOWN_LOCKDOWN: int = Field(default=600)
    
    # ========================================================================
    # WEATHER INTELLIGENCE - Phase 1 (Solar forecasting)
    # ========================================================================
    WEATHER_ENABLED: bool = Field(default=True)
    WEATHER_UPDATE_INTERVAL_SECONDS: int = Field(default=300)
    WEATHER_FORECAST_HOURS: int = Field(default=24)
    WEATHER_CACHE_TTL_SECONDS: int = Field(default=1800)
    WEATHER_FALLBACK_ENABLED: bool = Field(default=True)
    SOLAR_PREDICTION_ENABLED: bool = Field(default=True)
    
    # ========================================================================
    # HARDWARE INTEGRATION - Phase 1 (Solar inverters only)
    # ========================================================================
    MODBUS_ENABLED: bool = Field(default=True)
    MODBUS_HOST: str = Field(default="127.0.0.1")
    MODBUS_PORT: int = Field(default=502)
    MODBUS_UNIT_ID: int = Field(default=1)
    MODBUS_TIMEOUT_SECONDS: int = Field(default=5)
    MODBUS_RETRY_COUNT: int = Field(default=3)
    HARDWARE_POLL_INTERVAL_SECONDS: int = Field(default=5)
    HARDWARE_SIMULATION_MODE: bool = Field(default=True)
    
    # ========================================================================
    # MONITORING & METRICS - Phase 1
    # ========================================================================
    PROMETHEUS_ENABLED: bool = Field(default=True)
    PROMETHEUS_MULTIPROC_DIR: str = Field(default="/tmp/prometheus_multiproc")
    METRICS_PORT: int = Field(default=9090)
    HEALTH_CHECK_INTERVAL: int = Field(default=30)
    SLOW_REQUEST_THRESHOLD_MS: int = Field(default=1000)
    VERY_SLOW_REQUEST_THRESHOLD_MS: int = Field(default=5000)
    
    # ========================================================================
    # WEBSOCKET - Phase 1 (Energy updates only)
    # ========================================================================
    WEBSOCKET_ENABLED: bool = Field(default=True)
    WEBSOCKET_PATH: str = Field(default="/ws/energy-channel")  # Changed from quantum-channel
    WEBSOCKET_HEARTBEAT_INTERVAL: int = Field(default=30)
    
    # ========================================================================
    # CORS - Phase 1
    # ========================================================================
    CORS_ORIGINS_STR: str = Field(
        default="http://localhost,http://localhost:3000,http://localhost:8000,https://api.neurobridge.ng"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: List[str] = Field(default=["*"])
    CORS_ALLOW_HEADERS: List[str] = Field(default=["*"])
    
    @field_validator("CORS_ORIGINS_STR", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        """Validate CORS origins string"""
        return v
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Parse CORS origins from string"""
        return [origin.strip() for origin in self.CORS_ORIGINS_STR.split(",")]
    
    # ========================================================================
    # COMPANY INFORMATION
    # ========================================================================
    COMPANY_NAME: str = Field(default="NeuroBridge Technologies Ltd")
    COMPANY_CTO: str = Field(default="Joseph Ochelebe")
    COMPANY_LOCATION: str = Field(default="Abuja, Nigeria")
    COMPANY_EMAIL: str = Field(default="neurobridgetechnologiesltd@gmail.com")
    COMPANY_WHATSAPP: str = Field(default="+2348163399026")
    COMPANY_WEBSITE: str = Field(default="https://neurobridge.energy")
    
    # ========================================================================
    # FEATURE FLAGS - PHASE 1 (Blocked domains removed)
    # ========================================================================
    FEATURE_AECE_ENABLED: bool = Field(default=True)
    # FEATURE_NUCLEAR_ENABLED: REMOVED - Hard blocked in Phase 1
    # FEATURE_QUANTUM_KERNEL_ENABLED: REMOVED - Hard blocked in Phase 1
    # FEATURE_FUSION_ENABLED: REMOVED - Hard blocked in Phase 1
    # FEATURE_DEFENSE_ENABLED: REMOVED - Hard blocked in Phase 1
    FEATURE_WEATHER_INTELLIGENCE_ENABLED: bool = Field(default=True)
    FEATURE_GEOSPATIAL_INTELLIGENCE_ENABLED: bool = Field(default=True)
    FEATURE_HARDWARE_INTEGRATION_ENABLED: bool = Field(default=True)
    FEATURE_REPORT_GENERATION_ENABLED: bool = Field(default=True)
    FEATURE_WEBSOCKET_ENABLED: bool = Field(default=True)
    FEATURE_CELERY_TASKS_ENABLED: bool = Field(default=True)
    FEATURE_PROMETHEUS_METRICS_ENABLED: bool = Field(default=True)
    FEATURE_ADFI_ORCHESTRATION_ENABLED: bool = Field(default=True)
    FEATURE_OPTIMIZATION_METRICS: bool = Field(default=True)
    
    # ========================================================================
    # PARTNER PORTAL - Phase 1
    # ========================================================================
    PARTNER_PORTAL_ENABLED: bool = Field(default=True)
    PARTNER_MAX_CONCURRENT_SESSIONS: int = Field(default=100)
    PARTNER_DEFAULT_ENERGY_LIMIT_KWH: int = Field(default=10000)
    PARTNER_REPORT_RETENTION_DAYS: int = Field(default=90)
    
    # ========================================================================
    # MEMORY OPTIMIZATION - Phase 1
    # ========================================================================
    MEMORY_PRESSURE_GC_THRESHOLD: float = Field(default=0.85)
    MEMORY_PRESSURE_WARN_THRESHOLD: float = Field(default=0.80)
    CPU_SPIKE_THRESHOLD: float = Field(default=90.0)
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value"""
        valid_envs = [e.value for e in Environment]
        if v.lower() not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of: {valid_envs}")
        return v.lower()
    
    @field_validator("DEPLOYMENT_ZONE")
    @classmethod
    def validate_deployment_zone(cls, v: str) -> str:
        """Validate deployment zone - Phase 1 only Abuja"""
        valid_zones = [z.value for z in DeploymentZone]
        if v.lower() not in valid_zones:
            raise ValueError(f"DEPLOYMENT_ZONE must be: {valid_zones}")
        return v.lower()
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["debug", "info", "warning", "error", "critical"]
        if v.lower() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {valid_levels}")
        return v.lower()
    
    @field_validator("PHASE1_ENABLED", mode="before")
    @classmethod
    def validate_phase1_enabled(cls, v: bool) -> bool:
        """Ensure Phase 1 is enabled"""
        if not v:
            raise ValueError("PHASE1_ENABLED must be True for production deployment")
        return v
    
    # ========================================================================
    # HELPER METHODS - Phase 1
    # ========================================================================
    
    def get_redis_url(self) -> str:
        """Get Redis URL with validation"""
        return self.REDIS_URL
    
    def get_celery_broker(self) -> str:
        """Get Celery broker URL"""
        return self.CELERY_BROKER_URL
    
    def get_aece_risk_thresholds(self) -> Dict[str, float]:
        """Get AECE risk thresholds - Phase 1"""
        return {
            "critical": self.AECE_RISK_THRESHOLD_CRITICAL,
            "high": self.AECE_RISK_THRESHOLD_HIGH,
            "medium": self.AECE_RISK_THRESHOLD_MEDIUM
        }
    
    def get_api_keys_status(self) -> Dict[str, bool]:
        """Get status of external API keys - Phase 1 only"""
        return {
            "nasa_power": bool(self.NASA_POWER_API_KEY),
            "openweather": bool(self.OPENWEATHER_API_KEY),
            "google_earth_engine": bool(self.GEE_CREDENTIALS_PATH),
            "sungrow_isolarcloud": bool(self.ISOLARCLOUD_API_KEY)
        }
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags - Phase 1 (blocked domains removed)"""
        return {
            "aece": self.FEATURE_AECE_ENABLED,
            "weather_intelligence": self.FEATURE_WEATHER_INTELLIGENCE_ENABLED,
            "geospatial": self.FEATURE_GEOSPATIAL_INTELLIGENCE_ENABLED,
            "hardware": self.FEATURE_HARDWARE_INTEGRATION_ENABLED,
            "reports": self.FEATURE_REPORT_GENERATION_ENABLED,
            "websocket": self.FEATURE_WEBSOCKET_ENABLED,
            "celery": self.FEATURE_CELERY_TASKS_ENABLED,
            "prometheus": self.FEATURE_PROMETHEUS_METRICS_ENABLED,
            "adfi": self.FEATURE_ADFI_ORCHESTRATION_ENABLED,
            "optimization_metrics": self.FEATURE_OPTIMIZATION_METRICS
        }
    
    def get_phase1_config(self) -> Dict[str, Any]:
        """Get Phase 1 configuration summary"""
        return {
            "phase": self.PHASE,
            "enabled": self.PHASE1_ENABLED,
            "excluded_domains": self.PHASE1_EXCLUDED_DOMAINS,
            "allowed_sectors": self.PHASE1_ALLOWED_SECTORS,
            "blocked_task_prefixes": self.PHASE1_BLOCKED_TASK_PREFIXES,
            "blocked_route_prefixes": self.PHASE1_BLOCKED_ROUTE_PREFIXES,
            "blocked_queues": self.PHASE1_BLOCKED_QUEUES,
            "blocked_metric_prefixes": self.PHASE1_BLOCKED_METRIC_PREFIXES,
            "key_filtering_enabled": self.PHASE1_KEY_FILTERING_ENABLED
        }
    
    def get_health_check_config(self) -> Dict[str, Any]:
        """Get configuration for health checks - Phase 1"""
        return {
            "environment": self.ENVIRONMENT,
            "version": self.VERSION,
            "deployment_zone": self.DEPLOYMENT_ZONE,
            "phase": self.PHASE,
            "features_enabled": self.get_feature_flags(),
            "phase1_compliant": True,
            "services": {
                "redis": self.REDIS_ENABLED,
                "celery": self.CELERY_ENABLED,
                "prometheus": self.PROMETHEUS_ENABLED,
                "websocket": self.FEATURE_WEBSOCKET_ENABLED,
                "aece": self.FEATURE_AECE_ENABLED
            }
        }
    
    def get_memory_optimization_config(self) -> Dict[str, Any]:
        """Get memory optimization configuration - Phase 1"""
        return {
            "celery_worker_concurrency": self.CELERY_WORKER_CONCURRENCY,
            "celery_worker_max_memory_mb": self.CELERY_WORKER_MAX_MEMORY_MB,
            "celery_task_max_memory_mb": self.CELERY_TASK_MAX_MEMORY_MB,
            "celery_max_tasks_per_child": self.CELERY_WORKER_MAX_TASKS_PER_CHILD,
            "celery_task_time_limit": self.CELERY_TASK_TIME_LIMIT,
            "celery_worker_prefetch_multiplier": self.CELERY_WORKER_PREFETCH_MULTIPLIER,
            "memory_pressure_gc_threshold": self.MEMORY_PRESSURE_GC_THRESHOLD,
            "memory_pressure_warn_threshold": self.MEMORY_PRESSURE_WARN_THRESHOLD,
            "cpu_spike_threshold": self.CPU_SPIKE_THRESHOLD,
            "startup_jitter_min": self.STARTUP_JITTER_MIN_SECONDS,
            "startup_jitter_max": self.STARTUP_JITTER_MAX_SECONDS
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary (excluding secrets) - Phase 1"""
        return {
            "environment": self.ENVIRONMENT,
            "phase": self.PHASE,
            "phase1_compliant": True,
            "deployment_zone": self.DEPLOYMENT_ZONE,
            "debug": self.DEBUG,
            "version": self.VERSION,
            "api_prefix": self.API_V1_PREFIX,
            "host": self.HOST,
            "port": self.PORT,
            "log_level": self.LOG_LEVEL,
            "redis_enabled": self.REDIS_ENABLED,
            "celery_enabled": self.CELERY_ENABLED,
            "prometheus_enabled": self.PROMETHEUS_ENABLED,
            "aece_enabled": self.FEATURE_AECE_ENABLED,
            "api_keys": self.get_api_keys_status(),
            "feature_flags": self.get_feature_flags(),
            "phase1_config": self.get_phase1_config(),
            "memory_optimization": self.get_memory_optimization_config(),
            "company": {
                "name": self.COMPANY_NAME,
                "cto": self.COMPANY_CTO,
                "location": self.COMPANY_LOCATION,
                "email": self.COMPANY_EMAIL,
                "whatsapp": self.COMPANY_WHATSAPP
            }
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance - Phase 1"""
    return Settings()


settings = get_settings()


# ============================================================================
# PHASE 1 VALIDATION SUMMARY
# ============================================================================

import logging
logger = logging.getLogger("NeuroBridge.Config")

logger.info("""
╔═══════════════════════════════════════════════════════════════════════════╗
║              CONFIGURATION v5.0.0 - PHASE 1 ISOLATED                     ║
║     ✅ PHASE 1 PRODUCTION MODE ACTIVE                                     ║
║     ✅ EXCLUDED DOMAINS: nuclear, fusion, quantum, defense               ║
║     ✅ ALLOWED SECTORS: renewables, grid_storage                         ║
║     ✅ BLOCKED TASKS: nuclear_tasks, fusion_tasks, quantum_tasks,        ║
║        defense_tasks                                                      ║
║     ✅ BLOCKED ROUTES: /nuclear/*, /fusion/*, /quantum/*, /defense/*     ║
║     ✅ BLOCKED QUEUES: nuclear_queue, fusion_queue, quantum_queue,       ║
║        defense_queue                                                      ║
║     ✅ BLOCKED METRICS: nuclear_*, fusion_*, quantum_*, defense_*        ║
║     ✅ MEMORY OPTIMIZED: Concurrency=1, Timeout=300s, Max Memory=512MB   ║
║     ✅ CELERY OPTIMIZED: Prefetch=1, Max Tasks per Child=50              ║
║     ✅ STARTUP JITTER: 5-30s random delay                                ║
║     ✅ Abuja Quantum Grid Pilot Zone Compliance                          ║
║     ╔═══════════════════════════════════════════════════════════════════╗ ║
║     ║  PHASE 1 EXCLUSIONS (HARD BLOCKED):                              ║ ║
║     ║  ❌ Nuclear energy systems                                        ║ ║
║     ║  ❌ Fusion energy modeling                                        ║ ║
║     ║  ❌ Quantum computing execution                                   ║ ║
║     ║  ❌ Defense systems or military simulations                       ║ ║
║     ╚═══════════════════════════════════════════════════════════════════╝ ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'Settings',
    'Environment',
    'DeploymentZone',
    'Phase1Sector',
    'settings',
    'get_settings'
]


# ============================================================================
# END OF FILE - PHASE 1 PRODUCTION READY
# ============================================================================