"""
NeuroBridge - External API Routes
Partner / Investor / SaaS external access layer.
Prometheus Metrics Instrumented - External API Observability
"""

from __future__ import annotations

import logging
import time
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union, Tuple

from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.core.api_key_manager import (
    ApiPlan,
    ApiClient,
    get_api_key_manager,
)
from backend.core.usage_meter import get_usage_meter
from backend.core.cognitive_engine import CognitiveContext, get_cognitive_engine
from backend.core.security_rotation import rotate_external_client_key

logger = logging.getLogger("NeuroBridge.ExternalRoutes")

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

try:
    from backend.monitoring.prometheus_metrics import (
        record_external_request,
        record_auth_failure,
        record_onboarding_event,
        set_investor_clients_active,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    def record_external_request(*args, **kwargs): pass
    def record_auth_failure(*args, **kwargs): pass
    def record_onboarding_event(*args, **kwargs): pass
    def set_investor_clients_active(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[EXTERNAL] prometheus metrics instrumented")
else:
    logger.debug("[EXTERNAL] prometheus metrics unavailable - running without instrumentation")

# Single concise initialization log - NO BANNER
logger.info("[EXTERNAL] routes initialized")

router = APIRouter(
    prefix="/api/v1/external",
    tags=["External API"],
)

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class PartnerOnboardingRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    organization: str = Field(default="Unknown", max_length=160)
    email: str = Field(default="", max_length=160)
    plan: ApiPlan = ApiPlan.INVESTOR_DEMO
    use_case: str = Field(default="investor_demo", max_length=500)


class ExternalCognitiveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    telemetry: Dict[str, Any] = Field(default_factory=dict)


class AuthResult(BaseModel):
    """Authentication result model for admin endpoints."""
    valid: bool
    client_id: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# SAFE CLIENT HELPER FUNCTIONS (Supports both dict and object)
# ============================================================================

def get_client_field(client: Union[Dict, Any], field: str, default: Any = None) -> Any:
    """
    Safely get a field from client (supports both dict and object).
    """
    if client is None:
        return default
    
    if isinstance(client, dict):
        return client.get(field, default)
    
    # Object access
    if hasattr(client, field):
        return getattr(client, field, default)
    
    return default


def get_client_plan_str(client: Union[Dict, Any]) -> str:
    """
    Safely get plan as string from client.
    """
    plan = get_client_field(client, "plan", "investor_demo")
    
    # Handle enum values
    if hasattr(plan, "value"):
        return plan.value
    
    return str(plan)


def get_client_id(client: Union[Dict, Any]) -> str:
    """
    Safely get client_id from client.
    """
    return get_client_field(client, "client_id", "unknown")


def get_client_name(client: Union[Dict, Any]) -> str:
    """
    Safely get name from client.
    """
    return get_client_field(client, "name", "Unknown")


def get_client_active(client: Union[Dict, Any]) -> bool:
    """
    Safely get active status from client.
    """
    active = get_client_field(client, "active", True)
    return bool(active)


def get_client_created_at(client: Union[Dict, Any]) -> Any:
    """
    Safely get created_at from client.
    """
    return get_client_field(client, "created_at", int(time.time()))


def get_client_metadata(client: Union[Dict, Any]) -> Dict[str, Any]:
    """
    Safely get metadata from client.
    """
    metadata = get_client_field(client, "metadata", {})
    if metadata is None:
        return {}
    return metadata


def _sanitize_client(client: Union[Dict, Any]) -> Dict[str, Any]:
    """
    Sanitize client object for API responses.
    Supports both dict and object clients.
    NEVER exposes API keys or sensitive internal fields.
    """
    return {
        "client_id": get_client_id(client),
        "name": get_client_name(client),
        "plan": get_client_plan_str(client),
        "active": get_client_active(client),
        "created_at": get_client_created_at(client),
        "metadata": get_client_metadata(client),
    }


def _generate_secure_api_key() -> str:
    """
    Generate a secure API key.
    Format: nb11d_{timestamp}_{random_hex}
    """
    timestamp = int(time.time())
    random_hex = secrets.token_hex(12)
    return f"nb11d_{timestamp}_{random_hex}"


def _extract_api_key_from_create_result(
    result: Any,
    client: Union[Dict, Any]
) -> Tuple[Optional[str], bool]:
    """
    Extract API key from create_client result.
    
    Supports:
    - Tuple (client, api_key)
    - Dict with 'api_key', 'key', or 'token' fields
    - Object with api_key attribute
    
    Returns:
        Tuple of (api_key, success)
        success=False means key cannot be used (return 500)
    """
    
    # Case 1: Result is tuple (client, api_key)
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        api_key = result[1]
        if api_key and isinstance(api_key, str) and len(api_key) > 10:
            return str(api_key), True
    
    # Case 2: Client dict has api_key field
    if isinstance(client, dict):
        if "api_key" in client:
            api_key = client["api_key"]
            if api_key and isinstance(api_key, str) and len(api_key) > 10:
                return str(api_key), True
        if "key" in client:
            api_key = client["key"]
            if api_key and isinstance(api_key, str) and len(api_key) > 10:
                return str(api_key), True
        if "token" in client:
            api_key = client["token"]
            if api_key and isinstance(api_key, str) and len(api_key) > 10:
                return str(api_key), True
    
    # Case 3: Client object has api_key attribute
    if hasattr(client, "api_key"):
        api_key = client.api_key
        if api_key and isinstance(api_key, str) and len(api_key) > 10:
            return str(api_key), True
    if hasattr(client, "key"):
        api_key = client.key
        if api_key and isinstance(api_key, str) and len(api_key) > 10:
            return str(api_key), True
    if hasattr(client, "token"):
        api_key = client.token
        if api_key and isinstance(api_key, str) and len(api_key) > 10:
            return str(api_key), True
    
    # Case 4: Result dict has api_key
    if isinstance(result, dict):
        if "api_key" in result:
            api_key = result["api_key"]
            if api_key and isinstance(api_key, str) and len(api_key) > 10:
                return str(api_key), True
        if "key" in result:
            api_key = result["key"]
            if api_key and isinstance(api_key, str) and len(api_key) > 10:
                return str(api_key), True
    
    # No valid API key found
    return None, False


def _extract_client_from_create_result(result: Any) -> Union[Dict, Any]:
    """
    Extract client object from create_client result.
    
    Supports:
    - Direct client return
    - Tuple (client, api_key)
    - Dict with 'client' field
    """
    # Case 1: Result is tuple/list - return first element
    if isinstance(result, (tuple, list)) and len(result) >= 1:
        return result[0]
    
    # Case 2: Result has 'client' attribute/field
    if isinstance(result, dict) and "client" in result:
        return result["client"]
    
    if hasattr(result, "client"):
        return result.client
    
    # Case 3: Result is the client itself
    return result


def _extract_frontend_metrics(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract frontend-compatible metrics from cognitive decision evidence.
    
    Maps:
    - gsi or grid_stability_index -> grid_stability_index
    - ses or solar_efficiency_score -> solar_efficiency_score
    - risk or risk_score -> risk_score
    """
    metrics = {}
    
    # Extract grid stability index
    gsi = evidence.get("gsi") or evidence.get("grid_stability_index")
    if gsi is not None:
        metrics["grid_stability_index"] = gsi
    
    # Extract solar efficiency score
    ses = evidence.get("ses") or evidence.get("solar_efficiency_score")
    if ses is not None:
        metrics["solar_efficiency_score"] = ses
    
    # Extract risk score
    risk = evidence.get("risk") or evidence.get("risk_score")
    if risk is not None:
        metrics["risk_score"] = risk
    
    return metrics


def _get_current_timestamp() -> int:
    """Get current Unix timestamp."""
    return int(time.time())


def _get_iso_timestamp() -> str:
    """Get ISO format timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def require_admin_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> AuthResult:
    """
    Authentication for admin endpoints.
    Requires CTO or ENTERPRISE plan.
    """
    if not x_api_key:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external/admin", method="GET")
        except Exception:
            pass
        return AuthResult(valid=False, error="Missing X-API-Key header")
    
    manager = get_api_key_manager()
    client = manager.verify_key(x_api_key)
    
    if not client:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external/admin", method="GET")
        except Exception:
            pass
        return AuthResult(valid=False, error="Invalid API key")
    
    plan_str = get_client_plan_str(client)
    
    if plan_str not in ["cto", "enterprise", "CTO", "ENTERPRISE"]:
        # PROMETHEUS: Record auth failure (insufficient privileges)
        try:
            record_auth_failure(route="/api/v1/external/admin", method="GET")
        except Exception:
            pass
        return AuthResult(valid=False, error="Admin privileges required")
    
    return AuthResult(valid=True, client_id=get_client_id(client))


def require_external_client(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> ApiClient:
    """Require valid external API key for client endpoints."""
    if not x_api_key:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external", method="GET")
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing X-API-Key header", "phase": "PHASE_1_PRODUCTION"}
        )
    
    manager = get_api_key_manager()
    client = manager.verify_key(x_api_key)

    if not client:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external", method="GET")
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid external API key", "phase": "PHASE_1_PRODUCTION"}
        )

    meter = get_usage_meter()
    limits = manager.get_limits(client)
    usage_status = meter.check_limits(get_client_id(client), limits)

    if not usage_status["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "API usage limit exceeded",
                "usage": usage_status,
                "phase": "PHASE_1_PRODUCTION"
            }
        )

    return client


# ============================================================================
# PUBLIC ENDPOINTS (No Authentication Required)
# ============================================================================

@router.get("/health")
async def external_health() -> Dict[str, Any]:
    """Health check for external API."""
    start_time = time.time()
    try:
        result = {
            "status": "ok",
            "service": "NeuroBridge External API",
            "phase": "PHASE_1_PRODUCTION",
            "available_products": [
                "investor_demo_api",
                "deterministic_cognitive_api",
                "solar_grid_telemetry_api",
                "aece_control_observability_api",
                "latency_metrics_api",
            ],
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Record external request
        try:
            record_external_request(
                route="/api/v1/external/health",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/status")
async def external_status() -> Dict[str, Any]:
    """Status endpoint for external API monitoring."""
    start_time = time.time()
    try:
        result = {
            "status": "ok",
            "phase": "PHASE_1_PRODUCTION",
            "deterministic_mode": True,
            "external_api": True,
            "latency_monitoring": True,
            "usage_metering": True,
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Record external request
        try:
            record_external_request(
                route="/api/v1/external/status",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/products")
async def external_products() -> Dict[str, Any]:
    """List available API products."""
    start_time = time.time()
    try:
        result = {
            "status": "success",
            "phase": "PHASE_1_PRODUCTION",
            "products": [
                {
                    "id": "investor_demo_api",
                    "name": "Investor Demo API",
                    "description": "Remote validation of NeuroBridge demo sessions and reports.",
                },
                {
                    "id": "energy_cognitive_api",
                    "name": "Energy Cognitive API",
                    "description": "Physics-grounded reasoning for solar/grid optimization.",
                },
                {
                    "id": "aece_observability_api",
                    "name": "AECE Observability API",
                    "description": "Autonomous control status and risk monitoring.",
                },
                {
                    "id": "latency_metrics_api",
                    "name": "Latency Metrics API",
                    "description": "Real-time p95/p99 latency metrics for performance verification.",
                },
            ],
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Record external request
        try:
            record_external_request(
                route="/api/v1/external/products",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ============================================================================
# ONBOARDING ENDPOINT - FIXED WITH SAFE CLIENT HANDLING
# ============================================================================

@router.post("/onboard")
async def onboard_partner(
    payload: PartnerOnboardingRequest,
) -> Dict[str, Any]:
    """Onboard a new external API client."""
    start_time = time.time()
    
    manager = get_api_key_manager()
    
    # Create client using the manager's create_client method
    result = manager.create_client(
        name=f"{payload.name} - {payload.organization}",
        plan=payload.plan,
        metadata={
            "email": payload.email,
            "organization": payload.organization,
            "use_case": payload.use_case,
        },
    )
    
    # Extract client from result (supports tuple, dict, object)
    client = _extract_client_from_create_result(result)
    
    # Extract API key from result/client
    api_key, key_found = _extract_api_key_from_create_result(result, client)
    
    # If no valid API key was found, return HTTP 500
    if not key_found or not api_key:
        logger.error(f"[AUDIT] onboarding_failed reason=key_persistence_error client_id={get_client_id(client)}")
        
        # PROMETHEUS: Record failed onboarding attempt
        try:
            record_external_request(
                route="/api/v1/external/onboard",
                method="POST",
                status=500,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "API key manager cannot persist generated keys",
                "phase": "PHASE_1_PRODUCTION"
            }
        )
    
    # Critical security event - keep as INFO
    logger.info(f"[AUDIT] client_onboarded client_id={get_client_id(client)} plan={payload.plan.value}")
    
    # PROMETHEUS: Record successful onboarding event
    try:
        plan_str = payload.plan.value if hasattr(payload.plan, 'value') else str(payload.plan)
        record_onboarding_event(plan=plan_str)
        record_external_request(
            route="/api/v1/external/onboard",
            method="POST",
            status=200,
            latency_seconds=time.time() - start_time
        )
    except Exception:
        pass
    
    # PROMETHEUS: Update active investor clients count
    try:
        manager_obj = get_api_key_manager()
        active_count = 0
        try:
            if hasattr(manager_obj, 'count_clients'):
                active_count = manager_obj.count_clients()
            elif hasattr(manager_obj, 'list_clients'):
                clients = manager_obj.list_clients(limit=1000)
                if isinstance(clients, list):
                    active_count = sum(1 for c in clients if get_client_active(c))
        except Exception:
            pass
        set_investor_clients_active(active_count)
    except Exception:
        pass
    
    return {
        "status": "success",
        "message": "External API client created",
        "client": _sanitize_client(client),
        "api_key": api_key,
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": _get_current_timestamp(),
        "timestamp_iso": _get_iso_timestamp(),
    }


# ============================================================================
# CLIENT ENDPOINTS (Require API Key)
# ============================================================================

@router.get("/me")
async def external_me(
    client: ApiClient = Depends(require_external_client),
) -> Dict[str, Any]:
    """Get information about the authenticated client."""
    start_time = time.time()
    
    manager = get_api_key_manager()
    meter = get_usage_meter()

    usage = meter.check_limits(
        get_client_id(client),
        manager.get_limits(client),
    )

    result = {
        "status": "success",
        "phase": "PHASE_1_PRODUCTION",
        "client": _sanitize_client(client),
        "usage": usage,
        "timestamp": _get_current_timestamp(),
        "timestamp_iso": _get_iso_timestamp(),
    }
    
    # PROMETHEUS: Record external request
    try:
        record_external_request(
            route="/api/v1/external/me",
            method="GET",
            status=200,
            latency_seconds=time.time() - start_time
        )
    except Exception:
        pass
    
    return result


@router.post("/cognitive/query")
async def external_cognitive_query(
    payload: ExternalCognitiveRequest,
    client: ApiClient = Depends(require_external_client),
) -> Dict[str, Any]:
    """Process cognitive query with deterministic reasoning."""
    start_time = time.time()
    
    manager = get_api_key_manager()
    meter = get_usage_meter()

    usage = meter.record(
        client_id=get_client_id(client),
        endpoint="/api/v1/external/cognitive/query",
    )

    engine = get_cognitive_engine()

    decision = engine.reason(
        payload.query,
        CognitiveContext(
            telemetry=payload.telemetry,
            metrics=payload.metrics,
            user_role="external_client",
            phase="PHASE_1_PRODUCTION",
        ),
    )
    
    decision_latency_ms = round((time.time() - start_time) * 1000, 2)
    
    # Extract frontend metrics from evidence
    frontend_metrics = _extract_frontend_metrics(decision.evidence)
    
    # Build result with all required fields
    result_data = {
        "intent": decision.intent.value,
        "confidence": decision.confidence,
        "severity": decision.severity.value,
        "summary": decision.summary,
        "explanation": decision.explanation,
        "recommended_actions": decision.recommended_actions,
        "evidence": decision.evidence,
        "mode": decision.mode,
    }

    result = {
        "status": "success",
        "phase": "PHASE_1_PRODUCTION",
        "client_id": get_client_id(client),
        "plan": get_client_plan_str(client),
        "usage": usage,
        "result": result_data,
        "metrics": frontend_metrics if frontend_metrics else None,
        "explanation": decision.explanation,
        "performance": {
            "decision_latency_ms": decision_latency_ms,
            "mode": "deterministic"
        },
        "timestamp": _get_current_timestamp(),
        "timestamp_iso": _get_iso_timestamp(),
    }
    
    # PROMETHEUS: Record external request with latency
    try:
        record_external_request(
            route="/api/v1/external/cognitive/query",
            method="POST",
            status=200,
            latency_seconds=time.time() - start_time
        )
    except Exception:
        pass
    
    return result


@router.get("/latency")
async def external_latency_summary(
    client: ApiClient = Depends(require_external_client),
) -> Dict[str, Any]:
    """Get latency metrics for performance verification."""
    start_time = time.time()
    
    from backend.core.latency_metrics import get_latency_metrics
    
    meter = get_usage_meter()
    meter.record(
        client_id=get_client_id(client),
        endpoint="/api/v1/external/latency",
    )
    
    try:
        latency_metrics = get_latency_metrics()
        summary = latency_metrics.summary()
        
        total_requests = summary.get("total_requests", 0)
        
        # Determine collector status
        collector_active = latency_metrics is not None
        
        # Calculate performance grade with proper fallback
        if not collector_active:
            performance_grade = "UNAVAILABLE"
            interpretation = "Latency metrics system not initialized. Check backend configuration."
        elif total_requests < 5:
            performance_grade = "INITIALIZING"
            interpretation = f"Latency engine active. Generate {6 - total_requests} more API request(s) to populate p50/p95/p99 metrics."
        else:
            p95_ms = summary.get("p95_ms", 0)
            p99_ms = summary.get("p99_ms", 0)
            
            if p95_ms < 50 and p99_ms < 100:
                performance_grade = "EXCELLENT"
                interpretation = "Exceptional API performance. p95 under 50ms, p99 under 100ms."
            elif p95_ms < 100 and p99_ms < 200:
                performance_grade = "GOOD"
                interpretation = "Good API performance. p95 under 100ms, p99 under 200ms."
            elif p95_ms < 250 and p99_ms < 500:
                performance_grade = "FAIR"
                interpretation = "Fair performance. Optimization recommended for high-throughput requirements."
            else:
                performance_grade = "POOR"
                interpretation = "Poor performance detected. Investigate bottlenecks and optimize endpoints."
        
        # Build investor-friendly response
        result = {
            "status": "success",
            "phase": "PHASE_1_PRODUCTION",
            "client_id": get_client_id(client),
            "plan": get_client_plan_str(client),
            "collector_active": collector_active,
            "latency": {
                "p50_ms": summary.get("p50_ms", 0),
                "p95_ms": summary.get("p95_ms", 0),
                "p99_ms": summary.get("p99_ms", 0),
                "mean_ms": summary.get("mean_ms", 0),
                "min_ms": summary.get("min_ms", 0),
                "max_ms": summary.get("max_ms", 0),
                "total_requests": total_requests,
                "requests_per_second": summary.get("requests_per_second", 0),
            },
            "performance_grade": performance_grade,
            "interpretation": interpretation,
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Record external request
        try:
            record_external_request(
                route="/api/v1/external/latency",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
        
    except Exception as e:
        logger.debug(f"Latency metrics unavailable: {e}")
        result = {
            "status": "degraded",
            "phase": "PHASE_1_PRODUCTION",
            "client_id": get_client_id(client),
            "plan": get_client_plan_str(client),
            "collector_active": False,
            "latency": {
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "mean_ms": 0,
                "min_ms": 0,
                "max_ms": 0,
                "total_requests": 0,
                "requests_per_second": 0,
            },
            "performance_grade": "UNAVAILABLE",
            "interpretation": "Latency metrics service unavailable. Please try again later.",
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Record external request (degraded)
        try:
            record_external_request(
                route="/api/v1/external/latency",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result


# ============================================================================
# ADMIN ENDPOINTS (Require Admin API Key)
# ============================================================================

@router.post("/admin/clients/{client_id}/rotate-key")
async def rotate_external_client_api_key(
    client_id: str,
    auth: AuthResult = Depends(require_admin_api_key),
) -> Dict[str, Any]:
    """Rotate an external client's API key. Admin only."""
    start_time = time.time()
    
    if not auth.valid:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external/admin/rotate-key", method="POST")
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            detail={"error": auth.error or "Authentication failed", "phase": "PHASE_1_PRODUCTION"}
        )
    
    # Critical security event - keep as INFO
    logger.info(f"[AUDIT] key_rotation client_id={client_id} admin_id={auth.client_id}")
    
    try:
        result = rotate_external_client_key(client_id)
        result["authenticated"] = auth.valid
        result["authenticated_client_id"] = auth.client_id
        result["phase"] = "PHASE_1_PRODUCTION"
        
        # PROMETHEUS: Record external request
        try:
            record_external_request(
                route="/api/v1/external/admin/rotate-key",
                method="POST",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
        
    except ValueError as e:
        # PROMETHEUS: Record external request (404)
        try:
            record_external_request(
                route="/api/v1/external/admin/rotate-key",
                method="POST",
                status=404,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=404,
            detail={"error": "Client not found", "message": str(e), "phase": "PHASE_1_PRODUCTION"}
        )
    except Exception as e:
        # PROMETHEUS: Record external request (500)
        try:
            record_external_request(
                route="/api/v1/external/admin/rotate-key",
                method="POST",
                status=500,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail={"error": "Key rotation failed", "message": str(e), "phase": "PHASE_1_PRODUCTION"}
        )


@router.get("/admin/clients")
async def list_external_clients(
    auth: AuthResult = Depends(require_admin_api_key),
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """List all external API clients. Admin only."""
    start_time = time.time()
    
    if not auth.valid:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external/admin/clients", method="GET")
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            detail={"error": auth.error or "Authentication failed", "phase": "PHASE_1_PRODUCTION"}
        )
    
    # Admin view - use DEBUG to avoid log flooding
    logger.debug(f"[AUDIT] client_list_view admin_id={auth.client_id}")
    
    manager = get_api_key_manager()
    meter = get_usage_meter()
    
    try:
        clients = manager.list_clients(limit=limit, offset=offset)
        total = manager.count_clients()
        
        enhanced_clients = []
        for c in clients:
            usage = meter.get_client_usage(get_client_id(c))
            enhanced_clients.append({
                "client_id": get_client_id(c),
                "name": get_client_name(c),
                "plan": get_client_plan_str(c),
                "active": get_client_active(c),
                "created_at": get_client_created_at(c),
                "metadata": get_client_metadata(c),
                "usage": {
                    "total_requests": usage.get("total_requests", 0),
                    "last_request_at": usage.get("last_request_at"),
                    "rate_limit_remaining": usage.get("rate_limit_remaining", 0),
                },
            })
        
        result = {
            "status": "success",
            "phase": "PHASE_1_PRODUCTION",
            "clients": enhanced_clients,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "has_more": (offset + limit) < total,
            },
            "authenticated_client_id": auth.client_id,
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Update investor clients active count and record request
        try:
            active_count = sum(1 for c in clients if get_client_active(c))
            set_investor_clients_active(active_count)
            record_external_request(
                route="/api/v1/external/admin/clients",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
        
    except AttributeError:
        result = {
            "status": "partial",
            "phase": "PHASE_1_PRODUCTION",
            "clients": [],
            "authenticated_client_id": auth.client_id,
            "timestamp": _get_current_timestamp(),
            "timestamp_iso": _get_iso_timestamp(),
        }
        
        # PROMETHEUS: Record external request (partial)
        try:
            record_external_request(
                route="/api/v1/external/admin/clients",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result


@router.get("/admin/usage/{client_id}")
async def get_client_usage_summary(
    client_id: str,
    auth: AuthResult = Depends(require_admin_api_key),
    days: int = 30,
) -> Dict[str, Any]:
    """Get detailed usage summary for a specific client. Admin only."""
    start_time = time.time()
    
    if not auth.valid:
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/external/admin/usage", method="GET")
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            detail={"error": auth.error or "Authentication failed", "phase": "PHASE_1_PRODUCTION"}
        )
    
    # Admin view - use DEBUG to avoid log flooding
    logger.debug(f"[AUDIT] usage_view client_id={client_id} admin_id={auth.client_id}")
    
    manager = get_api_key_manager()
    meter = get_usage_meter()
    
    try:
        client = manager.get_client(client_id)
        if not client:
            # PROMETHEUS: Record external request (404)
            try:
                record_external_request(
                    route="/api/v1/external/admin/usage",
                    method="GET",
                    status=404,
                    latency_seconds=time.time() - start_time
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=404,
                detail={"error": "Client not found", "phase": "PHASE_1_PRODUCTION"}
            )
    except HTTPException:
        raise
    except Exception:
        # PROMETHEUS: Record external request (404)
        try:
            record_external_request(
                route="/api/v1/external/admin/usage",
                method="GET",
                status=404,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=404,
            detail={"error": "Client not found", "phase": "PHASE_1_PRODUCTION"}
        )
    
    usage = meter.get_client_usage(client_id, days=days)
    
    result = {
        "status": "success",
        "phase": "PHASE_1_PRODUCTION",
        "client": {
            "client_id": get_client_id(client),
            "name": get_client_name(client),
            "plan": get_client_plan_str(client),
            "active": get_client_active(client),
            "created_at": get_client_created_at(client),
        },
        "usage": usage,
        "authenticated_client_id": auth.client_id,
        "timestamp": _get_current_timestamp(),
        "timestamp_iso": _get_iso_timestamp(),
    }
    
    # PROMETHEUS: Record external request
    try:
        record_external_request(
            route="/api/v1/external/admin/usage",
            method="GET",
            status=200,
            latency_seconds=time.time() - start_time
        )
    except Exception:
        pass
    
    return result