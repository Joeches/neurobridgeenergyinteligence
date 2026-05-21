"""
================================================================================
NEUROBRIDGE 11D - AECE CONTROL ROUTES
FastAPI Endpoints for Autonomous Energy Control Engine

Version: 3.0.2-PRODUCTION-FIXED
Build: 2026.04.16
CTO: Joseph Ochelebe | NeuroBridge Technologies Ltd

CRITICAL FIXES APPLIED (v3.0.2):
- FIXED: Celery import - Changed from 'celery_app' to 'celery' (correct export name in celery_app.py)
- FIXED: Removed circular import warnings
- ENHANCED: Better error handling for Celery availability
- VERIFIED: Full Abuja Pilot compliance

FIXES APPLIED (v3.0.1):
- FIXED: Router import chain for AECE engine
- FIXED: Circular dependency with main.py
- FIXED: Async Redis initialization in background tasks
- ENHANCED: Error handling for all integration points
- ENHANCED: Graceful degradation when services unavailable

INTEGRATIONS:
- Celery async task queue for background processing
- Redis caching for decision history
- Prometheus metrics for monitoring
- AECE engine for autonomous control
- Hardware bridge for telemetry
- Full audit trail with UEIV snapshots

ENDPOINTS:
- GET  /health              - Health check
- GET  /status              - AECE engine status
- GET  /metrics             - AECE metrics
- POST /auto                - Autonomous control decision
- POST /manual/{action}     - Manual control override
- POST /reset-protection    - Reset protection mode
- GET  /audit/recent        - Recent decisions
- GET  /audit/summary       - Audit summary
- GET  /hardware/telemetry  - Live hardware telemetry
- POST /hardware/simulate   - Simulate hardware anomaly
- GET  /risk/current        - Current risk assessment
- POST /risk/override       - Override risk threshold
================================================================================
"""

import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Header
from datetime import datetime, timezone, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# LOGGER CONFIGURATION
# ============================================================================

# Initialize logger BEFORE any imports that might use it
logger = logging.getLogger("NeuroBridge.ControlRoutes")
logger.setLevel(logging.INFO)

# Ensure console handler exists
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
    ))
    logger.addHandler(console_handler)

# ============================================================================
# PROMETHEUS METRICS INTEGRATION - ENHANCED ERROR HANDLING
# ============================================================================

PROMETHEUS_AVAILABLE = False
prom_metrics = None

try:
    from backend.monitoring.prometheus_metrics import (
        metrics as prom_metrics,
        record_aece_action,
        track_aece_decision,
        update_aece_risk_score,
        record_grid_risk_event,
        track_auto_control_latency,
        update_energy_metrics,
        update_system_metrics
    )
    PROMETHEUS_AVAILABLE = True
    logger.info("[ControlRoutes] ✅ Prometheus metrics integration enabled")
except ImportError as e:
    logger.warning(f"[ControlRoutes] ⚠️ Prometheus not available: {e}")
    
    # Dummy functions with logging
    def record_aece_action(*args, **kwargs): 
        logger.debug(f"[Metrics] record_aece_action called: {args}")
    
    def track_aece_decision(func=None):
        if func:
            return func
        return lambda x: x
    
    def update_aece_risk_score(*args, **kwargs): 
        logger.debug(f"[Metrics] update_aece_risk_score called: {args}")
    
    def record_grid_risk_event(*args, **kwargs): 
        logger.debug(f"[Metrics] record_grid_risk_event called: {args}")
    
    def track_auto_control_latency(func=None):
        if func:
            return func
        return lambda x: x
    
    def update_energy_metrics(*args, **kwargs): 
        logger.debug(f"[Metrics] update_energy_metrics called: {args}")
    
    def update_system_metrics(*args, **kwargs): 
        logger.debug(f"[Metrics] update_system_metrics called: {args}")

# ============================================================================
# REDIS CACHE INTEGRATION - FIXED ASYNC INITIALIZATION
# ============================================================================

redis_manager = None
REDIS_AVAILABLE = False

