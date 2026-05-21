
import os
import re
import time
import secrets
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Union, Callable
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Request, Depends, Header
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.core.redis import redis_client, rate_limiter

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token types
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
API_KEY_TYPE = "api_key"

# Role definitions
class Role(str, Enum):
    CTO = "cto"
    ADMIN = "admin"
    PARTNER = "partner"
    PILOT = "pilot"
    VIEWER = "viewer"
    SYSTEM = "system"


# Permission definitions
class Permission(str, Enum):
    # Energy permissions
    VIEW_ENERGY_DATA = "view_energy_data"
    SIMULATE_ENERGY = "simulate_energy"
    EXPORT_ENERGY_REPORT = "export_energy_report"
    
    # Control permissions
    EXECUTE_CONTROL_ACTION = "execute_control_action"
    VIEW_CONTROL_STATUS = "view_control_status"
    RESET_PROTECTION = "reset_protection"
    
    # Nuclear permissions
    VIEW_NUCLEAR_DATA = "view_nuclear_data"
    SIMULATE_NUCLEAR = "simulate_nuclear"
    
    # Admin permissions
    MANAGE_USERS = "manage_users"
    MANAGE_API_KEYS = "manage_api_keys"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    SYSTEM_CONFIG = "system_config"


# Role to permissions mapping
ROLE_PERMISSIONS = {
    Role.CTO: [
        Permission.VIEW_ENERGY_DATA,
        Permission.SIMULATE_ENERGY,
        Permission.EXPORT_ENERGY_REPORT,
        Permission.EXECUTE_CONTROL_ACTION,
        Permission.VIEW_CONTROL_STATUS,
        Permission.RESET_PROTECTION,
        Permission.VIEW_NUCLEAR_DATA,
        Permission.SIMULATE_NUCLEAR,
        Permission.MANAGE_USERS,
        Permission.MANAGE_API_KEYS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.SYSTEM_CONFIG,
    ],
    Role.ADMIN: [
        Permission.VIEW_ENERGY_DATA,
        Permission.SIMULATE_ENERGY,
        Permission.EXPORT_ENERGY_REPORT,
        Permission.VIEW_CONTROL_STATUS,
        Permission.VIEW_NUCLEAR_DATA,
        Permission.MANAGE_USERS,
        Permission.VIEW_AUDIT_LOGS,
    ],
    Role.PARTNER: [
        Permission.VIEW_ENERGY_DATA,
        Permission.EXPORT_ENERGY_REPORT,
        Permission.VIEW_CONTROL_STATUS,
    ],
    Role.PILOT: [
        Permission.VIEW_ENERGY_DATA,
        Permission.VIEW_CONTROL_STATUS,
    ],
    Role.VIEWER: [
        Permission.VIEW_ENERGY_DATA,
    ],
    Role.SYSTEM: [
        Permission.VIEW_ENERGY_DATA,
        Permission.VIEW_CONTROL_STATUS,
        Permission.EXECUTE_CONTROL_ACTION,
        Permission.RESET_PROTECTION,
    ],
}


# ============================================================================
# TOKEN BLACKLIST
# ============================================================================

class TokenBlacklist:
    """Redis-based token blacklist for logout and revocation"""
    
    def __init__(self):
        self.redis = redis_client
        self.prefix = "blacklist:token:"
    
    def add(self, token: str, expires_in: int) -> bool:
        """Add token to blacklist"""
        key = f"{self.prefix}{token}"
        return self.redis.set(key, "revoked", expires_in)
    
    def is_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        key = f"{self.prefix}{token}"
        return self.redis.exists(key)
    
    def remove(self, token: str) -> bool:
        """Remove token from blacklist"""
        key = f"{self.prefix}{token}"
        return self.redis.delete(key)


# ============================================================================
# API KEY MANAGER
# ============================================================================

