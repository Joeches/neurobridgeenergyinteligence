# backend/api/demo_routes.py - PRODUCTION CLEAN v2.1.1
# Investor Demo Routes - Self-contained, no circular imports
# Fixed: Safe environment variable validation

import asyncio
import logging
import time
import uuid
import random
import os
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ============================================================================
# LOGGER - SINGLE CONCISE INITIALIZATION
# ============================================================================

logger = logging.getLogger("NeuroBridge.DemoRoutes")
logger.info("[DEMO] routes initialized endpoints=9")

# ============================================================================
# LOCAL CONFIGURATION - NO IMPORTS FROM BACKEND.MAIN
# ============================================================================

ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
IS_DEVELOPMENT = ENVIRONMENT in ["development", "dev", "local"]
IS_STAGING = ENVIRONMENT in ["staging", "stage"]
IS_PRODUCTION = ENVIRONMENT in ["production", "prod"]

DEV_BYPASS_TOKEN = os.getenv("DEV_BYPASS_TOKEN", "DEV_ABUJA_PILOT_2026")
DEMO_ENABLED = os.getenv("DEMO_ENABLED", "true").lower() == "true"

CTO_TOKEN_PATTERN = re.compile(r'^CTO-[A-F0-9]{4,8}(-[A-F0-9]{4,8}){2,4}$', re.IGNORECASE)
PILOT_TOKEN_PATTERN = re.compile(r'^PILOT-[A-F0-9]{4,8}(-[A-F0-9]{4,8}){1,3}$', re.IGNORECASE)

CTO_ACCESS_CODE = os.getenv("CTO_ACCESS_CODE", "")
NEUROBRIDGE_API_KEY = os.getenv("NEUROBRIDGE_API_KEY", "")
CTO_API_KEY = os.getenv("CTO_API_KEY", "")
API_KEY = os.getenv("API_KEY", "")

# ============================================================================
# LOCAL ANALYTICS
# ============================================================================

class LocalAnalytics:
    def __init__(self):
        self._counters: Dict[str, int] = {}
    
    def increment(self, key: str, value: int = 1):
        self._counters[key] = self._counters.get(key, 0) + value
    
    def get(self, key: str, default: int = 0) -> int:
        return self._counters.get(key, default)


_analytics = LocalAnalytics()

# ============================================================================
# API KEY MANAGER INTEGRATION - FOR INVESTOR DEMO ACCESS
# ============================================================================