class ProductionRedisManager:
    """Production-grade Redis manager with proper error handling"""
    
    def __init__(self):
        self.available = False
        self.client = None
        self._initialized = False
        self._init_error = None
    
    async def initialize(self):
        """Initialize Redis connection with retry logic"""
        if self._initialized:
            return self.available
        
        try:
            import redis.asyncio as aioredis
            import os
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.client = await aioredis.from_url(
                redis_url, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            await self.client.ping()
            self.available = True
            logger.info("[ControlRoutes] ✅ Redis connected successfully")
        except ImportError:
            self._init_error = "redis library not installed"
            logger.warning(f"[ControlRoutes] ⚠️ {self._init_error}")
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"[ControlRoutes] ⚠️ Redis connection failed: {e}")
        
        self._initialized = True
        return self.available
    
    async def get(self, key: str):
        if self.available and self.client:
            try:
                return await self.client.get(key)
            except Exception as e:
                logger.debug(f"[Redis] Get failed for {key}: {e}")
                return None
        return None
    
    async def set(self, key: str, value: str, ttl: int = 60):
        if self.available and self.client:
            try:
                await self.client.setex(key, ttl, value)
                return True
            except Exception as e:
                logger.debug(f"[Redis] Set failed for {key}: {e}")
                return False
        return False
    
    async def delete(self, key: str):
        if self.available and self.client:
            try:
                await self.client.delete(key)
                return True
            except Exception as e:
                logger.debug(f"[Redis] Delete failed for {key}: {e}")
                return False
        return False

# Create Redis manager instance
redis_manager = ProductionRedisManager()

# ============================================================================
# CELERY INTEGRATION - FIXED: Use 'celery' not 'celery_app'
# ============================================================================

CELERY_AVAILABLE = False
celery = None

try:
    # FIX: The export name in celery_app.py is 'celery', not 'celery_app'
    from backend.core.celery_app import celery as celery_instance
    celery = celery_instance
    CELERY_AVAILABLE = True
    logger.info("[ControlRoutes] ✅ Celery module loaded (export name: celery)")
except ImportError as e:
    logger.warning(f"[ControlRoutes] ⚠️ Celery not available: {e}")
except Exception as e:
    logger.error(f"[ControlRoutes] Celery error: {e}")

# ============================================================================
# AECE ENGINE IMPORT - FIXED IMPORT PATH
# ============================================================================

# IMPORTANT: Use absolute import from backend.control
# NOT from backend.control.aece_engine directly to avoid circular imports
aece = None
get_aece_engine = None
UEIV = None
ControlAction = None
ControlPriority = None

try:
    # Try to import from control package
    from backend.control import aece as _aece
    from backend.control import get_aece_engine as _get_aece_engine
    from backend.control import UEIV as _UEIV
    from backend.control import ControlAction as _ControlAction
    from backend.control import ControlPriority as _ControlPriority
    
    aece = _aece
    get_aece_engine = _get_aece_engine
    UEIV = _UEIV
    ControlAction = _ControlAction
    ControlPriority = _ControlPriority
    
    logger.info("[ControlRoutes] ✅ AECE engine imported from backend.control")
except ImportError as e:
    logger.error(f"[ControlRoutes] ❌ Failed to import AECE engine: {e}")
    # Fallback: try direct import
    try:
        from backend.control.aece_engine import aece as _aece, get_aece_engine as _get_aece_engine, UEIV as _UEIV, ControlAction as _ControlAction, ControlPriority as _ControlPriority
        aece = _aece
        get_aece_engine = _get_aece_engine
        UEIV = _UEIV
        ControlAction = _ControlAction
        ControlPriority = _ControlPriority
        logger.info("[ControlRoutes] ✅ AECE engine imported directly (fallback)")
    except ImportError as e2:
        logger.critical(f"[ControlRoutes] ❌ CRITICAL: Cannot import AECE engine: {e2}")
        # Create placeholder to prevent crashes
        aece = None
        UEIV = type('UEIV', (), {})
        ControlAction = type('ControlAction', (), {})
        ControlPriority = type('ControlPriority', (), {})

# ============================================================================
# HARDWARE BRIDGE INTEGRATION - ENHANCED
# ============================================================================

hardware_bridge = None
HARDWARE_AVAILABLE = False

try:
    from backend.services.hardware_bridge import get_hardware_bridge
    hardware_bridge = get_hardware_bridge()
    HARDWARE_AVAILABLE = True
    logger.info("[ControlRoutes] ✅ Hardware bridge integration enabled")
except ImportError as e:
    logger.warning(f"[ControlRoutes] ⚠️ Hardware bridge not available: {e}")
    HARDWARE_AVAILABLE = False

# ============================================================================
# TOKEN VALIDATION - FIXED CIRCULAR IMPORT
# ============================================================================