class ApiKeyManager:
    """API key management for partner access"""
    
    def __init__(self):
        self.redis = redis_client
        self.prefix = "api_key:"
    
    def generate_api_key(self, name: str, role: Role, expires_days: int = 365) -> str:
        """Generate a new API key"""
        # Generate random key
        key = f"NB_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        # Store key info
        key_data = {
            "name": name,
            "role": role.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat(),
            "last_used": None,
            "usage_count": 0,
        }
        
        self.redis.set(f"{self.prefix}{key_hash}", key_data, expires_days * 86400)
        return key
    
    def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Validate API key and return key data"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self.redis.get(f"{self.prefix}{key_hash}")
        
        if not key_data:
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(key_data["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            return None
        
        # Update last used and usage count
        key_data["last_used"] = datetime.now(timezone.utc).isoformat()
        key_data["usage_count"] += 1
        self.redis.set(f"{self.prefix}{key_hash}", key_data)
        
        return key_data
    
    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return self.redis.delete(f"{self.prefix}{key_hash}")
    
    def get_api_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get API key information without updating usage"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return self.redis.get(f"{self.prefix}{key_hash}")


# ============================================================================
# JWT TOKEN FUNCTIONS
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": ACCESS_TOKEN_TYPE,
        "iat": datetime.now(timezone.utc),
    })
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "type": REFRESH_TOKEN_TYPE,
        "iat": datetime.now(timezone.utc),
    })
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # Check if token is blacklisted
        if token_blacklist.is_blacklisted(token):
            logger.warning(f"Blacklisted token used: {token[:20]}...")
            return None
        
        return payload
    except JWTError as e:
        logger.warning(f"Token decode failed: {e}")
        return None


def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Refresh access token using refresh token"""
    payload = decode_token(refresh_token)
    
    if not payload or payload.get("type") != REFRESH_TOKEN_TYPE:
        return None
    
    # Create new access token
    user_id = payload.get("sub")
    role = payload.get("role")
    
    if not user_id:
        return None
    
    return create_access_token({"sub": user_id, "role": role})


# ============================================================================
# TOKEN BLACKLIST INSTANCE
# ============================================================================

token_blacklist = TokenBlacklist()


# ============================================================================
# RATE LIMITING DECORATOR
# ============================================================================

def rate_limit(limit: int, window: int, key_func: Optional[Callable] = None):
    """
    Rate limiting decorator for endpoints
    
    Args:
        limit: Maximum requests per window
        window: Time window in seconds
        key_func: Function to extract rate limit key from request
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args
            request = None
            for arg in args:
                if hasattr(arg, "client") and hasattr(arg, "headers"):
                    request = arg
                    break
            
            if request is None:
                return await func(*args, **kwargs)
            
            # Get rate limit key
            if key_func:
                key = key_func(request)
            else:
                # Default: use client IP
                client_ip = request.client.host if request.client else "unknown"
                key = f"{func.__name__}:{client_ip}"
            
            # Check rate limit
            if not rate_limiter.check(key, limit, window):
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Limit: {limit} requests per {window} seconds"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# ROLE-BASED ACCESS CONTROL
# ============================================================================

def require_role(allowed_roles: List[Union[Role, str]]):
    """Decorator to require specific role for endpoint"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from kwargs (set by auth dependency)
            user = kwargs.get("user")
            
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            user_role = user.get("role")
            if user_role not in [r.value if isinstance(r, Role) else r for r in allowed_roles]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied. Required roles: {allowed_roles}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_permission(permission: Permission):
    """Decorator to require specific permission for endpoint"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user")
            
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            user_role = user.get("role")
            allowed_permissions = ROLE_PERMISSIONS.get(Role(user_role), [])
            
            if permission not in allowed_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied. Required permission: {permission.value}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user.
    Supports both JWT and API key authentication.
    """
    # Try API key first
    if x_api_key:
        api_key_data = api_key_manager.validate_api_key(x_api_key)
        if api_key_data:
            return {
                "user_id": f"api_key_{api_key_data['name']}",
                "role": api_key_data["role"],
                "auth_type": API_KEY_TYPE,
                "name": api_key_data["name"],
            }
    
    # Try JWT token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        payload = decode_token(token)
        
        if payload:
            return {
                "user_id": payload.get("sub"),
                "role": payload.get("role", Role.VIEWER.value),
                "auth_type": ACCESS_TOKEN_TYPE,
                "exp": payload.get("exp"),
            }
    
    raise HTTPException(status_code=401, detail="Invalid authentication credentials")


async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get current active user (for endpoints requiring authentication)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user


async def get_current_cto_user(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get current CTO user (for admin endpoints)"""
    if current_user.get("role") != Role.CTO.value:
        raise HTTPException(status_code=403, detail="CTO access required")
    return current_user


# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


# ============================================================================
# AUDIT LOGGING
# ============================================================================

