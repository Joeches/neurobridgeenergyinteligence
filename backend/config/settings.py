"""
================================================================================
Project: NeuroBridge 11D Energy Intelligence Kernel
Component: Centralized Configuration Management (11D-CONFIG) v4.0.0
Version: 4.0.0-QUANTUM-UNIFIED
Author: NeuroBridge Quantum Engineering Team
Copyright: NeuroBridge Energy Systems - Sovereign Grid Deployment
================================================================================

This module provides centralized configuration management with:
- Environment-aware configuration loading
- Validation and type conversion
- Feature flags for progressive rollout
- Service-specific configuration sections
- AECE autonomous control parameters
- API client configurations
- Redis cache settings
- Prometheus metrics configuration
- Multi-tenancy partner settings
- Pilot program specific overrides

Usage:
    from backend.config.settings import settings
    
    # Access configuration
    redis_url = settings.REDIS_URL
    aece_risk_threshold = settings.AECE_RISK_THRESHOLD_CRITICAL
    
    # Check feature flags
    if settings.FEATURE_AECE_ENABLED:
        enable_autonomous_control()
================================================================================
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from dotenv import load_dotenv

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger("NeuroBridge.Config")

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

class Environment(str, Enum):
    """Deployment environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class DeploymentZone(str, Enum):
    """Physical deployment zones"""
    ABUJA_QUANTUM_GRID = "abuja_quantum_grid"
    LAGOS_PILOT = "lagos_pilot"
    KANO_NORTHERN_HUB = "kano_northern_hub"
    PORT_HARCOURT_SOUTH = "port_harcourt_south"


# ============================================================================
# CONFIGURATION DATA CLASSES
# ============================================================================

@dataclass
class ServerConfig:
    """Server configuration settings"""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 4
    log_level: str = "info"
    timeout_keep_alive: int = 65
    limit_concurrency: int = 1000
    max_requests: int = 10000
    max_requests_jitter: int = 1000
    graceful_timeout: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "reload": self.reload,
            "workers": self.workers,
            "log_level": self.log_level,
            "timeout_keep_alive": self.timeout_keep_alive,
            "limit_concurrency": self.limit_concurrency,
            "max_requests": self.max_requests,
            "max_requests_jitter": self.max_requests_jitter,
            "graceful_timeout": self.graceful_timeout
        }


@dataclass
class SecurityConfig:
    """Security and authentication settings"""
    cto_access_code: str = ""
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 55
    jwt_refresh_expiry_days: int = 7
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    rate_limit_per_minute: int = 60
    rate_limit_per_second: int = 10
    max_token_length: int = 128
    session_timeout_seconds: int = 3300  # 55 minutes
    encryption_key_rotation_days: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cto_access_code_masked": self.cto_access_code[:12] + "..." if self.cto_access_code else None,
            "jwt_algorithm": self.jwt_algorithm,
            "jwt_expiry_minutes": self.jwt_expiry_minutes,
            "allowed_origins": self.allowed_origins,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "session_timeout_seconds": self.session_timeout_seconds
        }


@dataclass
class DatabaseConfig:
    """Database configuration"""
    url: str = "sqlite:///./neurobridge.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url.split("://")[0] if "://" in self.url else self.url,
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout
        }


@dataclass
class RedisConfig:
    """Redis cache configuration"""
    url: str = "redis://localhost:6379/0"
    enabled: bool = True
    ttl_default_seconds: int = 300
    ttl_session_seconds: int = 3600
    ttl_telemetry_seconds: int = 60
    ttl_weather_seconds: int = 1800
    ttl_aece_state_seconds: int = 10
    max_connections: int = 50
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    retry_on_timeout: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url.split("@")[-1] if "@" in self.url else self.url,
            "enabled": self.enabled,
            "ttl_default_seconds": self.ttl_default_seconds,
            "max_connections": self.max_connections
        }