def _validate_with_api_key_manager(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate token using the API key manager.
    Returns client info if valid, None otherwise.
    """
    try:
        from backend.core.api_key_manager import get_api_key_manager
        
        manager = get_api_key_manager()
        client = manager.verify_key(token)
        
        if client:
            plan_value = getattr(client, 'plan', None)
            plan_str = plan_value.value if hasattr(plan_value, 'value') else str(plan_value) if plan_value else ""
            
            # Accept investor_demo, enterprise, and cto plans
            if plan_str in ["investor_demo", "enterprise", "cto"]:
                return {
                    "valid": True,
                    "auth_type": "api_key",
                    "client_id": client.client_id,
                    "plan": plan_str
                }
        return None
    except ImportError:
        logger.debug("API key manager not available")
        return None
    except Exception as e:
        logger.debug(f"API key manager validation error: {type(e).__name__}")
        return None


def _validate_local_token(token: Optional[str]) -> Tuple[bool, str, str, Dict]:
    """
    Validate token using local methods with safe empty checks.
    Returns (is_valid, token_type, message, extra_data)
    """
    if not token:
        return False, "", "No token provided", {}
    
    # Safe check for CTO_ACCESS_CODE (non-empty)
    if CTO_ACCESS_CODE and token == CTO_ACCESS_CODE:
        if CTO_TOKEN_PATTERN.match(CTO_ACCESS_CODE):
            return True, "cto", "Valid CTO token", {"plan": "cto"}
    
    # Safe check for CTO_API_KEY (non-empty)
    if CTO_API_KEY and token == CTO_API_KEY:
        return True, "cto", "Valid CTO API key", {"plan": "cto"}
    
    # Safe check for NEUROBRIDGE_API_KEY (non-empty)
    if NEUROBRIDGE_API_KEY and token == NEUROBRIDGE_API_KEY:
        return True, "api_key", "Valid NeuroBridge API key", {"plan": "enterprise"}
    
    # Safe check for API_KEY (non-empty)
    if API_KEY and token == API_KEY:
        return True, "api_key", "Valid API key", {"plan": "enterprise"}
    
    # Check pilot token pattern
    if PILOT_TOKEN_PATTERN.match(token):
        return True, "pilot", "Valid pilot token", {"plan": "investor_demo"}
    
    # Development bypass
    if IS_DEVELOPMENT and token == DEV_BYPASS_TOKEN:
        return True, "developer", "Development bypass", {"plan": "dev"}
    
    return False, "", "Invalid token", {}


# ============================================================================
# ENHANCED AUTHENTICATION DEPENDENCY FOR DEMO ACCESS
# ============================================================================

async def require_demo_access(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_lattice_token: Optional[str] = Header(None, alias="X-Lattice-Token"),
) -> Dict[str, Any]:
    """
    Authentication dependency for demo endpoints that should be accessible to:
    - CTO tokens
    - Investor demo API keys
    - Enterprise API keys
    - Pilot tokens
    - Development bypass tokens (dev mode only)
    
    Returns auth_info dict with user_type and plan information.
    Raises HTTP 403 on failure.
    """
    # Extract token from various headers
    token = None
    
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token and x_api_key:
        token = x_api_key
    if not token and x_lattice_token:
        token = x_lattice_token
    
    # Development mode - allow open access for testing
    if IS_DEVELOPMENT:
        if not token:
            _analytics.increment("auth:dev_no_token")
            logger.debug(f"[AUTH] DEV MODE: No token for {request.url.path}")
            return {
                "authenticated": True,
                "mode": "DEVELOPMENT_OPEN",
                "user_type": "anonymous_dev",
                "plan": "dev",
                "phase": "PHASE_1_PRODUCTION"
            }
        if token == DEV_BYPASS_TOKEN:
            _analytics.increment("auth:dev_bypass")
            return {
                "authenticated": True,
                "mode": "DEVELOPMENT_BYPASS",
                "user_type": "developer",
                "plan": "dev",
                "phase": "PHASE_1_PRODUCTION"
            }
    
    # Try API Key Manager first (supports investor_demo, enterprise, cto)
    api_key_result = _validate_with_api_key_manager(token)
    if api_key_result:
        _analytics.increment("auth:api_key_success")
        return {
            "authenticated": True,
            "mode": "PRODUCTION",
            "user_type": "api_client",
            "plan": api_key_result.get("plan", "investor_demo"),
            "client_id": api_key_result.get("client_id"),
            "phase": "PHASE_1_PRODUCTION"
        }
    
    # Try local token validation (CTO, pilot, etc.)
    is_valid, token_type, message, extra = _validate_local_token(token)
    
    if is_valid:
        _analytics.increment("auth:token_success")
        return {
            "authenticated": True,
            "mode": "PRODUCTION" if IS_PRODUCTION else ("STAGING" if IS_STAGING else "DEVELOPMENT"),
            "user_type": token_type,
            "plan": extra.get("plan", "unknown"),
            "phase": "PHASE_1_PRODUCTION"
        }
    
    # Authentication failed
    _analytics.increment("auth:failed")
    logger.debug(f"[AUTH] Failed authentication for {request.url.path}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "Authentication required",
            "message": "Valid CTO token or investor API key required",
            "phase": "PHASE_1_PRODUCTION"
        }
    )


async def require_cto_access(
    auth_info: Dict[str, Any] = Depends(require_demo_access),
) -> bool:
    """
    Require CTO-level access for admin operations.
    """
    user_type = auth_info.get("user_type", "")
    plan = auth_info.get("plan", "")
    
    # Allow CTO token users
    if user_type == "cto":
        return True
    
    # Allow enterprise API keys
    if plan == "enterprise" or plan == "cto":
        return True
    
    # Allow development mode
    if IS_DEVELOPMENT and auth_info.get("mode") in ["DEVELOPMENT_OPEN", "DEVELOPMENT_BYPASS"]:
        return True
    
    _analytics.increment("auth:cto_required_failed")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "CTO access required",
            "message": "This operation requires CTO-level privileges",
            "phase": "PHASE_1_PRODUCTION"
        }
    )

# ============================================================================
# DEMO SESSION MANAGER
# ============================================================================

class DemoSessionManager:
    """Manages active investor demo sessions"""
    
    def __init__(self):
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._session_history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._demo_records: List[Dict[str, Any]] = []
        self._showcase_counter = 0
        
    async def start_session(self, session_id: str, demo_type: str = "standard", parameters: Dict = None) -> Dict[str, Any]:
        async with self._lock:
            if session_id in self._active_sessions:
                return {"success": False, "error": "Session already active", "session_id": session_id}
            
            session = {
                "session_id": session_id,
                "demo_type": demo_type,
                "parameters": parameters or {},
                "start_time": datetime.now(timezone.utc).isoformat(),
                "status": "running",
                "decisions_made": 0,
                "actions_taken": 0,
                "telemetry_samples": []
            }
            self._active_sessions[session_id] = session
            return {"success": True, "session": session}
    
    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        async with self._lock:
            if session_id not in self._active_sessions:
                return {"success": False, "error": "Session not found", "session_id": session_id}
            
            session = self._active_sessions.pop(session_id)
            session["end_time"] = datetime.now(timezone.utc).isoformat()
            session["status"] = "completed"
            session["duration_seconds"] = (
                datetime.fromisoformat(session["end_time"]) - 
                datetime.fromisoformat(session["start_time"])
            ).total_seconds()
            self._session_history.append(session)
            
            return {"success": True, "session": session}
    
    async def get_session_status(self, session_id: str = None) -> Dict[str, Any]:
        if session_id:
            if session_id in self._active_sessions:
                return {"success": True, "session": self._active_sessions[session_id], "active": True}
            for session in self._session_history:
                if session.get("session_id") == session_id:
                    return {"success": True, "session": session, "active": False}
            return {"success": False, "error": "Session not found"}
        
        return {
            "success": True,
            "active_sessions": list(self._active_sessions.values()),
            "total_sessions": len(self._session_history),
            "active_count": len(self._active_sessions)
        }
    
    async def record_decision(self, session_id: str, decision: Dict[str, Any], telemetry: Dict[str, Any]) -> None:
        async with self._lock:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["decisions_made"] += 1
                if decision.get("action_executed"):
                    self._active_sessions[session_id]["actions_taken"] += 1
                self._active_sessions[session_id]["telemetry_samples"].append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "telemetry": telemetry,
                    "decision": decision
                })
                if len(self._active_sessions[session_id]["telemetry_samples"]) > 100:
                    self._active_sessions[session_id]["telemetry_samples"] = \
                        self._active_sessions[session_id]["telemetry_samples"][-100:]
    
    async def add_demo_record(self, record: Dict[str, Any]) -> None:
        self._showcase_counter += 1
        record["recorded_at"] = datetime.now(timezone.utc).isoformat()
        record["showcase_number"] = self._showcase_counter
        self._demo_records.append(record)
        if len(self._demo_records) > 1000:
            self._demo_records = self._demo_records[-1000:]
    
    async def get_demo_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._demo_records[-limit:] if limit > 0 else self._demo_records
    
    async def generate_report(self, session_id: str = None, include_telemetry: bool = False) -> Dict[str, Any]:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "PHASE_1_PRODUCTION",
            "version": "2.1.1"
        }
        
        if session_id:
            session = None
            if session_id in self._active_sessions:
                session = self._active_sessions[session_id]
            else:
                for s in self._session_history:
                    if s.get("session_id") == session_id:
                        session = s
                        break
            
            if session:
                report["session"] = {
                    "session_id": session.get("session_id"),
                    "demo_type": session.get("demo_type"),
                    "start_time": session.get("start_time"),
                    "end_time": session.get("end_time"),
                    "duration_seconds": session.get("duration_seconds", 
                        (datetime.now(timezone.utc) - datetime.fromisoformat(session["start_time"])).total_seconds() 
                        if session.get("status") == "running" else 0),
                    "status": session.get("status"),
                    "decisions_made": session.get("decisions_made", 0),
                    "actions_taken": session.get("actions_taken", 0),
                    "decision_rate_per_minute": round(
                        session.get("decisions_made", 0) / max(
                            (session.get("duration_seconds", 1) / 60), 0.1
                        ), 2
                    )
                }
                if include_telemetry and session.get("telemetry_samples"):
                    report["telemetry_samples"] = session["telemetry_samples"][-20:]
        else:
            report["summary"] = {
                "total_sessions": len(self._session_history),
                "active_sessions": len(self._active_sessions),
                "total_decisions": sum(s.get("decisions_made", 0) for s in self._session_history),
                "total_actions": sum(s.get("actions_taken", 0) for s in self._session_history),
                "showcase_records": len(self._demo_records)
            }
            
            if self._session_history:
                durations = [s.get("duration_seconds", 0) for s in self._session_history]
                report["summary"]["avg_session_duration_seconds"] = round(sum(durations) / len(durations), 2)
                report["summary"]["total_demo_time_hours"] = round(sum(durations) / 3600, 2)
        
        return report
    
    def reset(self):
        self._active_sessions.clear()
        self._session_history.clear()
        self._demo_records.clear()
        self._showcase_counter = 0


demo_manager = DemoSessionManager()

# ============================================================================
# SHOWCASE SCENARIOS
# ============================================================================

SHOWCASE_SCENARIOS = {
    "stable": {
        "description": "Normal grid operations",
        "solar_output_kw": [150, 160, 155, 165, 170, 158, 162, 168],
        "grid_frequency_hz": [50.02, 50.01, 50.03, 50.00, 50.02, 50.01, 50.03, 50.00],
        "demand_load_kw": [900, 950, 920, 880, 910, 940, 930, 895],
        "cloud_cover_percent": [20, 25, 22, 18, 23, 21, 24, 19],
        "expected_action": "no_action"
    },
    "volatile": {
        "description": "Volatile grid conditions",
        "solar_output_kw": [120, 80, 140, 60, 130, 90, 110, 70],
        "grid_frequency_hz": [49.8, 50.1, 49.7, 50.2, 49.9, 50.05, 49.85, 50.15],
        "demand_load_kw": [1100, 1300, 1050, 1400, 1150, 1250, 1080, 1350],
        "cloud_cover_percent": [40, 65, 35, 70, 45, 55, 38, 68],
        "expected_action": "reduce_load"
    },
    "critical": {
        "description": "Critical grid conditions",
        "solar_output_kw": [40, 35, 45, 30, 50, 38, 42, 33],
        "grid_frequency_hz": [49.2, 49.1, 49.3, 49.0, 49.2, 49.15, 49.25, 49.05],
        "demand_load_kw": [1800, 1900, 1750, 1950, 1850, 1880, 1780, 1920],
        "cloud_cover_percent": [85, 90, 82, 88, 86, 89, 83, 87],
        "expected_action": "lockdown_mode"
    },
    "mixed": {
        "description": "Mixed conditions",
        "solar_output_kw": [160, 90, 145, 55, 170, 80, 150, 45, 165, 85],
        "grid_frequency_hz": [50.02, 49.8, 50.01, 49.5, 50.03, 49.7, 50.00, 49.3, 50.01, 49.6],
        "demand_load_kw": [850, 1200, 950, 1600, 880, 1400, 920, 1750, 890, 1300],
        "cloud_cover_percent": [15, 55, 25, 80, 18, 60, 22, 85, 16, 58],
        "expected_action": "mixed"
    }
}

# ============================================================================
# DEMO TELEMETRY LOOP
# ============================================================================

async def _run_demo_telemetry_loop(session_id: str, demo_type: str, duration_minutes: int):
    """Background task that generates telemetry and decisions for active demo."""
    end_time = time.time() + (duration_minutes * 60)
    iteration = 0
    
    while time.time() < end_time:
        try:
            iteration += 1
            
            if demo_type == "stress":
                solar = 50 + random.randint(-30, 80)
                freq = 49.8 + random.uniform(-0.3, 0.5)
                demand = 1500 + random.randint(-400, 500)
                cloud = 50 + random.randint(-30, 40)
            elif demo_type == "performance":
                solar = 120 + random.randint(-20, 40)
                freq = 50.0 + random.uniform(-0.1, 0.1)
                demand = 1000 + random.randint(-100, 150)
                cloud = 25 + random.randint(-10, 20)
            else:
                solar = 100 + random.randint(-40, 60)
                freq = 50.0 + random.uniform(-0.2, 0.2)
                demand = 1200 + random.randint(-200, 300)
                cloud = 35 + random.randint(-20, 30)
            
            telemetry = {
                "solar_output_kw": max(0, min(200, solar)),
                "grid_frequency_hz": max(49.0, min(51.0, freq)),
                "demand_load_kw": max(500, min(2000, demand)),
                "cloud_cover_percent": max(0, min(100, cloud)),
                "battery_soc_percent": random.randint(20, 90),
                "temperature_c": 28 + random.uniform(-5, 8),
                "irradiance_wm2": max(100, min(1200, 800 + random.randint(-300, 300)))
            }
            
            decision = {"action": "monitor", "risk_score": random.uniform(0.05, 0.3), "reason": "Demo mode"}
            await demo_manager.record_decision(session_id, decision, telemetry)
            
            await asyncio.sleep(random.uniform(2, 5))
            
        except Exception:
            await asyncio.sleep(5)
    
    await demo_manager.stop_session(session_id)

# ============================================================================
# LAZY AECE IMPORT FOR BACKWARD COMPATIBILITY
# ============================================================================

_AECE_AVAILABLE = None


async def _get_aece_decision(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """Get AECE decision with lazy import."""
    try:
        from backend.control.aece_engine import evaluate_and_execute_telemetry
        return await evaluate_and_execute_telemetry(telemetry, execute=False)
    except ImportError:
        return {"action": "monitor", "risk_score": 0.15, "reason": "AECE not available"}
    except Exception:
        return {"action": "monitor", "risk_score": 0.10, "reason": "Error in decision"}

# ============================================================================
# FASTAPI ROUTER - PREFIX HANDLED IN MAIN.PY (/api/v1/demo)
# ============================================================================

router = APIRouter(tags=["Investor Demo"])


@router.get("/health")
async def demo_health() -> Dict[str, Any]:
    """Health check for demo routes."""
    return {
        "status": "ok",
        "service": "investor_demo",
        "demo_enabled": DEMO_ENABLED,
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/status")
async def demo_status(
    session_id: Optional[str] = Query(None),
    auth_info: Dict[str, Any] = Depends(require_demo_access)
):
    """Get status of demo session(s)."""
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    _analytics.increment("demo:status")
    
    result = await demo_manager.get_session_status(session_id)
    
    if result["success"]:
        return {
            "success": True,
            "data": result,
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    return result


@router.get("/scenarios")
async def list_scenarios(
    auth_info: Dict[str, Any] = Depends(require_demo_access)
):
    """Get list of available showcase scenarios with their descriptions."""
    scenarios = []
    for name, config in SHOWCASE_SCENARIOS.items():
        scenarios.append({
            "name": name,
            "description": config["description"],
            "expected_action": config["expected_action"],
            "data_points": len(config["solar_output_kw"])
        })
    
    return {
        "success": True,
        "scenarios": scenarios,
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/showcase")
async def demo_showcase(
    showcase_type: str = Query("full"),
    duration_seconds: int = Query(60, ge=10, le=600),
    scenario: str = Query("mixed"),
    auth_info: Dict[str, Any] = Depends(require_demo_access)  # Now accepts investor API keys
):
    """
    Run a pre-configured investor showcase.
    Demonstrates autonomous energy control capabilities with preset scenarios.
    Accessible to: CTO tokens, investor_demo API keys, enterprise API keys, pilot tokens.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    _analytics.increment("demo:showcase")
    
    showcase_id = f"showcase_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}"
    
    selected = SHOWCASE_SCENARIOS.get(scenario, SHOWCASE_SCENARIOS["mixed"])
    showcase_record = {
        "showcase_id": showcase_id,
        "type": showcase_type,
        "scenario": scenario,
        "description": selected["description"],
        "duration_seconds": duration_seconds,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "decisions": []
    }
    
    try:
        telemetry_count = min(duration_seconds // 5, len(selected["solar_output_kw"]))
        if telemetry_count < 1:
            telemetry_count = 1
        
        for i in range(telemetry_count):
            idx = i % len(selected["solar_output_kw"])
            telemetry = {
                "solar_output_kw": selected["solar_output_kw"][idx],
                "grid_frequency_hz": selected["grid_frequency_hz"][idx],
                "demand_load_kw": selected["demand_load_kw"][idx],
                "cloud_cover_percent": selected["cloud_cover_percent"][idx],
                "battery_soc_percent": random.randint(30, 80),
                "temperature_c": random.uniform(25, 35)
            }
            
            decision = await _get_aece_decision(telemetry)
            
            showcase_record["decisions"].append({
                "step": i + 1,
                "telemetry": telemetry,
                "decision": {
                    "action": decision.get("action"),
                    "risk_score": decision.get("risk_score"),
                    "reason": decision.get("reason", "")[:100]
                }
            })
            
            await asyncio.sleep(0.1)
        
        showcase_record["ended_at"] = datetime.now(timezone.utc).isoformat()
        showcase_record["total_decisions"] = len(showcase_record["decisions"])
        
        actions = list({d["decision"]["action"] for d in showcase_record["decisions"] if d["decision"].get("action")})
        risk_scores = [d["decision"]["risk_score"] for d in showcase_record["decisions"] if d["decision"].get("risk_score")]
        
        showcase_record["summary"] = {
            "unique_actions": actions,
            "avg_risk_score": round(sum(risk_scores) / len(risk_scores), 3) if risk_scores else 0,
            "max_risk_score": max(risk_scores) if risk_scores else 0,
            "min_risk_score": min(risk_scores) if risk_scores else 0
        }
        
        await demo_manager.add_demo_record(showcase_record)
        
        return {
            "success": True,
            "message": "Investor showcase completed",
            "showcase_id": showcase_id,
            "scenario": scenario,
            "total_decisions": len(showcase_record["decisions"]),
            "summary": showcase_record["summary"],
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[DEMO] Showcase failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "showcase_id": showcase_id,
            "phase": "PHASE_1_PRODUCTION"
        }


@router.get("/showcases")
async def list_showcases(
    limit: int = Query(50, ge=1, le=200),
    _cto_check: bool = Depends(require_cto_access)
):
    """
    Get list of previously run showcase records.
    CTO access only.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    records = await demo_manager.get_demo_records(limit)
    
    return {
        "success": True,
        "total_records": len(records),
        "records": records,
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/start")
async def demo_start(
    demo_type: str = Query("standard"),
    duration_minutes: int = Query(30, ge=1, le=120),
    _cto_check: bool = Depends(require_cto_access)
):
    """
    Start an investor demo session.
    CTO access only.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    _analytics.increment("demo:start")
    
    session_id = f"demo_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    
    parameters = {"duration_minutes": duration_minutes, "demo_type": demo_type, "started_by": "cto"}
    
    result = await demo_manager.start_session(session_id, demo_type, parameters)
    
    if result["success"]:
        asyncio.create_task(_run_demo_telemetry_loop(session_id, demo_type, duration_minutes))
        
        return {
            "success": True,
            "session_id": session_id,
            "demo_type": demo_type,
            "message": f"Demo session started",
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    return result


@router.post("/stop")
async def demo_stop(
    session_id: str = Query(..., description="Demo session ID"),
    _cto_check: bool = Depends(require_cto_access)
):
    """
    Stop an active investor demo session.
    CTO access only.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    _analytics.increment("demo:stop")
    
    result = await demo_manager.stop_session(session_id)
    
    if result["success"]:
        session = result["session"]
        return {
            "success": True,
            "session_id": session_id,
            "duration_seconds": session.get("duration_seconds", 0),
            "decisions_made": session.get("decisions_made", 0),
            "actions_taken": session.get("actions_taken", 0),
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    return result


@router.get("/report")
async def demo_report(
    session_id: Optional[str] = Query(None),
    include_telemetry: bool = Query(False),
    _cto_check: bool = Depends(require_cto_access)
):
    """
    Generate a comprehensive demo report.
    CTO access only.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    _analytics.increment("demo:report")
    
    report = await demo_manager.generate_report(session_id, include_telemetry)
    
    return {
        "success": True,
        "report": report,
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.delete("/reset")
async def reset_demo_manager(
    _cto_check: bool = Depends(require_cto_access)
):
    """
    Reset the demo session manager. Clears all active sessions and history.
    CTO access only.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=503, detail="Demo engine is disabled")
    
    demo_manager.reset()
    
    return {
        "success": True,
        "message": "Demo manager reset",
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


__all__ = ['router', 'demo_manager', 'SHOWCASE_SCENARIOS', 'DemoSessionManager', 'require_demo_access', 'require_cto_access']