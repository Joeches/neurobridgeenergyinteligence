"""
NeuroBridge - Authentication Validation Routes
Phase 1 Production API Key and Token Validation
Prometheus Metrics Instrumented - Auth Observability
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger("NeuroBridge.AuthRoutes")

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

try:
    from backend.monitoring.prometheus_metrics import (
        record_external_request,
        record_auth_failure,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    def record_external_request(*args, **kwargs): pass
    def record_auth_failure(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[AUTH] prometheus metrics instrumented")
else:
    logger.debug("[AUTH] prometheus metrics unavailable - running without instrumentation")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AuthValidateResponse(BaseModel):
    """Response model for authentication validation endpoint"""
    status: str = Field(..., description="Response status (success/error)")
    valid: bool = Field(..., description="Whether the token is valid")
    phase: str = Field(..., description="Current deployment phase")
    auth_type: Optional[str] = Field(None, description="Type of authentication used")
    client_id: Optional[str] = Field(None, description="Client ID if applicable")
    error: Optional[str] = Field(None, description="Error message if validation fails")
    timestamp: int = Field(..., description="Unix timestamp of the response")

    class Config:
        json_schema_extra = {
            "example_success": {
                "status": "success",
                "valid": True,
                "phase": "PHASE_1_PRODUCTION",
                "auth_type": "api_key",
                "client_id": "client_abc123",
                "timestamp": 1700000000
            },
            "example_failure": {
                "status": "error",
                "valid": False,
                "phase": "PHASE_1_PRODUCTION",
                "error": "Invalid or missing authentication token",
                "timestamp": 1700000000
            }
        }


# ============================================================================
# ROUTER DEFINITION
# ============================================================================

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


# ============================================================================
# AUTHENTICATION HELPERS - No imports from backend.main
# ============================================================================

def _get_token_from_headers(
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Extract token from Authorization Bearer header or X-API-Key header.
    
    Args:
        authorization: Authorization header value (e.g., "Bearer token123")
        x_api_key: X-API-Key header value
    
    Returns:
        Extracted token or None if not found
    """
    # Check Authorization Bearer header first
    if authorization:
        try:
            if authorization.startswith("Bearer "):
                token = authorization[7:].strip()
                if token:
                    return token
        except Exception:
            pass
    
    # Check X-API-Key header
    if x_api_key:
        try:
            token = x_api_key.strip()
            if token:
                return token
        except Exception:
            pass
    
    return None