@dataclass
class AECEConfig:
    """Autonomous Energy Control Engine configuration"""
    enabled: bool = True
    risk_threshold_critical: float = 0.8
    risk_threshold_high: float = 0.6
    risk_threshold_medium: float = 0.3
    cooldown_seconds_reduce_load: int = 30
    cooldown_seconds_redistribute: int = 60
    cooldown_seconds_stabilization: int = 120
    cooldown_seconds_alert: int = 300
    cooldown_seconds_lockdown: int = 600
    max_actions_per_minute: int = 10
    polling_interval_ms: int = 100
    protection_mode_enabled: bool = True
    adaptive_thresholds: bool = True
    ml_prediction_enabled: bool = True
    weather_integration: bool = True
    hardware_integration: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "risk_threshold_critical": self.risk_threshold_critical,
            "risk_threshold_high": self.risk_threshold_high,
            "risk_threshold_medium": self.risk_threshold_medium,
            "cooldown_seconds_reduce_load": self.cooldown_seconds_reduce_load,
            "max_actions_per_minute": self.max_actions_per_minute,
            "protection_mode_enabled": self.protection_mode_enabled,
            "ml_prediction_enabled": self.ml_prediction_enabled
        }


@dataclass
class APIConfig:
    """External API configuration"""
    # NASA POWER API
    nasa_power_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    nasa_power_api_key: str = ""
    nasa_power_timeout: int = 30
    
    # OpenWeather API
    openweather_url: str = "https://api.openweathermap.org/data/2.5"
    openweather_api_key: str = ""
    openweather_timeout: int = 10
    
    # Google Earth Engine
    gee_credentials_path: str = ""
    gee_project_id: str = ""
    gee_timeout: int = 60
    
    # Sungrow iSolarCloud
    isolarcloud_url: str = "https://api.isolarcloud.com"
    isolarcloud_api_key: str = ""
    isolarcloud_secret: str = ""
    isolarcloud_username: str = ""
    isolarcloud_password: str = ""
    isolarcloud_timeout: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nasa_power_configured": bool(self.nasa_power_api_key),
            "openweather_configured": bool(self.openweather_api_key),
            "gee_configured": bool(self.gee_credentials_path),
            "isolarcloud_configured": bool(self.isolarcloud_api_key)
        }


@dataclass
class CeleryConfig:
    """Celery async task configuration"""
    enabled: bool = True
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/0"
    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: List[str] = field(default_factory=lambda: ["json"])
    timezone: str = "Africa/Lagos"
    enable_utc: bool = True
    task_track_started: bool = True
    task_time_limit: int = 1800
    task_soft_time_limit: int = 1500
    worker_prefetch_multiplier: int = 1
    worker_max_tasks_per_child: int = 100
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "broker_url": self.broker_url.split("@")[-1] if "@" in self.broker_url else self.broker_url,
            "task_time_limit": self.task_time_limit,
            "worker_max_tasks_per_child": self.worker_max_tasks_per_child
        }


@dataclass
class MonitoringConfig:
    """Monitoring and metrics configuration"""
    prometheus_enabled: bool = True
    prometheus_multiproc_dir: str = ""
    metrics_port: int = 9090
    health_check_interval: int = 30
    log_retention_days: int = 30
    slow_request_threshold_ms: int = 1000
    very_slow_request_threshold_ms: int = 5000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prometheus_enabled": self.prometheus_enabled,
            "health_check_interval": self.health_check_interval,
            "slow_request_threshold_ms": self.slow_request_threshold_ms,
            "log_retention_days": self.log_retention_days
        }


@dataclass
class WeatherConfig:
    """Weather intelligence configuration"""
    enabled: bool = True
    update_interval_seconds: int = 300
    forecast_hours: int = 24
    cache_ttl_seconds: int = 1800
    fallback_enabled: bool = True
    solar_prediction_enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "update_interval_seconds": self.update_interval_seconds,
            "forecast_hours": self.forecast_hours,
            "solar_prediction_enabled": self.solar_prediction_enabled
        }


@dataclass
class HardwareConfig:
    """Hardware integration configuration"""
    modbus_enabled: bool = True
    modbus_host: str = "192.168.1.100"
    modbus_port: int = 502
    modbus_unit_id: int = 1
    modbus_timeout_seconds: int = 5
    modbus_retry_count: int = 3
    hardware_poll_interval_seconds: int = 5
    simulation_mode: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "modbus_enabled": self.modbus_enabled,
            "modbus_host": self.modbus_host,
            "modbus_port": self.modbus_port,
            "hardware_poll_interval_seconds": self.hardware_poll_interval_seconds,
            "simulation_mode": self.simulation_mode
        }


