"""
NeuroBridge - Integrations Package

Production-safe integration exports for ADFI engine and orchestrator.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("NeuroBridge.Integrations")

# Single concise initialization log - NO BANNER
logger.info("[INTEGRATIONS] package initializing")

# ============================================================================
# EXISTING SUCCESSFUL ADFI ENGINE EXPORTS
# ============================================================================

try:
    from backend.ingestion.adfi_engine import (
        ADFIEngine,
        get_adfi_engine,
        initialize_adfi,
        shutdown_adfi,
        get_grid_metrics,
        get_solar_metrics,
        get_aece_risk,
        DeterministicPhysicsEngine,
        DataQualityEngine,
        get_physics_status,
        get_data_fabric_status,
        get_audit_log,
    )

    ADFI_ENGINE_AVAILABLE = True
    logger.debug("[INTEGRATIONS] ADFI engine loaded")

except ImportError as exc:
    logger.debug(f"[INTEGRATIONS] ADFI engine not available: {exc}")
    ADFI_ENGINE_AVAILABLE = False

    ADFIEngine = None
    DeterministicPhysicsEngine = None
    DataQualityEngine = None

    def get_adfi_engine(*args, **kwargs) -> Optional[Any]:
        return None

    def initialize_adfi(*args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "ADFI engine unavailable"}

    def shutdown_adfi(*args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "ADFI engine unavailable"}

    def get_grid_metrics(*args, **kwargs) -> Dict[str, Any]:
        return {"available": False, "error": "ADFI engine unavailable"}

    def get_solar_metrics(*args, **kwargs) -> Dict[str, Any]:
        return {"available": False, "error": "ADFI engine unavailable"}

    def get_aece_risk(*args, **kwargs) -> float:
        return 0.15

    def get_physics_status(*args, **kwargs) -> Dict[str, Any]:
        return {"available": False, "status": "unavailable"}

    def get_data_fabric_status(*args, **kwargs) -> Dict[str, Any]:
        return {"available": False, "status": "unavailable"}

    def get_audit_log(*args, **kwargs) -> List[Dict[str, Any]]:
        return []

except Exception as exc:
    logger.error(f"[INTEGRATIONS] Failed to load ADFI engine: {exc}")
    ADFI_ENGINE_AVAILABLE = False
    ADFIEngine = None
    DeterministicPhysicsEngine = None
    DataQualityEngine = None
    get_adfi_engine = lambda *a, **k: None
    initialize_adfi = lambda *a, **k: {"success": False, "error": str(exc)}
    shutdown_adfi = lambda *a, **k: {"success": False, "error": str(exc)}
    get_grid_metrics = lambda *a, **k: {"available": False, "error": str(exc)}
    get_solar_metrics = lambda *a, **k: {"available": False, "error": str(exc)}
    get_aece_risk = lambda *a, **k: 0.15
    get_physics_status = lambda *a, **k: {"available": False, "status": "error"}
    get_data_fabric_status = lambda *a, **k: {"available": False, "status": "error"}
    get_audit_log = lambda *a, **k: []


# ============================================================================
# NEW PRODUCTION-SAFE ADFI ORCHESTRATOR EXPORTS
# ============================================================================

try:
    from backend.integrations.adfi_orchestrator import (
        ADFIOrchestrator,
        ADFIDataPoint,
        DataSourceType,
        RegisteredSource,
        SourceStatus,
        get_orchestrator,
        reset_orchestrator,
    )

    ADFI_ORCHESTRATOR_AVAILABLE = True
    logger.debug("[INTEGRATIONS] ADFI orchestrator loaded")

except ImportError as exc:
    logger.debug(f"[INTEGRATIONS] ADFI orchestrator not available: {exc}")
    ADFI_ORCHESTRATOR_AVAILABLE = False

    ADFIOrchestrator = None
    ADFIDataPoint = None
    RegisteredSource = None
    SourceStatus = None

    class DataSourceType:
        HARDWARE = "hardware"
        ISOLARCLOUD = "isolarcloud"
        NASA = "nasa"
        OPENWEATHER = "openweather"
        GEE = "gee"
        SYNTHETIC = "synthetic"
        CACHE = "cache"
        FALLBACK = "fallback"

    def get_orchestrator(*args, **kwargs) -> Optional[Any]:
        return None

    def reset_orchestrator(*args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "ADFI orchestrator unavailable"}

except Exception as exc:
    logger.error(f"[INTEGRATIONS] Failed to load ADFI orchestrator: {exc}")
    ADFI_ORCHESTRATOR_AVAILABLE = False
    ADFIOrchestrator = None
    ADFIDataPoint = None
    RegisteredSource = None
    SourceStatus = None
    
    class DataSourceType:
        HARDWARE = "hardware"
        ISOLARCLOUD = "isolarcloud"
        NASA = "nasa"
        OPENWEATHER = "openweather"
        GEE = "gee"
        SYNTHETIC = "synthetic"
        CACHE = "cache"
        FALLBACK = "fallback"
    
    get_orchestrator = lambda *a, **k: None
    reset_orchestrator = lambda *a, **k: {"success": False, "error": str(exc)}


# ============================================================================
# DATA PIPELINE EXPORTS
# ============================================================================

try:
    from backend.integrations.data_pipeline import get_data_pipeline
    DATA_PIPELINE_AVAILABLE = True
    logger.debug("[INTEGRATIONS] data pipeline loaded")
except ImportError as exc:
    logger.debug(f"[INTEGRATIONS] data pipeline not available: {exc}")
    DATA_PIPELINE_AVAILABLE = False
    
    def get_data_pipeline(*args, **kwargs) -> Optional[Any]:
        return None
except Exception as exc:
    logger.error(f"[INTEGRATIONS] Failed to load data pipeline: {exc}")
    DATA_PIPELINE_AVAILABLE = False
    get_data_pipeline = lambda *a, **k: None


try:
    from backend.integrations.data_pipeline import initialize_pipeline
except ImportError:
    def initialize_pipeline(*args: Any, **kwargs: Any) -> Optional[Any]:
        return None
except Exception:
    def initialize_pipeline(*args: Any, **kwargs: Any) -> Optional[Any]:
        return None


# ============================================================================
# ENERGY DATA POINT EXPORTS
# ============================================================================

try:
    from backend.integrations.data_pipeline import EnergyDataPoint
    ENERGY_DATA_POINT_AVAILABLE = True
except ImportError:
    ENERGY_DATA_POINT_AVAILABLE = False
    
    class EnergyDataPoint:
        __slots__ = ('timestamp', 'source_type', 'priority', 'data', 'quality_score')
        
        def __init__(self, timestamp=None, source_type=None, priority=None, data=None, quality_score=0.85):
            self.timestamp = timestamp
            self.source_type = source_type
            self.priority = priority
            self.data = data or {}
            self.quality_score = quality_score
        
        def to_dict(self) -> Dict[str, Any]:
            return {
                "timestamp": self.timestamp,
                "source_type": self.source_type,
                "priority": self.priority,
                "data": self.data,
                "quality_score": self.quality_score
            }
except Exception:
    ENERGY_DATA_POINT_AVAILABLE = False
    
    class EnergyDataPoint:
        def __init__(self, *args, **kwargs):
            pass
        
        def to_dict(self) -> Dict[str, Any]:
            return {}


# ============================================================================
# DATA PRIORITY EXPORTS
# ============================================================================

try:
    from backend.integrations.data_pipeline import DataPriority
    DATA_PRIORITY_AVAILABLE = True
except ImportError:
    DATA_PRIORITY_AVAILABLE = False
    
    class DataPriority:
        LOW = "low"
        NORMAL = "normal"
        HIGH = "high"
        CRITICAL = "critical"
except Exception:
    DATA_PRIORITY_AVAILABLE = False
    
    class DataPriority:
        LOW = "low"
        NORMAL = "normal"
        HIGH = "high"
        CRITICAL = "critical"


# ============================================================================
# LEGACY EXPORTS FOR BACKWARD COMPATIBILITY
# ============================================================================

try:
    from backend.integrations.data_pipeline import (
        get_pipeline_status,
        get_pipeline_metrics,
        get_data_quality_report
    )
except ImportError:
    def get_pipeline_status() -> Dict[str, Any]:
        return {"available": DATA_PIPELINE_AVAILABLE, "status": "unavailable"}
    
    def get_pipeline_metrics() -> Dict[str, Any]:
        return {"available": DATA_PIPELINE_AVAILABLE, "metrics": {}}
    
    def get_data_quality_report() -> Dict[str, Any]:
        return {"available": DATA_PIPELINE_AVAILABLE, "quality_score": 0.85}


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ADFI_ENGINE_AVAILABLE",
    "ADFI_ORCHESTRATOR_AVAILABLE",
    "DATA_PIPELINE_AVAILABLE",
    "ENERGY_DATA_POINT_AVAILABLE",
    "DATA_PRIORITY_AVAILABLE",
    "ADFIEngine",
    "get_adfi_engine",
    "initialize_adfi",
    "shutdown_adfi",
    "get_grid_metrics",
    "get_solar_metrics",
    "get_aece_risk",
    "DeterministicPhysicsEngine",
    "DataQualityEngine",
    "get_physics_status",
    "get_data_fabric_status",
    "get_audit_log",
    "ADFIOrchestrator",
    "ADFIDataPoint",
    "DataSourceType",
    "RegisteredSource",
    "SourceStatus",
    "get_orchestrator",
    "reset_orchestrator",
    "get_data_pipeline",
    "initialize_pipeline",
    "get_pipeline_status",
    "get_pipeline_metrics",
    "get_data_quality_report",
    "EnergyDataPoint",
    "DataPriority",
]


EXPORT_COUNT = len(__all__)

# Module ready log
logger.info(f"[INTEGRATIONS] ready exports={EXPORT_COUNT}")