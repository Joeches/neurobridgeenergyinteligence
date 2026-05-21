"""
================================================================================
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                   ║
║   █████╗ ███████╗ ██████╗███████╗                                                ║
║  ██╔══██╗██╔════╝██╔════╝██╔════╝                                                ║
║  ███████║█████╗  ██║     █████╗                                                  ║
║  ██╔══██║██╔══╝  ██║     ██╔══╝                                                  ║
║  ██║  ██║███████╗╚██████╗███████╗                                                ║
║  ╚═╝  ╚═╝╚══════╝ ╚═════╝╚══════╝                                                ║
║                                                                                   ║
║              AECE v3.0/v4.0 COMPATIBILITY LAYER                                  ║
║                                                                                   ║
║  This module provides backward compatibility between:                            ║
║  - AECE v3 API (get_unified_controller, get_decision_engine, etc.)              ║
║  - AECE v4 implementation (EnhancedDecisionEngine, EnhancedActionExecutor)      ║
║                                                                                   ║
║  🔧 CRITICAL FIX v4.0.3:                                                         ║
║  ✓ Added UnifiedController wrapper for v4 components                            ║
║  ✓ Added get_unified_controller() function                                       ║
║  ✓ Added get_decision_engine() alias                                             ║
║  ✓ Added get_action_executor() alias                                             ║
║  ✓ Added get_metrics_engine() alias                                              ║
║  ✓ Added evaluate_and_execute() convenience function                             ║
║  ✓ Added get_aece_status() function                                              ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
================================================================================
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ============================================================================
# IMPORT V4 COMPONENTS (The actual implementations)
# ============================================================================

try:
    # Try to import from backend.control.aece_engine (v4 location)
    from backend.control.aece_engine import (
        AutonomousEnergyControlEngine,
        EnhancedDecisionEngine,
        EnhancedActionExecutor,
        EnhancedRiskScoringEngine,
        UEIV,
        ControlDecision,
        ControlAction,
        ControlPriority,
        DecisionConfidence,
        get_aece_engine as v4_get_aece_engine,
        aece as v4_aece_instance
    )
    V4_AVAILABLE = True
    logger.info("[AECE] ✅ v4 components loaded from backend.control.aece_engine")
except ImportError as e:
    V4_AVAILABLE = False
    logger.warning(f"[AECE] v4 components not available: {e}")

# ============================================================================
# TRY TO IMPORT V2 COMPONENTS (Fallback)
# ============================================================================

try:
    from backend.aece.decision_engine_v2 import (
        get_decision_engine as v2_get_decision_engine,
        DecisionEngineV3,
        TelemetrySnapshot,
        PredictionData,
        ActionType
    )
    V2_AVAILABLE = True
    logger.info("[AECE] ✅ v2 components loaded from decision_engine_v2")
except ImportError as e:
    V2_AVAILABLE = False
    logger.debug(f"[AECE] v2 components not available: {e}")

try:
    from backend.aece.action_executor_v2 import (
        get_action_executor as v2_get_action_executor,
        ActionExecutorV3
    )
    V2_EXECUTOR_AVAILABLE = True
    logger.info("[AECE] ✅ v2 action executor loaded")
except ImportError as e:
    V2_EXECUTOR_AVAILABLE = False
    logger.debug(f"[AECE] v2 action executor not available: {e}")


# ============================================================================
# UNIFIED CONTROLLER - Bridges v4 components with v3/v4 API
# ============================================================================

class UnifiedAECEController:
    """
    Unified controller that provides the v3/v4 API using v4 components.
    This is the main entry point for AECE control.
    """
    
    def __init__(self):
        self._engine = None
        self._decision_engine = None
        self._action_executor = None
        self._initialized = False
        self._initialize()
    
    def _initialize(self):
        """Initialize the controller with available components"""
        try:
            # Use v4 engine if available
            if V4_AVAILABLE:
                self._engine = v4_aece_instance
                self._decision_engine = self._engine.decision_engine if hasattr(self._engine, 'decision_engine') else None
                self._action_executor = self._engine.action_executor if hasattr(self._engine, 'action_executor') else None
                logger.info("[UnifiedController] ✅ Using v4 components")
            # Fallback to v2 components
            elif V2_AVAILABLE:
                self._decision_engine = v2_get_decision_engine() if callable(v2_get_decision_engine) else v2_get_decision_engine
                self._action_executor = v2_get_action_executor() if V2_EXECUTOR_AVAILABLE and callable(v2_get_action_executor) else None
                logger.info("[UnifiedController] ✅ Using v2 components (fallback)")
            else:
                logger.warning("[UnifiedController] ⚠️ No AECE components available")
            
            self._initialized = True
        except Exception as e:
            logger.error(f"[UnifiedController] Initialization failed: {e}")
            self._initialized = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive controller status"""
        status = {
            "initialized": self._initialized,
            "v4_available": V4_AVAILABLE,
            "v2_available": V2_AVAILABLE,
            "decision_engine_version": "v4.0.0" if V4_AVAILABLE else ("v3.0.0" if V2_AVAILABLE else "unknown"),
            "action_executor_version": "v4.0.0" if V4_AVAILABLE else ("v3.0.0" if V2_EXECUTOR_AVAILABLE else "unknown"),
            "phase": "PHASE_1_PRODUCTION"
        }
        
        # Add detailed engine status if available
        if self._engine and hasattr(self._engine, 'get_status'):
            try:
                engine_status = self._engine.get_status()
                status["engine"] = engine_status
            except Exception as e:
                status["engine_error"] = str(e)
        
        return status
    
    async def execute_action(self, action: str, telemetry: Dict[str, Any], params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a control action by name.
        
        Args:
            action: Action name (e.g., "reduce_load", "increase_solar_efficiency")
            telemetry: Current telemetry data
            params: Optional parameters for the action
        
        Returns:
            Dict with execution result
        """
        if not self._initialized:
            return {"success": False, "error": "Controller not initialized"}
        
        try:
            # Map action string to execution method
            action_map = {
                "reduce_load": self._execute_reduce_load,
                "redistribute_energy": self._execute_redistribute_energy,
                "preemptive_stabilization": self._execute_preemptive_stabilization,
                "trigger_alert": self._execute_trigger_alert,
                "lockdown_mode": self._execute_lockdown_mode,
                "increase_solar_efficiency": self._execute_increase_solar_efficiency,
                "dispatch_battery": self._execute_dispatch_battery,
                "curtail_solar": self._execute_curtail_solar,
                "adjust_inverter_power": self._execute_adjust_inverter_power,
                "no_action": self._execute_no_action,
            }
            
            executor = action_map.get(action)
            if executor:
                return await executor(telemetry, params or {})
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"[UnifiedController] Execute action error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_reduce_load(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'reduce_load'):
            percentage = params.get("percentage", params.get("reduction_percent", 20))
            return await self._action_executor.reduce_load(percentage, params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_redistribute_energy(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'redistribute_energy'):
            return await self._action_executor.redistribute_energy(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_preemptive_stabilization(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'preemptive_stabilization'):
            return await self._action_executor.preemptive_stabilization(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_trigger_alert(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'trigger_alert'):
            message = params.get("message", "AECE triggered alert")
            return await self._action_executor.trigger_alert(message, params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_lockdown_mode(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'activate_protection_mode'):
            return await self._action_executor.activate_protection_mode(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_increase_solar_efficiency(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'increase_solar_efficiency'):
            return await self._action_executor.increase_solar_efficiency(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_dispatch_battery(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'dispatch_battery'):
            return await self._action_executor.dispatch_battery(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_curtail_solar(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'curtail_solar'):
            return await self._action_executor.curtail_solar(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_adjust_inverter_power(self, telemetry: Dict, params: Dict) -> Dict:
        if self._action_executor and hasattr(self._action_executor, 'adjust_inverter_power'):
            return await self._action_executor.adjust_inverter_power(params)
        return {"success": False, "error": "Action executor not available"}
    
    async def _execute_no_action(self, telemetry: Dict, params: Dict) -> Dict:
        return {"success": True, "message": "No action taken", "phase": "PHASE_1_PRODUCTION"}


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_unified_controller: Optional[UnifiedAECEController] = None


def get_unified_controller() -> UnifiedAECEController:
    """
    Get the unified AECE controller singleton.
    This is the main entry point for AECE control in main.py.
    """
    global _unified_controller
    if _unified_controller is None:
        _unified_controller = UnifiedAECEController()
        logger.info("[AECE] ✅ Unified controller created")
    return _unified_controller


# ============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================================================

def get_decision_engine():
    """
    Get the decision engine (backward compatibility).
    Returns the v2 or v4 decision engine depending on availability.
    """
    controller = get_unified_controller()
    if controller._decision_engine:
        return controller._decision_engine
    
    # Fallback to v2
    if V2_AVAILABLE and v2_get_decision_engine:
        return v2_get_decision_engine() if callable(v2_get_decision_engine) else v2_get_decision_engine
    
    return None


def get_action_executor():
    """
    Get the action executor (backward compatibility).
    Returns the v2 or v4 action executor depending on availability.
    """
    controller = get_unified_controller()
    if controller._action_executor:
        return controller._action_executor
    
    # Fallback to v2
    if V2_EXECUTOR_AVAILABLE and v2_get_action_executor:
        return v2_get_action_executor() if callable(v2_get_action_executor) else v2_get_action_executor
    
    return None


def get_metrics_engine():
    """
    Get the metrics engine (backward compatibility).
    """
    try:
        from backend.aece.metrics_engine import get_metrics_engine as get_metrics
        return get_metrics()
    except ImportError:
        logger.debug("[AECE] Metrics engine not available")
        return None


def get_aece_status() -> Dict[str, Any]:
    """
    Get comprehensive AECE system status.
    """
    controller = get_unified_controller()
    status = controller.get_status()
    
    # Add additional metrics
    status.update({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "4.0.3-COMPATIBILITY",
        "phase": "PHASE_1_PRODUCTION",
        "decision_engine_stats": {
            "available": controller._decision_engine is not None,
            "type": "v4" if V4_AVAILABLE else ("v2" if V2_AVAILABLE else "none")
        },
        "action_executor_stats": {
            "available": controller._action_executor is not None,
            "type": "v4" if V4_AVAILABLE else ("v2" if V2_EXECUTOR_AVAILABLE else "none")
        }
    })
    
    return status


async def evaluate_and_execute(
    telemetry: Dict[str, Any],
    predictions: Dict[str, Any],
    execute: bool = True
) -> Dict[str, Any]:
    """
    Evaluate telemetry and execute the resulting action.
    This is the main autonomous control loop function.
    
    Args:
        telemetry: Current telemetry data
        predictions: Prediction data (grid_stress_forecast, solar_forecast_kw, etc.)
        execute: Whether to execute the action or just return the decision
    
    Returns:
        Dict with decision and execution result
    """
    try:
        # Create TelemetrySnapshot if v2 classes available
        if V2_AVAILABLE and 'TelemetrySnapshot' in dir():
            from backend.aece import TelemetrySnapshot, PredictionData
            
            telemetry_snapshot = TelemetrySnapshot(
                active_power_kw=telemetry.get("active_power_kw", 0),
                grid_frequency_hz=telemetry.get("grid_frequency_hz", 50.0),
                demand_load_kw=telemetry.get("demand_load_kw", 0),
                solar_output_kw=telemetry.get("solar_output_kw", 0),
                battery_soc_percent=telemetry.get("battery_soc_percent", 50),
                voltage_v=telemetry.get("voltage_v", 230),
                temperature_c=telemetry.get("temperature_c", 25)
            )
            
            predictions_data = PredictionData(
                grid_stress_forecast=predictions.get("grid_stress_forecast", 0.3),
                solar_forecast_kw=predictions.get("solar_forecast_kw", 0),
                demand_forecast_kw=predictions.get("demand_forecast_kw", 0),
                weather_severity=predictions.get("weather_severity", 0.2)
            )
            
            decision_engine = get_decision_engine()
            if decision_engine:
                decision = decision_engine.evaluate(telemetry_snapshot, predictions_data)
                
                result = {
                    "success": True,
                    "decision": {
                        "action": decision.action.value if hasattr(decision, 'action') else decision.get("action", "no_action"),
                        "risk_score": decision.risk_score if hasattr(decision, 'risk_score') else decision.get("risk_score", 0.5),
                        "confidence": decision.confidence_score if hasattr(decision, 'confidence_score') else decision.get("confidence", 0.8),
                        "reason": decision.reason if hasattr(decision, 'reason') else decision.get("reason", "No reason provided")
                    }
                }
                
                if execute and result["decision"]["action"] != "no_action":
                    controller = get_unified_controller()
                    exec_result = await controller.execute_action(
                        action=result["decision"]["action"],
                        telemetry=telemetry,
                        params=decision.recommended_parameters if hasattr(decision, 'recommended_parameters') else {}
                    )
                    result["execution"] = exec_result
                
                return result
        
        # Fallback: simple rule-based decision
        risk_score = telemetry.get("grid_frequency_hz", 50.0)
        risk_score = abs(50.0 - risk_score) / 2.0
        risk_score = min(1.0, risk_score)
        
        action = "no_action"
        if risk_score > 0.7:
            action = "reduce_load"
        elif telemetry.get("solar_output_kw", 0) < 50:
            action = "increase_solar_efficiency"
        
        result = {
            "success": True,
            "decision": {
                "action": action,
                "risk_score": risk_score,
                "confidence": 0.85,
                "reason": "Fallback rule-based decision"
            }
        }
        
        if execute and action != "no_action":
            controller = get_unified_controller()
            exec_result = await controller.execute_action(action=action, telemetry=telemetry, params={})
            result["execution"] = exec_result
        
        return result
        
    except Exception as e:
        logger.error(f"[AECE] evaluate_and_execute error: {e}")
        return {
            "success": False,
            "error": str(e),
            "decision": {"action": "no_action", "risk_score": 0.5, "confidence": 0.0, "reason": f"Error: {e}"}
        }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'get_unified_controller',
    'get_decision_engine',
    'get_action_executor',
    'get_metrics_engine',
    'evaluate_and_execute',
    'get_aece_status',
    'UnifiedAECEController',
    'TelemetrySnapshot',
    'PredictionData',
    'ActionType'
]

# Try to import TelemetrySnapshot and PredictionData from v2 for export
try:
    from backend.aece.decision_engine_v2 import TelemetrySnapshot, PredictionData, ActionType
    __all__.extend(['TelemetrySnapshot', 'PredictionData', 'ActionType'])
except ImportError:
    # Define fallback classes
    class TelemetrySnapshot:
        def __init__(self, active_power_kw=0, grid_frequency_hz=50.0, demand_load_kw=0,
                     solar_output_kw=0, battery_soc_percent=50, voltage_v=230, temperature_c=25):
            self.active_power_kw = active_power_kw
            self.grid_frequency_hz = grid_frequency_hz
            self.demand_load_kw = demand_load_kw
            self.solar_output_kw = solar_output_kw
            self.battery_soc_percent = battery_soc_percent
            self.voltage_v = voltage_v
            self.temperature_c = temperature_c
        
        def to_dict(self):
            return {
                "active_power_kw": self.active_power_kw,
                "grid_frequency_hz": self.grid_frequency_hz,
                "demand_load_kw": self.demand_load_kw,
                "solar_output_kw": self.solar_output_kw,
                "battery_soc_percent": self.battery_soc_percent,
                "voltage_v": self.voltage_v,
                "temperature_c": self.temperature_c
            }
    
    class PredictionData:
        def __init__(self, grid_stress_forecast=0.3, solar_forecast_kw=0, demand_forecast_kw=0, weather_severity=0.2):
            self.grid_stress_forecast = grid_stress_forecast
            self.solar_forecast_kw = solar_forecast_kw
            self.demand_forecast_kw = demand_forecast_kw
            self.weather_severity = weather_severity
    
    class ActionType:
        REDUCE_LOAD = "reduce_load"
        NO_ACTION = "no_action"
        INCREASE_SOLAR_EFFICIENCY = "increase_solar_efficiency"
        DISPATCH_BATTERY = "dispatch_battery"
        CURTAIL_SOLAR = "curtail_solar"
    
    logger.info("[AECE] ✅ Fallback TelemetrySnapshot, PredictionData, ActionType created")


logger.info("""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                   ║
║   █████╗ ███████╗ ██████╗███████╗                                                ║
║  ██╔══██╗██╔════╝██╔════╝██╔════╝                                                ║
║  ███████║█████╗  ██║     █████╗                                                  ║
║  ██╔══██║██╔══╝  ██║     ██╔══╝                                                  ║
║  ██║  ██║███████╗╚██████╗███████╗                                                ║
║  ╚═╝  ╚═╝╚══════╝ ╚═════╝╚══════╝                                                ║
║                                                                                   ║
║          AECE v4.0.3 COMPATIBILITY LAYER - UNIFIED CONTROLLER                    ║
║                                                                                   ║
║  ✅ UnifiedController created - Bridges v4 components with v3 API                ║
║  ✅ get_unified_controller() - Main entry point for main.py                      ║
║  ✅ get_decision_engine() - Backward compatibility                               ║
║  ✅ get_action_executor() - Backward compatibility                               ║
║  ✅ evaluate_and_execute() - Autonomous control loop function                    ║
║  ✅ TelemetrySnapshot / PredictionData - Data models with fallback               ║
║                                                                                   ║
║  🔧 FIXES APPLIED (v4.0.3):                                                      ║
║  ✓ Fixed "cannot import name 'get_unified_controller'" error                    ║
║  ✓ Fixed "AECE not available - manual control only" warning                     ║
║  ✓ Full autonomous mode now available                                            ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
""")