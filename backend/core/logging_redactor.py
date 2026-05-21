
import re
import logging
import os
from typing import Dict, Any, Optional, Pattern, Match, List, Tuple
from functools import wraps
import threading

# ============================================================================
# REDACTION PATTERNS - PRODUCTION GRADE
# ============================================================================

class RedactionPatterns:
    """Central repository of all redaction patterns."""
    
    # Pattern for API keys with common formats
    API_KEY_PATTERNS = {
        # Generic API key (alphanumeric, 16-64 chars)
        'generic_api_key': re.compile(
            r'(api[_-]?key|apikey|api_key)[:=]\s*["\']?([a-zA-Z0-9]{16,64})["\']?',
            re.IGNORECASE
        ),
        # OpenWeather API key (32 chars, hex)
        'openweather': re.compile(
            r'(06582f7b[a-f0-9]{24})',
            re.IGNORECASE
        ),
        # Sungrow API key format
        'sungrow': re.compile(
            r'(y8jzhrhq[a-zA-Z0-9]{20,40})',
            re.IGNORECASE
        ),
        # Generic hex API key (32-64 hex chars)
        'hex_api_key': re.compile(
            r'([a-f0-9]{32,64})',
            re.IGNORECASE
        ),
        # Bearer token pattern
        'bearer_token': re.compile(
            r'(Bearer\s+)([a-zA-Z0-9._-]{20,200})',
            re.IGNORECASE
        ),
    }
    
    # Token patterns
    TOKEN_PATTERNS = {
        'access_token': re.compile(
            r'(access[_-]?token|refresh[_-]?token)[:=]\s*["\']?([a-zA-Z0-9._-]{20,200})["\']?',
            re.IGNORECASE
        ),
        'jwt_token': re.compile(
            r'(eyJ[a-zA-Z0-9._-]+)\.(eyJ[a-zA-Z0-9._-]+)\.([a-zA-Z0-9._-]+)',
            re.IGNORECASE
        ),
        'simple_token': re.compile(
            r'(token|auth_token)[:=]\s*["\']?([a-zA-Z0-9]{20,100})["\']?',
            re.IGNORECASE
        ),
    }
    
    # Password/Secret patterns
    SECRET_PATTERNS = {
        'password': re.compile(
            r'(password|passwd|pwd|secret|client_secret)[:=]\s*["\']?([^"\'{}\s]{4,50})["\']?',
            re.IGNORECASE
        ),
        'private_key': re.compile(
            r'(BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY)',
            re.IGNORECASE
        ),
    }
    
    # Sensitive headers
    HEADER_PATTERNS = {
        'authorization': re.compile(
            r'(Authorization|X-API-Key|X-Auth-Token)[:=]\s*["\']?([^"\'{}\s]{10,200})',
            re.IGNORECASE
        ),
    }
    
    # PII patterns
    PII_PATTERNS = {
        'email': re.compile(
            r'[\w\.-]+@[\w\.-]+\.\w+',
            re.IGNORECASE
        ),
        'ip_address': re.compile(
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
        ),
    }
    
    # Known key prefixes (partial redaction)
    KEY_PREFIXES = {
        'sungrow_prefix': 'y8jzhrhq',
        'openweather_prefix': '06582f7b',
        'jwt_prefix': 'eyJ',
    }
    
    @classmethod
    def get_all_patterns(cls) -> List[Tuple[str, Pattern]]:
        """Get all redaction patterns as list of (name, pattern)."""
        patterns = []
        patterns.extend(cls.API_KEY_PATTERNS.items())
        patterns.extend(cls.TOKEN_PATTERNS.items())
        patterns.extend(cls.SECRET_PATTERNS.items())
        patterns.extend(cls.HEADER_PATTERNS.items())
        patterns.extend(cls.PII_PATTERNS.items())
        return patterns


# ============================================================================
# LOG REDACTOR CORE ENGINE
# ============================================================================

