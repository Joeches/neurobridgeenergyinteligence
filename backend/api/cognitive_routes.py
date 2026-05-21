"""
NeuroBridge - Cognitive API Routes

Deterministic reasoning engine for Phase 1 production.
No ML/AI dependencies - fully deterministic.
"""

from __future__ import annotations

import logging
import time
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel, Field, field_validator

from backend.core.cognitive_engine import (
    CognitiveContext,
    CognitiveDecision,
    get_cognitive_engine,
)

logger = logging.getLogger("NeuroBridge.CognitiveRoutes")

# Single concise initialization log - NO BANNER
logger.info("[COGNITIVE] routes initialized")

router = APIRouter(
    tags=["Cognitive Reasoning"],
)

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CognitiveQueryRequest(BaseModel):
    query: str = Field(
        default="Analyze grid stability and solar risk",
        min_length=1,
        max_length=2000
    )
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    system: Dict[str, Any] = Field(default_factory=dict)
    user_role: str = Field(default="operator", max_length=80)
    context: Dict[str, Any] = Field(default_factory=dict)  # Frontend compatibility
    
    # Allow extra fields to be ignored (for frontend compatibility)
    class Config:
        extra = "ignore"
    
    @field_validator('telemetry', 'metrics', 'system', 'context', mode='before')
    @classmethod
    def ensure_dict(cls, v: Any) -> Dict[str, Any]:
        """Ensure that fields are always dictionaries."""
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        try:
            return dict(v) if v else {}
        except (TypeError, ValueError):
            return {}


class CognitiveQueryResponse(BaseModel):
    status: str
    query: str
    result: Dict[str, Any]
    metrics: Optional[Dict[str, Any]] = None
    explanation: Optional[str] = None
    authenticated: bool
    timestamp: int


class CognitiveHealthResponse(BaseModel):
    status: str
    engine: str
    version: str
    mode: str
    phase: str
    timestamp: int


# ============================================================================
# AUTHENTICATION HELPERS - Supports investor_demo API keys
# ============================================================================