@dataclass
class PartnerConfig:
    """Multi-tenancy partner configuration"""
    pilot_partners: List[Dict[str, Any]] = field(default_factory=list)
    default_energy_limit_kwh: int = 10000
    max_concurrent_sessions: int = 100
    enable_partner_portal: bool = True
    report_retention_days: int = 90
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pilot_partners_count": len(self.pilot_partners),
            "default_energy_limit_kwh": self.default_energy_limit_kwh,
            "enable_partner_portal": self.enable_partner_portal,
            "report_retention_days": self.report_retention_days
        }


@dataclass
class FeatureFlags:
    """Feature flags for progressive rollout"""
    aece_enabled: bool = True
    nuclear_enabled: bool = True
    quantum_kernel_enabled: bool = True
    weather_intelligence_enabled: bool = True
    geospatial_intelligence_enabled: bool = True
    hardware_integration_enabled: bool = True
    report_generation_enabled: bool = True
    websocket_enabled: bool = True
    celery_tasks_enabled: bool = True
    prometheus_metrics_enabled: bool = True
    adfi_orchestration_enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "aece_enabled": self.aece_enabled,
            "nuclear_enabled": self.nuclear_enabled,
            "quantum_kernel_enabled": self.quantum_kernel_enabled,
            "weather_intelligence_enabled": self.weather_intelligence_enabled,
            "hardware_integration_enabled": self.hardware_integration_enabled,
            "celery_tasks_enabled": self.celery_tasks_enabled
        }


@dataclass
class CompanyInfo:
    """Company information"""
    name: str = "NeuroBridge Technologies Ltd"
    cto: str = "Joseph Ochelebe"
    location: str = "Abuja, Nigeria"
    email: str = "neurobridgetechnologiesltd@gmail.com"
    whatsapp: str = "+2348163399026"
    website: str = "https://neurobridge.energy"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cto": self.cto,
            "location": self.location,
            "email": self.email,
            "whatsapp": self.whatsapp,
            "website": self.website
        }


# ============================================================================
# MAIN SETTINGS CLASS
# ============================================================================

