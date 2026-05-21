"""
NeuroBridge 11D - Core Authentication Utilities
Production-safe authentication module.

Purpose:
- Prevent circular imports from backend.main
- Support existing CTO_ACCESS_CODE
- Support NEUROBRIDGE_API_KEY, CTO_API_KEY, and API_KEY
- Provide FastAPI dependency for protected routes
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger("NeuroBridge.Auth")


@dataclass(frozen=True)
class AuthResult:
    valid: bool
    token_hash: str
    reason: str = "ok"
    token_source: str = "unknown"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_token(token: str) -> str:
    if not token:
        return "EMPTY"
    if len(token) <= 10:
        return "***REDACTED***"
    return f"{token[:6]}...{token[-4:]}"


def get_expected_token() -> str:
    """
    Reads the production token from environment.

    Priority order:
    1. NEUROBRIDGE_API_KEY
    2. CTO_API_KEY
    3. CTO_ACCESS_CODE
    4. API_KEY
    """

    token = (
        os.getenv("NEUROBRIDGE_API_KEY")
        or os.getenv("CTO_API_KEY")
        or os.getenv("CTO_ACCESS_CODE")
        or os.getenv("API_KEY")
        or ""
    ).strip()

    if not token:
        logger.warning("[AUTH] No production API token configured")

    return token


def get_token_source() -> str:
    if os.getenv("NEUROBRIDGE_API_KEY"):
        return "NEUROBRIDGE_API_KEY"
    if os.getenv("CTO_API_KEY"):
        return "CTO_API_KEY"
    if os.getenv("CTO_ACCESS_CODE"):
        return "CTO_ACCESS_CODE"
    if os.getenv("API_KEY"):
        return "API_KEY"
    return "none"


def validate_token(token: Optional[str]) -> AuthResult:
    """
    Validate token using constant-time comparison.
    """

    if not token:
        return AuthResult(
            valid=False,
            token_hash="none",
            reason="missing_token",
            token_source=get_token_source(),
        )

    expected = get_expected_token()
    token_source = get_token_source()

    if not expected:
        return AuthResult(
            valid=False,
            token_hash=_sha256(token),
            reason="server_token_not_configured",
            token_source=token_source,
        )

    valid = hmac.compare_digest(token.strip(), expected.strip())

    if not valid:
        logger.warning("[AUTH] Invalid token attempt: %s", _redact_token(token))

    return AuthResult(
        valid=valid,
        token_hash=_sha256(token),
        reason="ok" if valid else "invalid_token",
        token_source=token_source,
    )


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_lattice_token: Optional[str] = Header(default=None, alias="X-Lattice-Token"),
    x_lattice_session: Optional[str] = Header(default=None, alias="X-Lattice-Session"),
) -> AuthResult:
    """
    FastAPI dependency.

    Supports:
    - X-API-Key: <token>
    - Authorization: Bearer <token>
    - X-Lattice-Token: <token>
    - X-Lattice-Session: <token>
    """

    token = None

    if x_api_key:
        token = x_api_key.strip()

    elif authorization:
        auth_value = authorization.strip()
        if auth_value.lower().startswith("bearer "):
            token = auth_value[7:].strip()
        else:
            token = auth_value

    elif x_lattice_token:
        token = x_lattice_token.strip()

    elif x_lattice_session:
        token = x_lattice_session.strip()

    result = validate_token(token)

    if not result.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized",
                "reason": result.reason,
                "token_source": result.token_source,
                "timestamp": int(time.time()),
            },
        )

    return result