def _get_token_from_headers(
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Extract token from Authorization Bearer header or X-API-Key header.
    """
    # Check Authorization Bearer header first
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    
    # Check X-API-Key header
    if x_api_key:
        token = x_api_key.strip()
        if token:
            return token
    
    return None


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
            # Get plan as string
            plan_value = getattr(client, 'plan', None)
            if hasattr(plan_value, 'value'):
                plan_str = plan_value.value
            else:
                plan_str = str(plan_value) if plan_value else ""
            
            # Accept investor_demo, enterprise, and cto plans
            if plan_str in ["investor_demo", "enterprise", "cto", "INVESTOR_DEMO", "ENTERPRISE", "CTO"]:
                return {
                    "valid": True,
                    "auth_type": "api_key",
                    "client_id": getattr(client, 'client_id', 'unknown'),
                    "plan": plan_str
                }
        return None
    except ImportError:
        logger.debug("API key manager not available")
        return None
    except Exception as e:
        logger.debug(f"API key manager validation error: {type(e).__name__}")
        return None


def _validate_with_core_auth(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate token using the core auth system (CTO token support).
    """
    try:
        from backend.core.auth import validate_token_core
        
        result = validate_token_core(token)
        
        if result and result.get("valid"):
            return {
                "valid": True,
                "auth_type": result.get("auth_type", "core_auth"),
                "client_id": result.get("client_id"),
                "plan": result.get("plan", "cto")
            }
        return None
    except ImportError:
        logger.debug("Core auth module not available")
        return None
    except Exception as e:
        logger.debug(f"Core auth validation error: {type(e).__name__}")
        return None


def _is_development_mode() -> bool:
    """Check if running in development mode."""
    env = os.getenv("ENVIRONMENT", "production").lower()
    return env in ["development", "dev", "local"]


async def require_cognitive_access(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Dict[str, Any]:
    """
    Authentication dependency for cognitive endpoints.
    
    Accepts:
    - CTO tokens
    - Investor demo API keys (investor_demo plan)
    - Enterprise API keys (enterprise plan)
    - Core auth tokens
    - Development bypass tokens (dev mode only)
    
    Returns auth_info dict with authenticated flag and metadata.
    Raises HTTP 401 on failure.
    """
    # Extract token from headers
    token = _get_token_from_headers(authorization, x_api_key)
    
    # Development mode - allow bypass
    if _is_development_mode():
        dev_bypass_token = os.getenv("DEV_BYPASS_TOKEN", "DEV_ABUJA_PILOT_2026")
        if not token:
            logger.debug("[COGNITIVE] DEV MODE: No token - allowing access")
            return {
                "authenticated": True,
                "mode": "DEVELOPMENT_OPEN",
                "auth_type": "dev_bypass",
                "plan": "dev",
                "phase": "PHASE_1_PRODUCTION"
            }
        if token == dev_bypass_token:
            logger.debug("[COGNITIVE] DEV MODE: Bypass token used")
            return {
                "authenticated": True,
                "mode": "DEVELOPMENT_BYPASS",
                "auth_type": "dev_bypass",
                "plan": "dev",
                "phase": "PHASE_1_PRODUCTION"
            }
    
    # No token provided
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Authentication required",
                "message": "Missing authentication token",
                "phase": "PHASE_1_PRODUCTION"
            }
        )
    
    # Try API Key Manager first (supports investor_demo, enterprise, cto)
    api_key_result = _validate_with_api_key_manager(token)
    if api_key_result:
        logger.debug(f"[COGNITIVE] Token validated via API Key Manager: plan={api_key_result.get('plan')}")
        return {
            "authenticated": True,
            "mode": "PRODUCTION",
            "auth_type": api_key_result.get("auth_type", "api_key"),
            "client_id": api_key_result.get("client_id"),
            "plan": api_key_result.get("plan"),
            "phase": "PHASE_1_PRODUCTION"
        }
    
    # Try Core Auth system (CTO tokens)
    core_result = _validate_with_core_auth(token)
    if core_result:
        logger.debug(f"[COGNITIVE] Token validated via Core Auth")
        return {
            "authenticated": True,
            "mode": "PRODUCTION",
            "auth_type": core_result.get("auth_type", "core_auth"),
            "client_id": core_result.get("client_id"),
            "plan": core_result.get("plan", "cto"),
            "phase": "PHASE_1_PRODUCTION"
        }
    
    # All validation attempts failed
    logger.debug(f"[COGNITIVE] Authentication failed")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "Authentication failed",
            "message": "Invalid or expired authentication token",
            "phase": "PHASE_1_PRODUCTION"
        }
    )


# ============================================================================
# HELPER FUNCTIONS FOR METRICS EXTRACTION
# ============================================================================

def _decision_to_dict(decision: CognitiveDecision) -> Dict[str, Any]:
    return {
        "intent": decision.intent.value,
        "confidence": decision.confidence,
        "severity": decision.severity.value,
        "summary": decision.summary,
        "explanation": decision.explanation,
        "recommended_actions": decision.recommended_actions,
        "evidence": decision.evidence,
        "mode": decision.mode,
        "generated_at": decision.generated_at,
    }


def _extract_metrics_from_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract frontend-compatible metrics from decision evidence.
    
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


