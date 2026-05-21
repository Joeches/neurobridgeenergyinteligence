"""
================================================================================
Project: NeuroBridge 11D Energy Intelligence Kernel
Component: Lattice Authentication Dependency
Version: 1.0.0
Description: Security dependency for FastAPI routes that provides token verification
             and lattice security integration for all API endpoints.
================================================================================
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Header

logger = logging.getLogger("NeuroBridge.Security")


async def verify_token(
    request: Request,
    authorization: str = Header(None),
    x_lattice_token: Optional[str] = Header(None),
    x_lattice_session: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Verify authentication token or quantum session.
    
    This is the primary security dependency for all API routes.
    Supports:
    - Bearer token (classic mode)
    - Lattice token header
    - Quantum session header
    - Development bypass token
    
    Returns:
        Dictionary with authentication details
        
    Raises:
        HTTPException(403) if authentication fails
    """
    # Fast path for development
    if authorization == "Bearer DEV_ABUJA_PILOT_2026":
        return {"authenticated": True, "mode": "DEVELOPMENT"}
    
    # Check for quantum session
    if x_lattice_session:
        # Verify quantum session from app state
        lattice_engine = getattr(request.app.state, 'lattice_engine', None)
        if lattice_engine:
            session = lattice_engine.get_session(x_lattice_session)
            if session and session.tunnel_state.value == "ESTABLISHED":
                logger.debug(f"Quantum session authenticated: {x_lattice_session}")
                return {
                    "authenticated": True,
                    "mode": "QUANTUM",
                    "session_id": x_lattice_session,
                    "security_level": session.security_level.value
                }
    
    # Fall back to classic token verification
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_lattice_token:
        token = x_lattice_token
    
    if not token:
        logger.warning(f"Security violation: Missing authentication")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Lattice Guard: Unauthorized Access",
                "message": "Missing authentication token or quantum session",
                "path": request.url.path
            }
        )
    
    # Verify classic token (from .env)
    expected_code = os.getenv("CTO_ACCESS_CODE")
    
    if not expected_code:
        logger.warning("No active session configured")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Lattice Guard: No Active Session",
                "message": "No CTO_ACCESS_CODE configured in environment"
            }
        )
    
    # Validate token format
    if not token.startswith("CTO-"):
        logger.warning(f"Invalid token format: {token[:12]}...")
        raise HTTPException(status_code=403, detail="Lattice Guard: Invalid token format")
    
    # Validate token
    if token != expected_code:
        logger.warning(f"Security violation: Token mismatch for {request.url.path}")
        raise HTTPException(status_code=403, detail="Lattice Guard: Unauthorized Access")
    
    # Check expiry if available
    expiry_str = os.getenv("SESSION_EXPIRY")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
            now = datetime.now(timezone.utc)
            if now >= expiry:
                logger.warning(f"Session expired: {token[:12]}...")
                raise HTTPException(status_code=403, detail="Lattice Guard: Session Expired")
        except Exception as e:
            logger.debug(f"Expiry check failed: {e}")
    
    logger.debug(f"Token verified: {token[:12]}...")
    
    return {
        "authenticated": True,
        "mode": "CLASSICAL",
        "token": token[:12] + "..."
    }


# Alias for backward compatibility
verify_lattice_guard = verify_token