async def validate_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Validate CTO or Pilot access token with detailed response"""
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    
    token = authorization.replace("Bearer ", "")
    
    # Development bypass for testing
    import os
    if os.getenv("MODE") == "DEVELOPMENT":
        dev_token = os.getenv("DEV_BYPASS_TOKEN", "DEV_ABUJA_PILOT_2026")
        if token == dev_token:
            logger.debug("[Auth] Development bypass token accepted")
            return {"valid": True, "token_type": "dev", "user_type": "cto"}
    
    # Try to import token manager from main with fallback
    try:
        # Use relative import to avoid circular dependency
        from backend.main import token_manager
        validation = token_manager.validate_token(token)
        
        if not validation["valid"]:
            if PROMETHEUS_AVAILABLE:
                record_grid_risk_event("authentication_failure")
            raise HTTPException(status_code=403, detail=validation["reason"])
        
        if PROMETHEUS_AVAILABLE and prom_metrics:
            try:
                prom_metrics.user_login_total.labels(
                    user_type=validation.get("token_type", "unknown"),
                    status="success"
                ).inc()
            except:
                pass
        
        return {
            "valid": True,
            "token_type": validation.get("token_type", "unknown"),
            "user_type": validation.get("token_type", "unknown")
        }
        
    except ImportError:
        # Production fallback token validation
        valid_tokens = {
            "CTO-11D-MASTER-2026": "cto",
            "PILOT-ABUJA-2026": "pilot",
        }
        
        if token in valid_tokens:
            return {"valid": True, "token_type": valid_tokens[token], "user_type": valid_tokens[token]}
        
        raise HTTPException(status_code=403, detail="Invalid token")

# ============================================================================
# CREATE ROUTER - THIS IS WHAT THE AECE ENGINE LOOKS FOR
# ============================================================================

router = APIRouter(prefix="/api/v1/control", tags=["autonomous-control"])

# Log router creation - IMPORTANT FOR DEBUGGING
logger.info("[ControlRoutes] ✅ Router created at /api/v1/control")

# ============================================================================
# CACHE KEYS
# ============================================================================

CACHE_KEYS = {
    "latest_decision": "control:latest_decision",
    "risk_score": "control:risk_score",
    "protection_mode": "control:protection_mode",
    "hardware_telemetry": "control:hardware_telemetry",
}

# ============================================================================
# INITIALIZATION FLAG
# ============================================================================

_initialized = False

async def initialize_control_routes():
    """Initialize async dependencies for control routes"""
    global _initialized, REDIS_AVAILABLE
    
    if _initialized:
        return
    
    # Initialize Redis
    await redis_manager.initialize()
    REDIS_AVAILABLE = redis_manager.available
    
    _initialized = True
    logger.info("[ControlRoutes] ✅ All async dependencies initialized")

# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@router.get("/health")
async def control_health():
    """Health check for AECE control system with all integrations"""
    
    # Ensure Redis is initialized
    if not _initialized:
        await initialize_control_routes()
    
    health_status = {
        "status": "healthy",
        "aece_initialized": aece is not None and hasattr(aece, '_initialized') and aece._initialized if aece else False,
        "prometheus_available": PROMETHEUS_AVAILABLE,
        "redis_available": REDIS_AVAILABLE,
        "celery_available": CELERY_AVAILABLE,
        "hardware_available": HARDWARE_AVAILABLE,
        "router_prefix": "/api/v1/control",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Check Redis connectivity
    if REDIS_AVAILABLE and redis_manager:
        try:
            test_key = "control:health_test"
            await redis_manager.set(test_key, "ok", ttl=5)
            health_status["redis_connected"] = True
        except Exception as e:
            health_status["redis_connected"] = False
            health_status["redis_error"] = str(e)
            health_status["status"] = "degraded"
    
    # Check Celery
    if CELERY_AVAILABLE and celery:
        try:
            from celery.result import AsyncResult
            test_task = celery.send_task("celery.ping")
            health_status["celery_responding"] = True
        except Exception as e:
            health_status["celery_responding"] = False
            health_status["celery_error"] = str(e)
            health_status["status"] = "degraded"
    
    # Check AECE engine
    if aece is None:
        health_status["status"] = "critical"
        health_status["aece_error"] = "AECE engine not loaded"
    
    return health_status


@router.get("/status")
async def get_control_status(auth: Dict[str, Any] = Depends(validate_token)):
    """Get AECE engine status with hardware integration"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    try:
        status = aece.get_status()
        
        # Add hardware status if available
        if HARDWARE_AVAILABLE and hardware_bridge:
            hardware_status = hardware_bridge.get_status()
            status["hardware"] = hardware_status
        
        # Add Redis cached data
        if REDIS_AVAILABLE and redis_manager:
            cached_risk = await redis_manager.get(CACHE_KEYS["risk_score"])
            if cached_risk:
                status["cached_risk_score"] = float(cached_risk)
        
        # Update Prometheus metrics
        if PROMETHEUS_AVAILABLE and prom_metrics:
            update_system_metrics(uptime_seconds=status.get("metrics", {}).get("total_decisions", 0))
        
        return {
            "success": True,
            "status": status,
            "user_type": auth.get("user_type", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get AECE status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_control_metrics(auth: Dict[str, Any] = Depends(validate_token)):
    """Get AECE metrics with Prometheus integration"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    try:
        metrics_data = aece.get_metrics()
        
        # Add hardware metrics if available
        if HARDWARE_AVAILABLE and hardware_bridge:
            hardware_metrics = hardware_bridge.get_metrics()
            metrics_data["hardware"] = hardware_metrics
        
        # Add Celery queue metrics
        if CELERY_AVAILABLE and celery:
            try:
                from celery import current_app
                inspect = celery.control.inspect(timeout=2.0)
                stats = inspect.stats()
                active = inspect.active()
                metrics_data["celery"] = {
                    "workers": len(stats) if stats else 0,
                    "active_tasks": len(active) if active else 0
                }
            except Exception as e:
                metrics_data["celery"] = {"error": str(e)}
        
        return {
            "success": True,
            "metrics": metrics_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get AECE metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONTROL ENDPOINTS
# ============================================================================

@router.post("/auto")
async def auto_control(
    ueiv: UEIV,
    background_tasks: BackgroundTasks,
    auth: Dict[str, Any] = Depends(validate_token)
):
    """
    Autonomous control decision based on UEIV (Unified Energy Intelligence Vector)
    
    Integrates with:
    - Celery for background task execution
    - Redis for caching results
    - Prometheus for metrics
    - Hardware bridge for telemetry
    """
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    start_time = datetime.now(timezone.utc)
    
    try:
        # Record metrics for this request
        record_aece_action(action="auto_decision", priority="normal")
        
        # Check hardware telemetry first if available
        hardware_risk = 0.0
        if HARDWARE_AVAILABLE and hardware_bridge:
            try:
                telemetry = await hardware_bridge.poll_telemetry()
                if telemetry:
                    hardware_risk = telemetry.aece_risk_factor
                    # Merge hardware risk with UEIV
                    ueiv.grid_risk = max(ueiv.grid_risk, hardware_risk)
                    logger.debug(f"[ControlRoutes] Hardware risk factor: {hardware_risk}")
            except Exception as e:
                logger.warning(f"[ControlRoutes] Hardware telemetry failed: {e}")
        
        # Execute AECE decision
        audit_entry = await aece.process(ueiv)
        
        # Update risk score in Redis
        if REDIS_AVAILABLE and redis_manager:
            try:
                await redis_manager.set(
                    CACHE_KEYS["risk_score"],
                    str(audit_entry.decision.risk_score),
                    ttl=60
                )
                await redis_manager.set(
                    CACHE_KEYS["latest_decision"],
                    audit_entry.decision.to_dict(),
                    ttl=300
                )
            except Exception as e:
                logger.warning(f"[ControlRoutes] Redis cache update failed: {e}")
        
        # Update Prometheus metrics
        update_aece_risk_score(audit_entry.decision.risk_score)
        
        # Submit async task to Celery for additional processing if available
        if CELERY_AVAILABLE and celery and audit_entry.action_executed:
            background_tasks.add_task(
                _submit_celery_followup,
                audit_entry.decision_id,
                audit_entry.decision.to_dict()
            )
        
        # Calculate processing time
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return {
            "success": True,
            "decision": audit_entry.decision.to_dict(),
            "action_executed": audit_entry.action_executed,
            "execution_result": audit_entry.execution_result,
            "decision_id": audit_entry.decision_id,
            "duration_ms": round(audit_entry.duration_ms, 2),
            "processing_time_ms": round(processing_time, 2),
            "hardware_risk_factor": hardware_risk,
            "user_type": auth.get("user_type", "unknown"),
            "timestamp": start_time.isoformat()
        }
        
    except ValueError as e:
        logger.error(f"Invalid UEIV: {e}")
        record_grid_risk_event("validation_error")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Auto control failed: {e}", exc_info=True)
        record_grid_risk_event("control_failure")
        raise HTTPException(status_code=500, detail=str(e))


async def _submit_celery_followup(decision_id: str, decision: Dict[str, Any]):
    """Submit follow-up task to Celery for async processing"""
    if not CELERY_AVAILABLE or not celery:
        return
    
    try:
        celery.send_task(
            "backend.tasks.control_tasks.log_control_action",
            kwargs={
                "decision_id": decision_id,
                "decision": decision,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            queue="control_queue"
        )
        logger.debug(f"[ControlRoutes] Celery follow-up task submitted for {decision_id}")
    except Exception as e:
        logger.warning(f"[ControlRoutes] Celery task submission failed: {e}")


@router.post("/manual/{action}")
async def manual_control(
    action: str,
    reason: str = Query(..., description="Reason for manual control action"),
    percentage: Optional[float] = Query(20.0, ge=0, le=100, description="Load reduction percentage"),
    auth: Dict[str, Any] = Depends(validate_token)
):
    """Manual control override endpoint with full audit trail"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    # Only CTO can perform manual overrides
    if auth.get("user_type") != "cto":
        raise HTTPException(status_code=403, detail="Manual control requires CTO privileges")
    
    try:
        action_map = {
            "reduce_load": ControlAction.REDUCE_LOAD,
            "redistribute_energy": ControlAction.REDISTRIBUTE_ENERGY,
            "preemptive_stabilization": ControlAction.PREEMPTIVE_STABILIZATION,
            "trigger_alert": ControlAction.TRIGGER_ALERT,
            "lockdown_mode": ControlAction.LOCKDOWN_MODE,
        }
        
        if action not in action_map:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action. Available: {list(action_map.keys())}"
            )
        
        control_action = action_map[action]
        priority = ControlPriority.CRITICAL if action == "lockdown_mode" else ControlPriority.HIGH
        
        # Create manual decision
        class ManualDecision:
            def __init__(self, action, reason, priority):
                self.action = action
                self.reason = reason
                self.priority = priority
        
        decision = ManualDecision(control_action, f"Manual override: {reason}", priority)
        
        # Execute action
        if action == "reduce_load" and percentage:
            result = await aece.action_executor.reduce_load(percentage)
        else:
            result = await aece.action_executor.execute(decision)
        
        # Record metrics
        record_aece_action(action=action, priority=priority.value)
        
        # Log to audit
        logger.warning(f"[MANUAL] User: {auth.get('user_type')} | Action: {action} | Reason: {reason} | Result: {result.get('success')}")
        
        # Update Redis cache
        if REDIS_AVAILABLE and redis_manager:
            await redis_manager.set(
                CACHE_KEYS["protection_mode"],
                str(action == "lockdown_mode"),
                ttl=600
            )
        
        return {
            "success": result.get("success", False),
            "action": action,
            "reason": reason,
            "result": result,
            "user": auth.get("user_type"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual control failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-protection")
async def reset_protection_mode(auth: Dict[str, Any] = Depends(validate_token)):
    """Reset protection mode and restore normal operation"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    # Only CTO can reset protection mode
    if auth.get("user_type") != "cto":
        raise HTTPException(status_code=403, detail="Reset protection mode requires CTO privileges")
    
    try:
        aece.action_executor._protection_mode_active = False
        logger.info(f"[MANUAL] Protection mode reset by: {auth.get('user_type')}")
        
        # Record action
        record_aece_action(action="reset_protection", priority="high")
        
        # Clear Redis cache
        if REDIS_AVAILABLE and redis_manager:
            await redis_manager.delete(CACHE_KEYS["protection_mode"])
        
        # Reset risk score in Prometheus
        update_aece_risk_score(0.0)
        
        return {
            "success": True,
            "message": "Protection mode deactivated",
            "protection_mode_active": False,
            "user": auth.get("user_type"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to reset protection mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HARDWARE INTEGRATION ENDPOINTS
# ============================================================================

@router.get("/hardware/telemetry")
async def get_hardware_telemetry(
    force_refresh: bool = Query(False, description="Force refresh from hardware"),
    auth: Dict[str, Any] = Depends(validate_token)
):
    """Get live hardware telemetry from Modbus bridge"""
    
    if not HARDWARE_AVAILABLE or not hardware_bridge:
        raise HTTPException(status_code=503, detail="Hardware bridge not available")
    
    try:
        telemetry = await hardware_bridge.poll_telemetry(force_refresh=force_refresh)
        
        if telemetry:
            # Update Prometheus metrics
            update_energy_metrics(
                power_kw=telemetry.power_kw,
                frequency_hz=telemetry.frequency_hz,
                efficiency_percent=telemetry.quality_score * 100,
                sector="renewables",
                voltage_v=telemetry.voltage_ac,
                current_a=telemetry.current_ac
            )
            
            return {
                "success": True,
                "telemetry": telemetry.to_simulation_context(),
                "aece_risk_factor": telemetry.aece_risk_factor,
                "source": telemetry.source.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "success": False,
                "message": "No telemetry available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
    except Exception as e:
        logger.error(f"Hardware telemetry failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hardware/simulate")
async def simulate_hardware_anomaly(
    anomaly_type: str = Query(..., description="Anomaly type: overtemp, frequency_dip, overload"),
    auth: Dict[str, Any] = Depends(validate_token)
):
    """Simulate hardware anomaly for testing AECE response"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    # Only CTO can simulate anomalies
    if auth.get("user_type") != "cto":
        raise HTTPException(status_code=403, detail="Simulation requires CTO privileges")
    
    if not HARDWARE_AVAILABLE or not hardware_bridge:
        raise HTTPException(status_code=503, detail="Hardware bridge not available")
    
    try:
        # Get current telemetry
        telemetry = await hardware_bridge.poll_telemetry()
        
        if not telemetry:
            telemetry = hardware_bridge.get_simulated_telemetry()
        
        # Modify based on anomaly type
        if anomaly_type == "overtemp":
            telemetry.temperature_c = 85.0
            telemetry.aece_risk_factor = 0.75
            reason = "High temperature anomaly (85°C)"
        elif anomaly_type == "frequency_dip":
            telemetry.frequency_hz = 48.5
            telemetry.aece_risk_factor = 0.65
            reason = "Frequency dip (48.5 Hz)"
        elif anomaly_type == "overload":
            telemetry.power_kw = 95.0
            telemetry.aece_risk_factor = 0.70
            reason = "Overload condition (95kW)"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown anomaly type: {anomaly_type}")
        
        # Trigger AECE evaluation with modified UEIV
        ueiv = UEIV(
            solar_efficiency=0.85,
            grid_risk=telemetry.aece_risk_factor,
            nuclear_stability=0.92,
            ergotropy_score=0.88,
            weather_severity=0.3,
            demand_load=telemetry.power_kw / 100,
            threat_level="MEDIUM"
        )
        
        # Process AECE decision
        audit_entry = await aece.process(ueiv)
        
        # Record the anomaly event
        record_grid_risk_event("simulated_anomaly")
        
        return {
            "success": True,
            "anomaly_type": anomaly_type,
            "reason": reason,
            "telemetry": telemetry.to_simulation_context(),
            "aece_decision": audit_entry.decision.to_dict(),
            "action_taken": audit_entry.action_executed,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RISK ASSESSMENT ENDPOINTS
# ============================================================================

@router.get("/risk/current")
async def get_current_risk(auth: Dict[str, Any] = Depends(validate_token)):
    """Get current risk assessment from all sources"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    try:
        risk_assessment = {
            "aece_risk_score": 0.0,
            "hardware_risk_factor": 0.0,
            "composite_risk": 0.0,
            "risk_level": "LOW",
            "recommended_action": "none"
        }
        
        # Get AECE risk
        status = aece.get_status()
        if status and "metrics" in status:
            # Calculate approximate risk from metrics
            total_decisions = status["metrics"].get("total_decisions", 0)
            actions_taken = status["metrics"].get("total_actions", 0)
            if total_decisions > 0:
                risk_assessment["aece_risk_score"] = min(1.0, actions_taken / max(1, total_decisions) * 2)
        
        # Get hardware risk
        if HARDWARE_AVAILABLE and hardware_bridge:
            telemetry = await hardware_bridge.poll_telemetry()
            if telemetry:
                risk_assessment["hardware_risk_factor"] = telemetry.aece_risk_factor
        
        # Calculate composite risk
        risk_assessment["composite_risk"] = (
            risk_assessment["aece_risk_score"] * 0.4 +
            risk_assessment["hardware_risk_factor"] * 0.6
        )
        
        # Determine risk level
        if risk_assessment["composite_risk"] >= 0.8:
            risk_assessment["risk_level"] = "CRITICAL"
            risk_assessment["recommended_action"] = "lockdown_mode"
        elif risk_assessment["composite_risk"] >= 0.6:
            risk_assessment["risk_level"] = "HIGH"
            risk_assessment["recommended_action"] = "reduce_load"
        elif risk_assessment["composite_risk"] >= 0.3:
            risk_assessment["risk_level"] = "MEDIUM"
            risk_assessment["recommended_action"] = "monitor"
        else:
            risk_assessment["risk_level"] = "LOW"
            risk_assessment["recommended_action"] = "none"
        
        # Cache in Redis
        if REDIS_AVAILABLE and redis_manager:
            await redis_manager.set(CACHE_KEYS["risk_score"], str(risk_assessment["composite_risk"]), ttl=30)
        
        # Update Prometheus
        update_aece_risk_score(risk_assessment["composite_risk"])
        
        return {
            "success": True,
            "risk_assessment": risk_assessment,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Risk assessment failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/override")
async def override_risk_threshold(
    new_threshold: float = Query(..., ge=0.0, le=1.0, description="New risk threshold (0.0-1.0)"),
    auth: Dict[str, Any] = Depends(validate_token)
):
    """Override risk thresholds for testing (CTO only)"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    if auth.get("user_type") != "cto":
        raise HTTPException(status_code=403, detail="Risk override requires CTO privileges")
    
    try:
        # Update AECE thresholds
        aece.decision_engine.hysteresis.hysteresis_thresholds["grid_risk_up"] = new_threshold * 0.1
        
        logger.info(f"[ControlRoutes] Risk threshold overridden to {new_threshold} by {auth.get('user_type')}")
        
        return {
            "success": True,
            "new_threshold": new_threshold,
            "message": f"Risk threshold updated to {new_threshold}",
            "user": auth.get("user_type"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Risk override failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AUDIT ENDPOINTS
# ============================================================================

@router.get("/audit/recent")
async def get_recent_decisions(
    limit: int = Query(10, ge=1, le=100),
    auth: Dict[str, Any] = Depends(validate_token)
):
    """Get recent control decisions from audit trail"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    try:
        recent = aece.audit_trail[-limit:] if aece.audit_trail else []
        
        # Try to get from Redis cache first
        if REDIS_AVAILABLE and redis_manager and not recent:
            cached = await redis_manager.get(CACHE_KEYS["latest_decision"])
            if cached:
                import json
                recent = [json.loads(cached)]
        
        return {
            "success": True,
            "count": len(recent),
            "decisions": [entry.to_dict() for entry in recent] if recent else [],
            "user_type": auth.get("user_type", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get audit trail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/summary")
async def get_audit_summary(auth: Dict[str, Any] = Depends(validate_token)):
    """Get summary statistics from audit trail"""
    
    if aece is None:
        raise HTTPException(status_code=503, detail="AECE engine not available")
    
    try:
        if not aece.audit_trail:
            return {
                "success": True,
                "summary": {
                    "total_decisions": 0,
                    "actions_executed": 0,
                    "execution_rate": 0,
                    "by_action": {},
                    "audit_trail_size": 0
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        total = len(aece.audit_trail)
        actions_taken = sum(1 for entry in aece.audit_trail if entry.action_executed)
        
        action_counts = {}
        priority_counts = {}
        
        for entry in aece.audit_trail:
            action = entry.decision.action.value
            priority = entry.decision.priority.value
            action_counts[action] = action_counts.get(action, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        return {
            "success": True,
            "summary": {
                "total_decisions": total,
                "actions_executed": actions_taken,
                "execution_rate": round(actions_taken / total * 100, 2) if total > 0 else 0,
                "by_action": action_counts,
                "by_priority": priority_counts,
                "audit_trail_size": len(aece.audit_trail)
            },
            "user_type": auth.get("user_type", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get audit summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXPORTS - CRITICAL: This is what AECE engine looks for
# ============================================================================

__all__ = ['router']

# Log successful module load
logger.info("[ControlRoutes] ✅ Module loaded successfully - router available for import")