def _calculate_metrics_from_inputs(combined_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate frontend metrics from combined input sources (telemetry + context + metrics).
    
    Combines data from:
    - Payload telemetry
    - Payload context (frontend)
    - Payload metrics (canonical)
    
    Returns calculated frontend metrics:
    - grid_stability_index
    - solar_efficiency_score
    - risk_score
    """
    metrics = {}
    
    # Calculate grid stability index from frequency and voltage
    frequency = (combined_inputs.get("frequency_hz") or 
                 combined_inputs.get("grid_frequency_hz") or
                 combined_inputs.get("frequency"))
    voltage = (combined_inputs.get("voltage_v") or 
               combined_inputs.get("grid_voltage_v") or
               combined_inputs.get("voltage"))
    
    if frequency is not None:
        try:
            freq_val = float(frequency)
            # Stability decreases as frequency deviates from 50Hz
            freq_quality = 100 - min(100, abs(50.0 - freq_val) * 10)
            metrics["grid_stability_index"] = round(max(0, min(100, freq_quality)), 1)
        except (ValueError, TypeError):
            pass
    
    # Calculate solar efficiency from actual vs expected
    actual_kw = (combined_inputs.get("actual_kw") or 
                 combined_inputs.get("solar_output_kw") or
                 combined_inputs.get("actual_power"))
    expected_kw = (combined_inputs.get("expected_kw") or 
                   combined_inputs.get("expected_power"))
    
    if actual_kw is not None and expected_kw is not None:
        try:
            actual = float(actual_kw)
            expected = float(expected_kw)
            if expected > 0:
                efficiency = (actual / expected) * 100
                metrics["solar_efficiency_score"] = round(max(0, min(100, efficiency)), 1)
        except (ValueError, TypeError):
            pass
    
    # Calculate risk score from multiple factors
    risk_score = None
    
    # Try from frequency deviation
    if frequency is not None:
        try:
            freq_val = float(frequency)
            freq_risk = abs(50.0 - freq_val) / 2.0
            risk_score = min(1.0, freq_risk)
        except (ValueError, TypeError):
            pass
    
    # Try from irradiance quality
    irradiance_quality = combined_inputs.get("irradiance_quality")
    if irradiance_quality is not None and risk_score is None:
        try:
            # Lower quality = higher risk
            quality = float(irradiance_quality)
            risk_score = max(0, min(1, 1 - quality))
        except (ValueError, TypeError):
            pass
    
    # Try from load balance
    load_balance = combined_inputs.get("load_balance")
    if load_balance is not None and risk_score is None:
        try:
            balance = float(load_balance)
            # Balance below 0.85 indicates risk
            if balance < 0.85:
                risk_score = min(0.5, (0.85 - balance) * 2)
            else:
                risk_score = 0.05
        except (ValueError, TypeError):
            pass
    
    if risk_score is not None:
        metrics["risk_score"] = round(max(0, min(1, risk_score)), 3)
    
    return metrics


def _normalize_payload_metrics(payload_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize canonical payload metrics to frontend metric names.
    
    Converts:
    - gsi or grid_stability_index -> grid_stability_index
    - ses or solar_efficiency_score -> solar_efficiency_score
    - risk or risk_score -> risk_score
    """
    normalized = {}
    
    if payload_metrics:
        # Grid stability index
        gsi = payload_metrics.get("gsi") or payload_metrics.get("grid_stability_index")
        if gsi is not None:
            normalized["grid_stability_index"] = gsi
        
        # Solar efficiency score
        ses = payload_metrics.get("ses") or payload_metrics.get("solar_efficiency_score")
        if ses is not None:
            normalized["solar_efficiency_score"] = ses
        
        # Risk score
        risk = payload_metrics.get("risk") or payload_metrics.get("risk_score")
        if risk is not None:
            normalized["risk_score"] = risk
    
    return normalized


def _build_frontend_metrics(
    evidence: Dict[str, Any],
    payload_metrics: Dict[str, Any],
    payload_context: Dict[str, Any],
    telemetry: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build frontend-compatible metrics from multiple sources.
    
    Priority order:
    1. Evidence metrics (highest priority)
    2. Normalized payload metrics
    3. Calculated metrics from combined inputs
    
    Never exposes raw context fields directly.
    """
    metrics = {}
    
    # Priority 1: Extract from evidence
    evidence_metrics = _extract_metrics_from_evidence(evidence)
    metrics.update(evidence_metrics)
    
    # Priority 2: Normalized payload metrics
    normalized_metrics = _normalize_payload_metrics(payload_metrics)
    for key, value in normalized_metrics.items():
        if key not in metrics:  # Don't override evidence
            metrics[key] = value
    
    # Build combined inputs for calculation (NO direct exposure)
    combined_inputs = {}
    combined_inputs.update(telemetry or {})
    combined_inputs.update(payload_context or {})
    combined_inputs.update(payload_metrics or {})
    
    # Priority 3: Calculate missing metrics from combined inputs
    calculated_metrics = _calculate_metrics_from_inputs(combined_inputs)
    for key, value in calculated_metrics.items():
        if key not in metrics:  # Don't override existing metrics
            metrics[key] = value
    
    return metrics


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/health", response_model=CognitiveHealthResponse)
async def cognitive_health() -> CognitiveHealthResponse:
    engine = get_cognitive_engine()

    return CognitiveHealthResponse(
        status="ok",
        engine="NeuroBridge Cognitive Engine",
        version=engine.VERSION,
        mode="deterministic",
        phase="PHASE_1_PRODUCTION",
        timestamp=int(time.time()),
    )


@router.post("/query")
async def cognitive_query(
    payload: CognitiveQueryRequest,
    auth: Dict[str, Any] = Depends(require_cognitive_access),
) -> Dict[str, Any]:
    """
    Process cognitive query with frontend compatibility.
    
    Supports both:
    - Original fields: telemetry, metrics, system, user_role
    - Frontend field: context (used as calculation input only)
    
    Returns frontend-compatible response with metrics and explanation.
    
    Authentication:
    - Accepts CTO tokens
    - Accepts investor_demo API keys
    - Accepts enterprise API keys
    - Development bypass in dev mode
    """
    try:
        engine = get_cognitive_engine()
        
        # Safe query normalization - ensure we have a valid query
        if not payload.query or not payload.query.strip():
            effective_query = "Analyze grid stability and solar risk"
        else:
            effective_query = payload.query.strip()
        
        # Merge frontend context into metrics for cognitive engine processing
        effective_metrics = payload.metrics or payload.context or {}
        
        # Build cognitive context
        context = CognitiveContext(
            telemetry=payload.telemetry,
            metrics=effective_metrics,
            system=payload.system,
            user_role=payload.user_role,
            phase="PHASE_1_PRODUCTION",
        )
        
        # Get decision from cognitive engine
        decision = engine.reason(effective_query, context)
        
        # Convert decision to dictionary
        decision_dict = _decision_to_dict(decision)
        
        # Extract explanation
        explanation = decision_dict.get("explanation", "")
        
        # Build frontend metrics (never exposes raw context)
        frontend_metrics = _build_frontend_metrics(
            evidence=decision_dict.get("evidence", {}),
            payload_metrics=payload.metrics,
            payload_context=payload.context,
            telemetry=payload.telemetry
        )
        
        # Build frontend-compatible response
        return {
            "status": "success",
            "query": effective_query,
            "result": decision_dict,
            "metrics": frontend_metrics if frontend_metrics else None,
            "explanation": explanation,
            "authenticated": auth.get("authenticated", True),
            "timestamp": int(time.time()),
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("[COGNITIVE] Query reasoning failed")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Cognitive reasoning failed",
                "message": "Internal reasoning failure",
                "timestamp": int(time.time()),
            },
        ) from exc


@router.post("/explain")
async def explain_decision(
    payload: CognitiveQueryRequest,
    auth: Dict[str, Any] = Depends(require_cognitive_access),
) -> Dict[str, Any]:
    """
    Get detailed explanation of a cognitive decision.
    
    Authentication:
    - Accepts CTO tokens
    - Accepts investor_demo API keys
    - Accepts enterprise API keys
    - Development bypass in dev mode
    """
    try:
        engine = get_cognitive_engine()
        
        # Safe query normalization - ensure we have a valid query
        if not payload.query or not payload.query.strip():
            effective_query = "Analyze grid stability and solar risk"
        else:
            effective_query = payload.query.strip()
        
        # Merge frontend context into metrics for cognitive engine processing
        effective_metrics = payload.metrics or payload.context or {}
        
        context = CognitiveContext(
            telemetry=payload.telemetry,
            metrics=effective_metrics,
            system=payload.system,
            user_role=payload.user_role,
            phase="PHASE_1_PRODUCTION",
        )

        decision = engine.reason(effective_query, context)

        return {
            "status": "success",
            "explainability": {
                "query": effective_query,
                "intent_detected": decision.intent.value,
                "confidence": decision.confidence,
                "severity": decision.severity.value,
                "reasoning_mode": decision.mode,
                "why": decision.explanation,
                "evidence_used": decision.evidence,
                "recommended_actions": decision.recommended_actions,
            },
            "authenticated": auth.get("authenticated", True),
            "timestamp": int(time.time()),
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("[COGNITIVE] Explainability reasoning failed")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Cognitive explainability failed",
                "message": "Internal reasoning failure",
                "timestamp": int(time.time()),
            },
        ) from exc