"""
NeuroBridge 11D - Autonomous Energy Control Engine Package
Enterprise-grade real-time control system

Version: 2.0.0-PRODUCTION-FIXED
Build: 2026.04.13

Exports:
    - aece: Singleton AECE engine instance
    - get_aece_engine: Function to get the engine instance
    - router: FastAPI router for control endpoints
    - get_router: Function to get the router
    - UEIV: Unified Energy Intelligence Vector dataclass
    - ControlAction: Enum of available control actions
    - ControlPriority: Enum of action priorities
    - ControlDecision: Decision output dataclass
    - RiskScoringEngine: Risk calculation engine
    - DecisionEngine: Decision making engine
    - ActionExecutor: Action execution engine
    - AECE_AVAILABLE: Flag indicating AECE is available
"""

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# EXPORTS - All imports properly exposed from aece_engine
# ============================================================================

from backend.control.aece_engine import (
    aece,
    get_aece_engine,
    router,
    get_router,
    UEIV,
    ControlAction,
    ControlPriority,
    ControlDecision,
    RiskScoringEngine,
    DecisionEngine,
    ActionExecutor,
    AutonomousEnergyControlEngine,
    AECE_AVAILABLE,
)

# Also export the engine class with alias
AECEEngine = AutonomousEnergyControlEngine

# Log successful import
logger.debug("[control.__init__] ✅ AECE package exports loaded")

# ============================================================================
# PACKAGE EXPORTS
# ============================================================================

__all__ = [
    'aece',
    'get_aece_engine',
    'router',
    'get_router',
    'UEIV',
    'ControlAction',
    'ControlPriority',
    'ControlDecision',
    'RiskScoringEngine',
    'DecisionEngine',
    'ActionExecutor',
    'AutonomousEnergyControlEngine',
    'AECEEngine',
    'AECE_AVAILABLE',
]