class SecurityAuditLogger:
    """Security event audit logging"""
    
    def __init__(self):
        self.redis = redis_client
        self.prefix = "audit:security:"
    
    def log_event(
        self,
        event_type: str,
        user_id: str,
        action: str,
        details: Dict[str, Any],
        success: bool = True
    ) -> None:
        """Log security event"""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "action": action,
            "details": details,
            "success": success,
            "ip_address": None,  # Would be set from request
        }
        
        # Store in Redis list (keep last 10000 events)
        key = f"{self.prefix}{event_type}"
        self.redis.lpush(key, event)
        self.redis.ltrim(key, 0, 9999)
        self.redis.expire(key, 30 * 86400)  # 30 days
        
        # Log to file as well
        logger.info(f"[SECURITY] {event_type}: user={user_id}, action={action}, success={success}")
    
    def get_events(self, event_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent security events"""
        key = f"{self.prefix}{event_type}"
        return self.redis.lrange(key, 0, limit - 1)


# ============================================================================
# BRUTE FORCE PROTECTION
# ============================================================================

class BruteForceProtector:
    """Brute force protection for authentication endpoints"""
    
    def __init__(self):
        self.redis = redis_client
        self.prefix = "bruteforce:"
        self.max_attempts = 5
        self.lockout_minutes = 15
    
    def record_failed_attempt(self, identifier: str) -> int:
        """Record a failed authentication attempt"""
        key = f"{self.prefix}{identifier}"
        attempts = self.redis.incr(key)
        if attempts == 1:
            self.redis.expire(key, 60)  # Reset after 1 minute if no more attempts
        return attempts
    
    def is_locked_out(self, identifier: str) -> bool:
        """Check if identifier is locked out"""
        key = f"{self.prefix}{identifier}"
        attempts = self.redis.get(key) or 0
        
        if attempts >= self.max_attempts:
            # Check if lockout period has passed
            lockout_key = f"{key}:lockout"
            if not self.redis.exists(lockout_key):
                self.redis.set(lockout_key, "locked", self.lockout_minutes * 60)
                return True
            return False
        return False
    
    def reset_attempts(self, identifier: str) -> bool:
        """Reset failed attempts for identifier"""
        key = f"{self.prefix}{identifier}"
        lockout_key = f"{key}:lockout"
        self.redis.delete(key, lockout_key)
        return True


# ============================================================================
# REQUEST SIGNING (for webhooks)
# ============================================================================

def sign_request(payload: Dict[str, Any], secret: str) -> str:
    """Sign a request payload using HMAC-SHA256"""
    message = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature


def verify_signature(payload: Dict[str, Any], signature: str, secret: str) -> bool:
    """Verify request signature"""
    expected = sign_request(payload, secret)
    return hmac.compare_digest(signature, expected)


# ============================================================================
# IP WHITELISTING
# ============================================================================

class IPWhitelist:
    """IP whitelist for admin endpoints"""
    
    def __init__(self):
        self.redis = redis_client
        self.prefix = "whitelist:ip:"
    
    def add_ip(self, ip: str, description: str = "") -> bool:
        """Add IP to whitelist"""
        key = f"{self.prefix}{ip}"
        data = {
            "ip": ip,
            "description": description,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.redis.set(key, data, 30 * 86400)  # 30 days
    
    def remove_ip(self, ip: str) -> bool:
        """Remove IP from whitelist"""
        key = f"{self.prefix}{ip}"
        return self.redis.delete(key)
    
    def is_whitelisted(self, ip: str) -> bool:
        """Check if IP is whitelisted"""
        key = f"{self.prefix}{ip}"
        return self.redis.exists(key)
    
    def get_all_ips(self) -> List[str]:
        """Get all whitelisted IPs"""
        pattern = f"{self.prefix}*"
        keys = self.redis.keys(pattern)
        return [k.replace(self.prefix, "") for k in keys]


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

api_key_manager = ApiKeyManager()
security_audit = SecurityAuditLogger()
brute_force_protector = BruteForceProtector()
ip_whitelist = IPWhitelist()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Password hashing
    'verify_password',
    'get_password_hash',
    
    # JWT tokens
    'create_access_token',
    'create_refresh_token',
    'decode_token',
    'refresh_access_token',
    'token_blacklist',
    
    # API keys
    'api_key_manager',
    'ApiKeyManager',
    
    # Rate limiting
    'rate_limit',
    
    # RBAC
    'Role',
    'Permission',
    'require_role',
    'require_permission',
    'ROLE_PERMISSIONS',
    
    # Authentication dependencies
    'get_current_user',
    'get_current_active_user',
    'get_current_cto_user',
    
    # Middleware
    'SecurityHeadersMiddleware',
    
    # Security utilities
    'security_audit',
    'brute_force_protector',
    'ip_whitelist',
    'sign_request',
    'verify_signature',
    
    # Constants
    'ACCESS_TOKEN_TYPE',
    'REFRESH_TOKEN_TYPE',
    'API_KEY_TYPE',
]