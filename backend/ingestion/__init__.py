"""
NeuroBridge 11D - Ingestion Package
Phase 1 Production - Deterministic Physics Data Fabric

AIQL: removed
Hugging Face: removed
Runtime mode: deterministic physics only
"""

from backend.ingestion.adfi_engine import (
    ADFIEngine,
    get_adfi_engine,
    reset_adfi_engine,
    initialize_adfi,
    shutdown_adfi,
    get_grid_metrics,
    get_solar_metrics,
    get_aece_risk,
    HardwareFetcher,
    APIFetcher,
    DataSource,
    DataPriority,
    DataSourceConfig,
    CircuitBreaker,
    DeterministicPhysicsEngine,
    DataQualityEngine,
    get_physics_status,
    get_data_fabric_status,
    get_audit_log,
)

__all__ = [
    "ADFIEngine",
    "get_adfi_engine",
    "reset_adfi_engine",
    "initialize_adfi",
    "shutdown_adfi",
    "get_grid_metrics",
    "get_solar_metrics",
    "get_aece_risk",
    "HardwareFetcher",
    "APIFetcher",
    "DataSource",
    "DataPriority",
    "DataSourceConfig",
    "CircuitBreaker",
    "DeterministicPhysicsEngine",
    "DataQualityEngine",
    "get_physics_status",
    "get_data_fabric_status",
    "get_audit_log",
]