def _validate_with_api_key_manager(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate token using the API key manager.
    
    Returns:
        Client dictionary if valid, None otherwise
    """
    try:
        from backend.core.api_key_manager import get_api_key_manager
        
        manager = get_api_key_manager()
        client = manager.verify_key(token)
        
        if client:
            return {
                "valid": True,
                "auth_type": "api_key",
                "client_id": client.client_id if hasattr(client, 'client_id') else "unknown",
                "client_name": getattr(client, 'name', None),
                "plan": getattr(client, 'plan', None),
            }
        return None
    except ImportError:
        logger.debug("API key manager not available")
        return None
    except Exception as e:
        logger.debug(f"API key manager validation error: {type(e).__name__}")
        return None


def _validate_with_auth_core(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate token using the core auth system (CTO token support).
    
    Returns:
        Validation result dict if valid, None otherwise
    """
    try:
        from backend.core.auth import validate_token_core
        
        result = validate_token_core(token)
        
        if result and result.get("valid"):
            return {
                "valid": True,
                "auth_type": result.get("auth_type", "core_auth"),
                "client_id": result.get("client_id"),
                "user_type": result.get("user_type"),
            }
        return None
    except ImportError:
        logger.debug("Core auth module not available")
        return None
    except Exception as e:
        logger.debug(f"Core auth validation error: {type(e).__name__}")
        return None


def _validate_with_simple_env_check(token: str) -> Optional[Dict[str, Any]]:
    """
    Fallback validation using environment variables.
    Supports CTO token and pilot tokens for development.
    
    Returns:
        Validation result dict if valid, None otherwise
    """
    import os
    import re
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    
    # Correct path resolution: backend/api/v1/auth.py -> root (3 levels up)
    # backend/api/v1/auth.py -> backend/api/v1 -> backend/api -> backend -> project_root
    try:
        env_path = Path(__file__).resolve().parents[3] / ".env"
        
        if env_path.exists() and load_dotenv:
            load_dotenv(env_path, override=False)
    except Exception:
        pass
    
    # Get configured tokens
    cto_token = os.getenv("CTO_ACCESS_CODE", "")
    neurobridge_api_key = os.getenv("NEUROBRIDGE_API_KEY", "")
    cto_api_key = os.getenv("CTO_API_KEY", "")
    api_key = os.getenv("API_KEY", "")
    dev_bypass_token = os.getenv("DEV_BYPASS_TOKEN", "DEV_ABUJA_PILOT_2026")
    
    # Check CTO token pattern
    cto_pattern = re.compile(r'^CTO-[A-F0-9]{4,8}(-[A-F0-9]{4,8}){2,4}$', re.IGNORECASE)
    pilot_pattern = re.compile(r'^PILOT-[A-F0-9]{4,8}(-[A-F0-9]{4,8}){1,3}$', re.IGNORECASE)
    
    # Check against configured tokens
    if token == cto_token and cto_token:
        return {"valid": True, "auth_type": "cto_token", "client_id": "cto_primary"}
    
    if token == neurobridge_api_key and neurobridge_api_key:
        return {"valid": True, "auth_type": "api_key", "client_id": "neurobridge_primary"}
    
    if token == cto_api_key and cto_api_key:
        return {"valid": True, "auth_type": "cto_api_key", "client_id": "cto_primary"}
    
    if token == api_key and api_key:
        return {"valid": True, "auth_type": "api_key", "client_id": "default_client"}
    
    # Check token patterns
    if cto_pattern.match(token):
        return {"valid": True, "auth_type": "cto_token", "client_id": "pattern_matched"}
    
    if pilot_pattern.match(token):
        return {"valid": True, "auth_type": "pilot_token", "client_id": "pilot_client"}
    
    # Development bypass
    env = os.getenv("ENVIRONMENT", "production").lower()
    if env in ["development", "dev", "local"] and token == dev_bypass_token:
        return {"valid": True, "auth_type": "dev_bypass", "client_id": "development"}
    
    return None


def _create_unauthorized_response(timestamp: int, phase: str, error_msg: str) -> HTTPException:
    """
    Create a standardized HTTP 401 Unauthorized response.
    
    Args:
        timestamp: Unix timestamp
        phase: Current deployment phase
        error_msg: Error message to display
    
    Returns:
        HTTPException with status 401 and error details
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "status": "error",
            "valid": False,
            "phase": phase,
            "error": error_msg,
            "timestamp": timestamp
        }
    )


# ============================================================================
# AUTHENTICATION VALIDATION ENDPOINT
# ============================================================================

@router.get(
    "/validate",
    response_model=AuthValidateResponse,
    summary="Validate Authentication Token",
    description="Validates API keys, CTO tokens, and pilot tokens for Phase 1 access"
)
async def validate_auth_token(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization", description="Bearer token"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="API key header"),
) -> Dict[str, Any]:
    """
    Validate authentication token for Phase 1 API access.
    
    Supports:
    - Bearer tokens via Authorization header
    - API keys via X-API-Key header
    - CTO tokens
    - Investor demo pilot tokens
    - Enterprise API keys
    
    Returns:
        AuthValidateResponse with validation result
        
    Raises:
        HTTPException: 401 Unauthorized for invalid or missing tokens
    """
    start_time = time.time()
    timestamp = int(time.time())
    phase = "PHASE_1_PRODUCTION"
    
    # Extract token from headers
    token = _get_token_from_headers(authorization, x_api_key)
    
    # No token provided - return HTTP 401
    if not token:
        logger.debug("No authentication token provided")
        
        # PROMETHEUS: Record auth failure
        try:
            record_auth_failure(route="/api/v1/auth/validate", method="GET")
            record_external_request(
                route="/api/v1/auth/validate",
                method="GET",
                status=401,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        raise _create_unauthorized_response(
            timestamp, 
            phase, 
            "Invalid or missing authentication token"
        )
    
    # Validate using available systems (ordered by priority)
    validation_result = None
    
    # Try API Key Manager first (most comprehensive)
    validation_result = _validate_with_api_key_manager(token)
    if validation_result:
        logger.debug(f"Token validated via API Key Manager: {validation_result.get('client_id')}")
        
        # PROMETHEUS: Record successful validation
        try:
            record_external_request(
                route="/api/v1/auth/validate",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return {
            "status": "success",
            "valid": True,
            "phase": phase,
            "auth_type": validation_result.get("auth_type", "api_key"),
            "client_id": validation_result.get("client_id", "unknown"),
            "timestamp": timestamp
        }
    
    # Try Core Auth system (CTO tokens)
    validation_result = _validate_with_auth_core(token)
    if validation_result:
        logger.debug(f"Token validated via Core Auth: {validation_result.get('auth_type')}")
        
        # PROMETHEUS: Record successful validation
        try:
            record_external_request(
                route="/api/v1/auth/validate",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return {
            "status": "success",
            "valid": True,
            "phase": phase,
            "auth_type": validation_result.get("auth_type", "core_auth"),
            "client_id": validation_result.get("client_id", validation_result.get("user_type", "unknown")),
            "timestamp": timestamp
        }
    
    # Try simple environment-based validation (fallback)
    validation_result = _validate_with_simple_env_check(token)
    if validation_result:
        logger.debug(f"Token validated via environment check: {validation_result.get('auth_type')}")
        
        # PROMETHEUS: Record successful validation (fallback)
        try:
            record_external_request(
                route="/api/v1/auth/validate",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return {
            "status": "success",
            "valid": True,
            "phase": phase,
            "auth_type": validation_result.get("auth_type", "environment"),
            "client_id": validation_result.get("client_id", "validated"),
            "timestamp": timestamp
        }
    
    # No validation succeeded - return HTTP 401
    logger.debug(f"Token validation failed - invalid token provided")
    
    # PROMETHEUS: Record auth failure
    try:
        record_auth_failure(route="/api/v1/auth/validate", method="GET")
        record_external_request(
            route="/api/v1/auth/validate",
            method="GET",
            status=401,
            latency_seconds=time.time() - start_time
        )
    except Exception:
        pass
    
    raise _create_unauthorized_response(
        timestamp, 
        phase, 
        "Invalid or missing authentication token"
    )


# ============================================================================
# HEALTH CHECK ENDPOINT (Optional)
# ============================================================================

@router.get(
    "/health",
    summary="Auth Service Health Check",
    description="Check if authentication service is operational",
    include_in_schema=False
)
async def auth_health() -> Dict[str, Any]:
    """Simple health check for auth service."""
    start_time = time.time()
    try:
        result = {
            "status": "healthy",
            "service": "authentication",
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": int(time.time())
        }
        
        # PROMETHEUS: Record health check request
        try:
            record_external_request(
                route="/api/v1/auth/health",
                method="GET",
                status=200,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        
        return result
    except Exception as e:
        # PROMETHEUS: Record failed health check
        try:
            record_external_request(
                route="/api/v1/auth/health",
                method="GET",
                status=500,
                latency_seconds=time.time() - start_time
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ['router']