class LogRedactor:
    """
    Enterprise-grade log redaction engine.
    Thread-safe, high-performance, production-ready.
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # Redaction marker
        self.REDACTED = "***REDACTED***"
        self.REDACTED_PARTIAL = "***...***"
        
        # Compile all patterns
        self._patterns: List[Tuple[str, Pattern]] = []
        for name, pattern in RedactionPatterns.get_all_patterns():
            self._patterns.append((name, pattern))
        
        # Statistics for monitoring
        self._redaction_count = 0
        self._pattern_hits: Dict[str, int] = {}
        self._stats_lock = threading.RLock()
        
        # Performance optimization: cache recently redacted strings
        self._cache: Dict[str, str] = {}
        self._cache_max_size = 1000
        self._cache_lock = threading.RLock()
        
        # Feature flags (from environment)
        self.redact_pii = os.getenv("LOG_REDACT_PII", "true").lower() == "true"
        self.redact_tokens = os.getenv("LOG_REDACT_TOKENS", "true").lower() == "true"
        self.redact_api_keys = os.getenv("LOG_REDACT_API_KEYS", "true").lower() == "true"
        
        logger = logging.getLogger(__name__)
        logger.info(f"[LogRedactor] ✅ Initialized | PII: {self.redact_pii} | Tokens: {self.redact_tokens} | API Keys: {self.redact_api_keys}")
    
    def redact(self, message: str) -> str:
        """
        Redact sensitive information from a log message.
        
        Args:
            message: Original log message (may contain sensitive data)
        
        Returns:
            Redacted log message with all sensitive data masked
        """
        if not isinstance(message, str):
            return str(message)
        
        # Check cache first (performance optimization)
        cache_key = hash(message) if len(message) < 500 else None
        if cache_key is not None:
            with self._cache_lock:
                if cache_key in self._cache:
                    return self._cache[cache_key]
        
        redacted = message
        
        # Apply all patterns
        for pattern_name, pattern in self._patterns:
            # Skip PII patterns if disabled
            if pattern_name == 'email' and not self.redact_pii:
                continue
            if pattern_name == 'ip_address' and not self.redact_pii:
                continue
            
            # Skip token patterns if disabled
            if 'token' in pattern_name and not self.redact_tokens:
                continue
            
            # Skip API key patterns if disabled
            if ('api_key' in pattern_name or pattern_name in ['openweather', 'sungrow', 'hex_api_key']) and not self.redact_api_keys:
                continue
            
            try:
                # Apply pattern replacement
                new_redacted = pattern.sub(self._replace_match, redacted)
                if new_redacted != redacted:
                    # Count hits for monitoring
                    with self._stats_lock:
                        self._redaction_count += 1
                        self._pattern_hits[pattern_name] = self._pattern_hits.get(pattern_name, 0) + 1
                    redacted = new_redacted
            except Exception as e:
                # Never let redaction failure break logging
                pass
        
        # Also handle known key prefixes (partial redaction)
        for prefix_name, prefix in RedactionPatterns.KEY_PREFIXES.items():
            if prefix in redacted:
                redacted = redacted.replace(prefix, f"{prefix}{self.REDACTED_PARTIAL}")
        
        # Cache the result
        if cache_key is not None:
            with self._cache_lock:
                if len(self._cache) < self._cache_max_size:
                    self._cache[cache_key] = redacted
        
        return redacted
    
    def _replace_match(self, match: Match) -> str:
        """
        Replace a matched pattern with redacted version.
        Preserves the key/field name while redacting the value.
        """
        groups = match.groups()
        
        # If there's a group representing the key/field name, preserve it
        if len(groups) >= 2:
            # Pattern with key and value: key=value
            return f"{groups[0]}={self.REDACTED}"
        elif len(groups) == 1:
            # Pattern with just the value
            return self.REDACTED
        else:
            # Full match replacement
            return self.REDACTED
    
    def redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively redact sensitive values in a dictionary.
        
        Args:
            data: Dictionary that may contain sensitive values
        
        Returns:
            Deep copy of dictionary with sensitive values redacted
        """
        if not isinstance(data, dict):
            return data
        
        redacted = {}
        sensitive_keys = [
            'api_key', 'apikey', 'apiKey', 'API_KEY',
            'token', 'access_token', 'refresh_token', 'bearer',
            'password', 'passwd', 'secret', 'client_secret',
            'authorization', 'Authorization', 'AUTHORIZATION',
            'private_key', 'ssh_key'
        ]
        
        for key, value in data.items():
            if key.lower() in [k.lower() for k in sensitive_keys]:
                redacted[key] = self.REDACTED
            elif isinstance(value, dict):
                redacted[key] = self.redact_dict(value)
            elif isinstance(value, str):
                redacted[key] = self.redact(value)
            else:
                redacted[key] = value
        
        return redacted
    
    def redact_list(self, data: List[Any]) -> List[Any]:
        """
        Redact sensitive values in a list.
        
        Args:
            data: List that may contain sensitive values
        
        Returns:
            New list with sensitive values redacted
        """
        if not isinstance(data, list):
            return data
        
        redacted = []
        for item in data:
            if isinstance(item, dict):
                redacted.append(self.redact_dict(item))
            elif isinstance(item, list):
                redacted.append(self.redact_list(item))
            elif isinstance(item, str):
                redacted.append(self.redact(item))
            else:
                redacted.append(item)
        
        return redacted
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get redaction statistics for monitoring."""
        with self._stats_lock:
            return {
                "total_redactions": self._redaction_count,
                "pattern_hits": dict(self._pattern_hits),
                "cache_size": len(self._cache),
                "redact_pii_enabled": self.redact_pii,
                "redact_tokens_enabled": self.redact_tokens,
                "redact_api_keys_enabled": self.redact_api_keys,
            }
    
    def reset_statistics(self):
        """Reset redaction statistics."""
        with self._stats_lock:
            self._redaction_count = 0
            self._pattern_hits.clear()
        
        with self._cache_lock:
            self._cache.clear()


# ============================================================================
# LOGGING FILTER - Integrates with Python logging
# ============================================================================

class RedactingFilter(logging.Filter):
    """
    Logging filter that redacts sensitive information.
    Add this filter to any logger or handler.
    
    Usage:
        logger.addFilter(RedactingFilter())
    """
    
    def __init__(self, name: str = ""):
        super().__init__(name)
        self._redactor = LogRedactor()
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records, redacting sensitive data.
        Returns True to keep the record (always keeps, just modifies).
        """
        try:
            # Redact the message
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                record.msg = self._redactor.redact(record.msg)
            
            # Redact arguments
            if hasattr(record, 'args') and record.args:
                if isinstance(record.args, tuple):
                    new_args = []
                    for arg in record.args:
                        if isinstance(arg, str):
                            new_args.append(self._redactor.redact(arg))
                        elif isinstance(arg, dict):
                            new_args.append(self._redactor.redact_dict(arg))
                        elif isinstance(arg, list):
                            new_args.append(self._redactor.redact_list(arg))
                        else:
                            new_args.append(arg)
                    record.args = tuple(new_args)
                elif isinstance(record.args, dict):
                    record.args = self._redactor.redact_dict(record.args)
        except Exception as e:
            # Never let redaction failure break logging
            pass
        
        return True