@dataclass
class Settings:
    """Centralized application settings"""
    
    # Environment
    environment: Environment = Environment.PRODUCTION
    deployment_zone: DeploymentZone = DeploymentZone.ABUJA_QUANTUM_GRID
    debug: bool = False
    
    # Service configurations
    server: ServerConfig = field(default_factory=ServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    aece: AECEConfig = field(default_factory=AECEConfig)
    apis: APIConfig = field(default_factory=APIConfig)
    celery: CeleryConfig = field(default_factory=CeleryConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    partner: PartnerConfig = field(default_factory=PartnerConfig)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    company: CompanyInfo = field(default_factory=CompanyInfo)
    
    # Version information
    version: str = "10.0.0-ENTERPRISE-PRODUCTION"
    build_date: str = "2026.04.12"
    
    def __post_init__(self):
        """Load configuration from environment variables"""
        self._load_from_env()
        self._validate()
        self._log_config()
    
    def _load_from_env(self):
        """Load configuration from environment variables"""
        
        # Environment
        env_str = os.getenv("ENVIRONMENT", "production").lower()
        self.environment = Environment(env_str) if env_str in [e.value for e in Environment] else Environment.PRODUCTION
        self.debug = self.environment == Environment.DEVELOPMENT
        
        # Deployment zone
        zone_str = os.getenv("DEPLOYMENT_ZONE", "abuja_quantum_grid").lower()
        if zone_str in [z.value for z in DeploymentZone]:
            self.deployment_zone = DeploymentZone(zone_str)
        
        # Server
        self.server.host = os.getenv("HOST", "0.0.0.0")
        self.server.port = int(os.getenv("PORT", "8000"))
        self.server.reload = os.getenv("RELOAD", "false").lower() == "true"
        self.server.workers = int(os.getenv("WORKERS", "4"))
        self.server.log_level = os.getenv("LOG_LEVEL", "info")
        
        # Security
        self.security.cto_access_code = os.getenv("CTO_ACCESS_CODE", "")
        self.security.jwt_secret_key = os.getenv("JWT_SECRET_KEY", self._generate_jwt_secret())
        
        # Database
        self.database.url = os.getenv("DATABASE_URL", "sqlite:///./neurobridge.db")
        
        # Redis
        self.redis.url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis.enabled = os.getenv("ENABLE_REDIS_CACHE", "true").lower() == "true"
        
        # AECE
        self.aece.enabled = os.getenv("AECE_ENABLED", "true").lower() == "true"
        self.aece.risk_threshold_critical = float(os.getenv("AECE_RISK_THRESHOLD_CRITICAL", "0.8"))
        self.aece.risk_threshold_high = float(os.getenv("AECE_RISK_THRESHOLD_HIGH", "0.6"))
        self.aece.protection_mode_enabled = os.getenv("AECE_PROTECTION_MODE", "true").lower() == "true"
        
        # External APIs
        self.apis.nasa_power_api_key = os.getenv("NASA_API_KEY", "")
        self.apis.openweather_api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.apis.gee_credentials_path = os.getenv("GEE_CREDENTIALS", "")
        self.apis.isolarcloud_api_key = os.getenv("ISOLARCLOUD_API_KEY", "")
        self.apis.isolarcloud_secret = os.getenv("ISOLARCLOUD_SECRET", "")
        self.apis.isolarcloud_username = os.getenv("ISOLARCLOUD_USERNAME", "")
        self.apis.isolarcloud_password = os.getenv("ISOLARCLOUD_PASSWORD", "")
        
        # Celery
        self.celery.enabled = os.getenv("CELERY_ENABLED", "true").lower() == "true"
        self.celery.broker_url = os.getenv("CELERY_BROKER_URL", self.redis.url)
        
        # Monitoring
        self.monitoring.prometheus_enabled = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"
        
        # Weather
        self.weather.enabled = os.getenv("WEATHER_INTELLIGENCE_ENABLED", "true").lower() == "true"
        
        # Hardware
        self.hardware.modbus_enabled = os.getenv("MODBUS_ENABLED", "true").lower() == "true"
        self.hardware.modbus_host = os.getenv("MODBUS_HOST", "192.168.1.100")
        self.hardware.modbus_port = int(os.getenv("MODBUS_PORT", "502"))
        self.hardware.simulation_mode = os.getenv("HARDWARE_SIMULATION", "false").lower() == "true"
        
        # Feature flags
        self.features.aece_enabled = self.aece.enabled
        self.features.weather_intelligence_enabled = self.weather.enabled
        
        # Company info
        self.company.name = os.getenv("COMPANY_NAME", "NeuroBridge Technologies Ltd")
        self.company.cto = os.getenv("COMPANY_CTO", "Joseph Ochelebe")
        self.company.location = os.getenv("COMPANY_LOCATION", "Abuja, Nigeria")
        self.company.email = os.getenv("COMPANY_EMAIL", "neurobridgetechnologiesltd@gmail.com")
        self.company.whatsapp = os.getenv("COMPANY_WHATSAPP", "+2348163399026")
        
        # Version from environment
        self.version = os.getenv("APP_VERSION", "10.0.0-ENTERPRISE-PRODUCTION")
    
    def _generate_jwt_secret(self) -> str:
        """Generate a secure JWT secret if not provided"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def _validate(self):
        """Validate critical configuration"""
        if self.environment == Environment.PRODUCTION:
            if not self.security.cto_access_code:
                logger.warning("PRODUCTION: CTO_ACCESS_CODE not set in environment")
            
            if self.redis.enabled and "localhost" in self.redis.url:
                logger.warning("PRODUCTION: Using localhost Redis - consider dedicated instance")
    
    def _log_config(self):
        """Log configuration summary"""
        logger.info("=" * 60)
        logger.info(f"NeuroBridge 11D Configuration Loaded")
        logger.info("=" * 60)
        logger.info(f"Environment: {self.environment.value.upper()}")
        logger.info(f"Deployment Zone: {self.deployment_zone.value}")
        logger.info(f"Version: {self.version}")
        logger.info("-" * 40)
        logger.info(f"Server: {self.server.host}:{self.server.port}")
        logger.info(f"Redis: {'Enabled' if self.redis.enabled else 'Disabled'}")
        logger.info(f"AECE: {'Enabled' if self.aece.enabled else 'Disabled'}")
        logger.info(f"Celery: {'Enabled' if self.celery.enabled else 'Disabled'}")
        logger.info(f"Prometheus: {'Enabled' if self.monitoring.prometheus_enabled else 'Disabled'}")
        logger.info(f"Hardware: {'Enabled' if self.hardware.modbus_enabled else 'Disabled'}")
        logger.info("=" * 60)
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == Environment.DEVELOPMENT
    
    def is_staging(self) -> bool:
        """Check if running in staging mode"""
        return self.environment == Environment.STAGING
    
    def get_redis_url(self) -> str:
        """Get Redis URL with validation"""
        if not self.redis.enabled:
            return ""
        return self.redis.url
    
    def get_aece_risk_thresholds(self) -> Dict[str, float]:
        """Get AECE risk thresholds"""
        return {
            "critical": self.aece.risk_threshold_critical,
            "high": self.aece.risk_threshold_high,
            "medium": self.aece.risk_threshold_medium
        }
    
    def get_api_keys_status(self) -> Dict[str, bool]:
        """Get status of external API keys"""
        return {
            "nasa_power": bool(self.apis.nasa_power_api_key),
            "openweather": bool(self.apis.openweather_api_key),
            "google_earth_engine": bool(self.apis.gee_credentials_path),
            "sungrow_isolarcloud": bool(self.apis.isolarcloud_api_key)
        }
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags"""
        return self.features.to_dict()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entire configuration to dictionary"""
        return {
            "environment": self.environment.value,
            "deployment_zone": self.deployment_zone.value,
            "debug": self.debug,
            "version": self.version,
            "build_date": self.build_date,
            "server": self.server.to_dict(),
            "security": self.security.to_dict(),
            "database": self.database.to_dict(),
            "redis": self.redis.to_dict(),
            "aece": self.aece.to_dict(),
            "apis": self.apis.to_dict(),
            "celery": self.celery.to_dict(),
            "monitoring": self.monitoring.to_dict(),
            "weather": self.weather.to_dict(),
            "hardware": self.hardware.to_dict(),
            "partner": self.partner.to_dict(),
            "features": self.features.to_dict(),
            "company": self.company.to_dict()
        }
    
    def get_health_check_config(self) -> Dict[str, Any]:
        """Get configuration for health checks"""
        return {
            "environment": self.environment.value,
            "version": self.version,
            "features_enabled": {
                "aece": self.features.aece_enabled,
                "nuclear": self.features.nuclear_enabled,
                "quantum_kernel": self.features.quantum_kernel_enabled,
                "weather": self.features.weather_intelligence_enabled,
                "hardware": self.features.hardware_integration_enabled,
                "celery": self.features.celery_tasks_enabled
            },
            "services": {
                "redis": self.redis.enabled,
                "prometheus": self.monitoring.prometheus_enabled,
                "websocket": self.features.websocket_enabled
            }
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the singleton settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# ============================================================================
# DEPENDENCY INJECTION FOR FASTAPI
# ============================================================================

async def get_settings_dependency() -> Settings:
    """FastAPI dependency for settings injection"""
    return get_settings()


# ============================================================================
# CONVENIENCE ACCESSOR
# ============================================================================

settings = get_settings()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'Settings',
    'Environment',
    'DeploymentZone',
    'ServerConfig',
    'SecurityConfig',
    'DatabaseConfig',
    'RedisConfig',
    'AECEConfig',
    'APIConfig',
    'CeleryConfig',
    'MonitoringConfig',
    'WeatherConfig',
    'HardwareConfig',
    'PartnerConfig',
    'FeatureFlags',
    'CompanyInfo',
    'get_settings',
    'get_settings_dependency',
    'settings'
]


# ============================================================================
# SELF-TEST
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Testing NeuroBridge 11D Configuration System")
    print("=" * 60)
    
    config = get_settings()
    
    print("\n📋 Configuration Summary:")
    print(f"   Environment: {config.environment.value}")
    print(f"   Deployment Zone: {config.deployment_zone.value}")
    print(f"   Version: {config.version}")
    
    print("\n🔧 Service Status:")
    print(f"   AECE: {'✅ Enabled' if config.aece.enabled else '❌ Disabled'}")
    print(f"   Redis: {'✅ Enabled' if config.redis.enabled else '❌ Disabled'}")
    print(f"   Celery: {'✅ Enabled' if config.celery.enabled else '❌ Disabled'}")
    print(f"   Hardware: {'✅ Enabled' if config.hardware.modbus_enabled else '❌ Disabled'}")
    
    print("\n🔑 API Keys Status:")
    for api, status in config.get_api_keys_status().items():
        print(f"   {api}: {'✅ Configured' if status else '⚠️ Not Configured'}")
    
    print("\n🎛️ AECE Risk Thresholds:")
    thresholds = config.get_aece_risk_thresholds()
    for level, threshold in thresholds.items():
        print(f"   {level.upper()}: {threshold}")
    
    print("\n✅ Configuration test complete!")