# ============================================================================
# LOGGING HANDLER WRAPPER - Protects all handlers
# ============================================================================

class SafeLoggingHandler(logging.Handler):
    """
    Wrapper handler that ensures all logs are redacted before output.
    
    Usage:
        handler = SafeLoggingHandler(base_handler)
        logger.addHandler(handler)
    """
    
    def __init__(self, base_handler: logging.Handler):
        super().__init__()
        self.base_handler = base_handler
        self._redactor = LogRedactor()
        self.setLevel(base_handler.level)
        self.setFormatter(base_handler.formatter)
    
    def emit(self, record: logging.LogRecord):
        """Emit redacted log record."""
        try:
            # Redact the record
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                record.msg = self._redactor.redact(record.msg)
            
            # Delegate to base handler
            self.base_handler.emit(record)
        except Exception as e:
            # Fallback: emit without redaction (better than losing logs)
            self.base_handler.emit(record)
    
    def flush(self):
        self.base_handler.flush()
    
    def close(self):
        self.base_handler.close()
        super().close()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_global_redactor: Optional[LogRedactor] = None
_global_filter: Optional[RedactingFilter] = None


def get_redactor() -> LogRedactor:
    """Get global log redactor instance."""
    global _global_redactor
    if _global_redactor is None:
        _global_redactor = LogRedactor()
    return _global_redactor


def apply_log_redaction():
    """
    Apply redaction to ALL existing loggers and handlers.
    Call this once at application startup.
    
    This is the main entry point for enabling log redaction.
    """
    redactor = get_redactor()
    redacting_filter = RedactingFilter()
    
    # Apply to root logger
    root_logger = logging.getLogger()
    root_logger.addFilter(redacting_filter)
    
    # Apply to all existing loggers
    for name in logging.root.manager.loggerDict:
        logger_obj = logging.getLogger(name)
        # Check if filter already exists to avoid duplicates
        has_filter = any(isinstance(f, RedactingFilter) for f in logger_obj.filters)
        if not has_filter:
            logger_obj.addFilter(redacting_filter)
    
    # Also wrap all existing handlers (optional, for extra protection)
    for handler in root_logger.handlers[:]:
        if not isinstance(handler, SafeLoggingHandler):
            safe_handler = SafeLoggingHandler(handler)
            root_logger.removeHandler(handler)
            root_logger.addHandler(safe_handler)
    
    logger = logging.getLogger(__name__)
    logger.info("[SECURITY] ✅ Log redaction active - All API keys and tokens will be redacted")
    
    # Log a test message to verify redaction (this should show redacted)
    test_key = "test_api_key_12345"
    logger.debug(f"[SECURITY] Test redaction: api_key={test_key}")
    
    return redactor


def redact_string(message: str) -> str:
    """Convenience function to redact a single string."""
    return get_redactor().redact(message)


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to redact a dictionary."""
    return get_redactor().redact_dict(data)


def get_redaction_stats() -> Dict[str, Any]:
    """Get redaction statistics for monitoring."""
    return get_redactor().get_statistics()


# ============================================================================
# MIDDLEWARE FOR FASTAPI (Optional)
# ============================================================================

class LogRedactionMiddleware:
    """
    FastAPI middleware to redact sensitive data in request/response logs.
    
    Usage:
        app.add_middleware(LogRedactionMiddleware)
    """
    
    def __init__(self, app):
        self.app = app
        self.redactor = get_redactor()
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Redact headers in request logs
        if "headers" in scope:
            headers = dict(scope["headers"])
            # Redact Authorization header
            for key in [b'authorization', b'x-api-key', b'x-auth-token']:
                if key in headers:
                    headers[key] = b"***REDACTED***"
            scope["headers"] = list(headers.items())
        
        await self.app(scope, receive, send)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'LogRedactor',
    'RedactingFilter',
    'SafeLoggingHandler',
    'apply_log_redaction',
    'redact_string',
    'redact_dict',
    'get_redaction_stats',
    'LogRedactionMiddleware',
]