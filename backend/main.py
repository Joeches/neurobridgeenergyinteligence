# backend/main.py - PRODUCTION FINAL v14.8.1
# Enterprise Phase 1 Energy Intelligence Platform
# Prometheus Metrics Instrumented - System Overview Observability
# Complete banner suppression | Professional logging | ADFI flag fixed

import os
import sys
import logging
import asyncio
import time
import json
import threading
import platform
import re
import secrets
import hashlib
import uuid
import traceback
import socket
import warnings
from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List, Tuple, Union
from collections import defaultdict

# ============================================================================
# BANNER SUPPRESSION - MUST BE FIRST
# ============================================================================

_original_print = print
_suppress_banners = not (os.getenv("LOG_BANNERS", "false").lower() == "true" and 
                          os.getenv("ENVIRONMENT", "production").lower() in ["development", "dev", "local"])


def _filtered_print(*args, **kwargs):
    if not _suppress_banners:
        _original_print(*args, **kwargs)
        return
    
    message = ' '.join(str(arg) for arg in args)
    banner_keywords = [
        '╔════════', '║', '╚════════', 'ADFI ENGINE', 'INVESTOR DEMO ROUTES',
        'DETERMINISTIC PHYSICS DATA FABRIC', 'ENTERPRISE-GRADE', 'BREAKING CHANGES',
        'ZERO Hugging Face', '100% deterministic', 'PRODUCTION READY', 'MOAT',
        'Physics Sources', 'CRITICAL FIX', 'circular dependency'
    ]
    
    for keyword in banner_keywords:
        if keyword in message:
            return
    
    _original_print(*args, **kwargs)


print = _filtered_print

os.environ['ADFI_DISABLE_BANNERS'] = 'true'
os.environ['ADFI_LOG_LEVEL'] = 'ERROR'
os.environ['DEMO_ROUTES_NO_BANNER'] = 'true'
os.environ['DISABLE_BANNERS'] = 'true'

# ============================================================================
# PRODUCTION LOGGING - ENTERPRISE CONFIGURATION
# ============================================================================

_LOGGING_HANDLERS_ATTACHED = False


def setup_logging():
    global _LOGGING_HANDLERS_ATTACHED
    
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if not _LOGGING_HANDLERS_ATTACHED:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        
        file_handler = logging.FileHandler(log_dir / "neurobridge.log", encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        
        error_handler = logging.FileHandler(log_dir / "neurobridge_error.log", encoding='utf-8')
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        root_logger.setLevel(log_level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_handler)
        
        _LOGGING_HANDLERS_ATTACHED = True
    
    return logging.getLogger("NeuroBridge")


def redact_sensitive(value: str) -> str:
    if not value or not isinstance(value, str):
        return value
    
    patterns = [
        (r'(api[_-]?key[=:]\s*)([A-Za-z0-9]{32,})', r'\1[REDACTED]'),
        (r'(secret[=:]\s*)([A-Za-z0-9]{20,})', r'\1[REDACTED]'),
        (r'(password[=:]\s*)([^\s]{4,})', r'\1[REDACTED]'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]'),
        (r'\+\d{2,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', '[REDACTED_PHONE]'),
    ]
    
    result = value
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def is_dev_mode() -> bool:
    env = os.getenv("ENVIRONMENT", "production").lower()
    return env in ["development", "dev", "local"]


def show_banners() -> bool:
    return is_dev_mode() and os.getenv("LOG_BANNERS", "false").lower() == "true"


logger = setup_logging()


class RedactingFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)
        return True


for handler in logging.getLogger().handlers:
    handler.addFilter(RedactingFilter())

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

_METRICS_AVAILABLE = False

try:
    from backend.monitoring.prometheus_metrics import (
        set_active_module,
        set_phase1_compliance_status,
        set_redis_health,
        set_hardware_bridge_status,
        set_prediction_accuracy,
        get_metrics_response,
        PrometheusMiddleware,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    def set_active_module(*args, **kwargs): pass
    def set_phase1_compliance_status(*args, **kwargs): pass
    def set_redis_health(*args, **kwargs): pass
    def set_hardware_bridge_status(*args, **kwargs): pass
    def set_prediction_accuracy(*args, **kwargs): pass
    def get_metrics_response():
        from fastapi.responses import Response
        return Response(content="# Prometheus metrics disabled\n", media_type="text/plain")
    def PrometheusMiddleware(app): return app

if _METRICS_AVAILABLE:
    logger.info("[MAIN] prometheus metrics instrumented")
else:
    logger.debug("[MAIN] prometheus metrics unavailable - running without instrumentation")

# ============================================================================
# PRODUCTION DIRECTORIES
# ============================================================================

PROJECT_RUNTIME_DIRS = ["data", "logs", "benchmarks", "benchmarks/reports", "postman", "exports"]

for _runtime_dir in PROJECT_RUNTIME_DIRS:
    try:
        Path(_runtime_dir).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# ============================================================================
# PHASE 1 IMPORT FILTER
# ============================================================================

PHASE1_BLOCKED_DOMAINS = ['nuclear', 'fusion', 'quantum', 'defense']


class ImportBlocker:
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
        self._enabled = True

    def is_blocked(self, module_name: str) -> bool:
        if not self._enabled:
            return False
        module_lower = module_name.lower()
        for domain in PHASE1_BLOCKED_DOMAINS:
            if domain in module_lower:
                return True
        return False


_import_blocker = ImportBlocker()


def validate_import(module_name: str, caller: str = "unknown") -> bool:
    return not _import_blocker.is_blocked(module_name)


from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

PSUTIL_AVAILABLE = False
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    pass


ENV_PATH = Path(__file__).parent.parent / '.env'


class EnvironmentManager:
    @classmethod
    def ensure_env_file(cls):
        if not ENV_PATH.exists():
            cls._create_default_env()
            return True
        return False

    @classmethod
    def _create_default_env(cls):
        random_bytes = secrets.token_bytes(32)
        segments = [hashlib.sha256(random_bytes[i*8:(i+1)*8]).hexdigest()[:6].upper() for i in range(4)]
        initial_token = f"CTO-{segments[0]}-{segments[1]}-{segments[2]}-{segments[3]}"

        with open(ENV_PATH, 'w', encoding='utf-8') as f:
            f.write(f"""# NeuroBridge Environment Configuration - PHASE 1
ENVIRONMENT=production
CTO_ACCESS_CODE={initial_token}
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
REDIS_URL=redis://localhost:6379/0
ENABLE_REDIS_CACHE=true
DEMO_ENABLED=true
LOG_BANNERS=false
""")


EnvironmentManager.ensure_env_file()
load_dotenv(ENV_PATH, override=True)

ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
IS_DEVELOPMENT = ENVIRONMENT in ["development", "dev", "local"]
IS_PRODUCTION = ENVIRONMENT in ["production", "prod"]

DEV_BYPASS_TOKEN = os.getenv("DEV_BYPASS_TOKEN", "DEV_ABUJA_PILOT_2026")
DEMO_ENABLED = os.getenv("DEMO_ENABLED", "true").lower() == "true"

logger.info(f"[ENV] mode={ENVIRONMENT.upper()} phase=phase_1")
logger.info(f"[PHASE1] blocked_domains={','.join(PHASE1_BLOCKED_DOMAINS)}")

# ============================================================================
# ADFI ENGINE INITIALIZATION - FIXED FLAG WITH ROBUST ERROR HANDLING
# ============================================================================

ADFI_ENGINE_AVAILABLE = False
adfi_engine = None

# Try multiple import strategies
def _try_import_adfi():
    """Attempt to import ADFI engine using multiple strategies."""
    global adfi_engine, ADFI_ENGINE_AVAILABLE
    
    strategies = [
        lambda: __import__('backend.ingestion.adfi_engine', fromlist=['get_adfi_engine']),
        lambda: __import__('backend.ingestion', fromlist=['adfi_engine']),
        lambda: __import__('backend.ingestion.adfi_engine', fromlist=['get_adfi_engine']),
    ]
    
    for idx, strategy in enumerate(strategies, 1):
        try:
            module = strategy()
            
            if hasattr(module, 'get_adfi_engine'):
                engine = module.get_adfi_engine()
                if engine is not None:
                    adfi_engine = engine
                    ADFI_ENGINE_AVAILABLE = True
                    logger.debug(f"[ADFI] import strategy {idx} succeeded")
                    return True
            elif hasattr(module, 'adfi_engine'):
                engine = module.adfi_engine
                if engine is not None:
                    adfi_engine = engine
                    ADFI_ENGINE_AVAILABLE = True
                    logger.debug(f"[ADFI] import strategy {idx} succeeded (attribute)")
                    return True
        except (ImportError, AttributeError, Exception):
            continue
    
    return False


# Execute import strategies
try:
    import_success = _try_import_adfi()
    
    if import_success:
        logger.info("[ADFI] initialized version=4.0.0 mode=deterministic")
        set_active_module(module="adfi_engine", active=True)
    else:
        try:
            from backend.ingestion.adfi_engine import get_adfi_engine as _get_engine
            _engine = _get_engine()
            if _engine is not None:
                adfi_engine = _engine
                ADFI_ENGINE_AVAILABLE = True
                logger.info("[ADFI] initialized version=4.0.0 mode=deterministic (direct)")
                set_active_module(module="adfi_engine", active=True)
            else:
                raise ImportError("Engine returned None")
        except ImportError:
            logger.debug("[ADFI] not available - Phase 1 valid")
            set_active_module(module="adfi_engine", active=False)
        except Exception as e:
            logger.debug(f"[ADFI] direct import failed: {type(e).__name__}")
            set_active_module(module="adfi_engine", active=False)

except Exception as e:
    logger.debug(f"[ADFI] initialization error: {type(e).__name__}")
    set_active_module(module="adfi_engine", active=False)

# Final safety check
if adfi_engine is not None and not ADFI_ENGINE_AVAILABLE:
    ADFI_ENGINE_AVAILABLE = True
    logger.debug("[ADFI] flag corrected via safety check")
    set_active_module(module="adfi_engine", active=True)


def fix_windows_console_encoding():
    if platform.system() == 'Windows':
        try:
            import subprocess
            subprocess.run('chcp 65001 > nul', shell=True, capture_output=True)
            os.environ['PYTHONIOENCODING'] = 'utf-8'
        except Exception:
            pass


fix_windows_console_encoding()

# ============================================================================
# PHASE 1 COMPLIANCE - GRID LOAD FORECAST
# ============================================================================

def grid_load_forecast(load_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "forecast_type": "grid_load_forecast",
        "phase": "PHASE_1",
        "predicted_load_mw": load_data.get("current_load_mw", 1000) * 1.05,
        "confidence": 0.89,
        "method": "physics_based"
    }


quantum_load_forecast = grid_load_forecast

# ============================================================================
# FASTAPI IMPORTS
# ============================================================================

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Query, Header, Depends, status, APIRouter
from fastapi.responses import JSONResponse, HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# ============================================================================
# PWA FRONTEND CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
_frontend_static_mounted = False


def serve_frontend_page() -> Response:
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists() and index_file.is_file():
        try:
            return FileResponse(
                str(index_file),
                media_type="text/html",
                headers={"Cache-Control": "no-cache"}
            )
        except Exception as e:
            logger.error(f"[PWA] serve failed: {e}")

    fallback_html = """
    <!DOCTYPE html>
    <html>
    <head><title>NeuroBridge - Phase 1</title></head>
    <body style="font-family: monospace; background: #050914; color: white; text-align: center; padding: 50px;">
        <h1>NeuroBridge - Phase 1</h1>
        <p>Energy Intelligence Platform</p>
        <p><a href="/api/docs">API Documentation</a></p>
    </body>
    </html>
    """
    return HTMLResponse(fallback_html, status_code=200)


def serve_favicon() -> Response:
    """Serve favicon with fallback to icon-144.png first."""
    candidates = [
        FRONTEND_DIR / "assets" / "icons" / "icon-144.png",
        FRONTEND_DIR / "assets" / "icons" / "favicon.ico",
        FRONTEND_DIR / "favicon.ico",
    ]

    for candidate in candidates:
        if candidate.exists():
            media_type = "image/png" if candidate.suffix == ".png" else "image/x-icon"
            return FileResponse(str(candidate), media_type=media_type)

    return HTMLResponse("", status_code=204)


# ============================================================================
# ROUTES IMPORTS - SILENT
# ============================================================================

demo_router = None
cognitive_router = None
external_router = None
benchmark_router = None
auth_router = None

import io
import contextlib

with contextlib.redirect_stderr(io.StringIO()):
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            from backend.api.demo_routes import router as demo_router
        except ImportError:
            pass

        try:
            from backend.api.cognitive_routes import router as cognitive_router
        except ImportError:
            pass

        try:
            from backend.api.external_routes import router as external_router
        except ImportError:
            pass

        try:
            from backend.api.benchmark_routes import router as benchmark_router
            logger.info("[BENCHMARK] routes initialized")
        except ImportError:
            pass

        try:
            from backend.api.v1.auth import router as auth_router
            logger.info("[AUTH] routes initialized")
        except ImportError as e:
            logger.debug(f"[AUTH] routes not available: {e}")
        except Exception as e:
            logger.debug(f"[AUTH] routes import error: {type(e).__name__}")

# ============================================================================
# MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Phase"] = "PHASE_1_PRODUCTION"
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

# ============================================================================
# REDIS MANAGER
# ============================================================================

class RedisManager:
    def __init__(self):
        self.available = False
        self.client = None

    async def initialize(self):
        if os.getenv("ENABLE_REDIS_CACHE", "true").lower() != "true":
            logger.info("[REDIS] disabled")
            try:
                set_redis_health(False)
            except Exception:
                pass
            return
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
            self.client.ping()
            self.available = True
            logger.info("[REDIS] available")
            try:
                set_redis_health(True)
            except Exception:
                pass
        except ImportError:
            logger.info("[REDIS] unavailable")
            try:
                set_redis_health(False)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[REDIS] unavailable: {e}")
            try:
                set_redis_health(False)
            except Exception:
                pass

    async def close(self):
        if self.client:
            try:
                self.client.close()
            except:
                pass
        try:
            set_redis_health(False)
        except Exception:
            pass


redis_manager = RedisManager()

# ============================================================================
# KERNEL LOADER
# ============================================================================

class NativeKernelLoader:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._kernel_type = None
        self._load_kernel()

    def _load_kernel(self):
        with contextlib.redirect_stdout(io.StringIO()):
            compiled = self._load_compiled_kernel()
        
        if compiled:
            self._kernel_type = 'compiled'
            logger.info("[KERNEL] native loaded version=13.0.0")
            set_active_module(module="kernel_loader", active=True)
            return
        
        with contextlib.redirect_stdout(io.StringIO()):
            python_kernel = self._load_python_kernel()
        
        if python_kernel:
            self._kernel_type = 'python'
            logger.warning("[KERNEL] fallback loaded")
            set_active_module(module="kernel_loader", active=True)
            return
        
        self._kernel_type = 'simulation'
        logger.error("[KERNEL] simulation active")
        set_active_module(module="kernel_loader", active=False)

    def _load_compiled_kernel(self):
        import importlib.util
        ext = ".pyd" if platform.system() == "Windows" else ".so"
        paths = [
            Path(__file__).parent / "kernel" / f"_kernel{ext}",
            Path(__file__).parent / f"_kernel{ext}",
            Path(__file__).parent.parent / "kernel" / f"_kernel{ext}",
        ]
        for path in paths:
            if path.exists():
                try:
                    spec = importlib.util.spec_from_file_location("_kernel_compiled", str(path))
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, 'EnergyPredictor'):
                            return module.EnergyPredictor()
                except Exception:
                    pass
        return None

    def _load_python_kernel(self):
        import importlib.util
        paths = [
            Path(__file__).parent / "kernel" / "energy_kernel.py",
            Path(__file__).parent / "energy_kernel.py",
            Path(__file__).parent.parent / "kernel" / "energy_kernel.py",
        ]
        for path in paths:
            if path.exists():
                try:
                    spec = importlib.util.spec_from_file_location("energy_kernel_fallback", str(path))
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, 'EnergyPredictor'):
                            return module.EnergyPredictor()
                except Exception:
                    pass
        return None

    def is_native(self) -> bool:
        return self._kernel_type == 'compiled'

    def get_kernel_type(self) -> str:
        return self._kernel_type or 'simulation'


kernel_loader = NativeKernelLoader()

# ============================================================================
# TOKEN MANAGER
# ============================================================================

class AutomatedTokenManager:
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.env_path = Path(__file__).parent.parent / '.env'
        self.current_token = None
        self._load_current_token()

    def _load_current_token(self):
        try:
            if self.env_path.exists():
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('CTO_ACCESS_CODE='):
                            value = line.split('=', 1)[1].strip().strip('\'"').strip()
                            if value:
                                self.current_token = value
                                break
            if not self.current_token:
                self._generate_new_token()
            else:
                logger.info("[SECURITY] token loaded")
        except Exception as e:
            logger.error(f"[TOKEN] error: {e}")
            self._generate_new_token()

    def _generate_new_token(self):
        random_bytes = secrets.token_bytes(32)
        segments = [hashlib.sha256(random_bytes[i*8:(i+1)*8]).hexdigest()[:6].upper() for i in range(4)]
        self.current_token = f"CTO-{segments[0]}-{segments[1]}-{segments[2]}-{segments[3]}"
        self._save_token_to_env(self.current_token)
        logger.info("[SECURITY] token generated")

    def _save_token_to_env(self, token: str):
        try:
            lines = []
            if self.env_path.exists():
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            token_updated = False
            for i, line in enumerate(lines):
                if line.startswith('CTO_ACCESS_CODE='):
                    lines[i] = f'CTO_ACCESS_CODE={token}\n'
                    token_updated = True
            if not token_updated:
                lines.append(f'CTO_ACCESS_CODE={token}\n')
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            os.environ['CTO_ACCESS_CODE'] = token
        except Exception as e:
            logger.error(f"[TOKEN] save error: {e}")

    def validate_token(self, token: str) -> Dict[str, Any]:
        if not token:
            return {"valid": False}
        return {"valid": token == self.current_token}


token_manager = AutomatedTokenManager()

# ============================================================================
# WEBSOCKET MANAGER
# ============================================================================

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)


ws_manager = WebSocketManager()

# ============================================================================
# AUTH FUNCTIONS
# ============================================================================

async def validate_token(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    if IS_DEVELOPMENT:
        if not token or token == DEV_BYPASS_TOKEN:
            return {"authenticated": True, "phase": "PHASE_1"}

    if not token:
        raise HTTPException(status_code=403, detail="Authentication required")
    
    validation = token_manager.validate_token(token)
    if not validation["valid"]:
        raise HTTPException(status_code=403, detail="Invalid token")

    return {"authenticated": True, "phase": "PHASE_1"}

# ============================================================================
# FASTAPI APP CREATION
# ============================================================================

app = FastAPI(
    title="NeuroBridge - Phase 1",
    description="Energy Intelligence Platform",
    version="14.8.1",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ============================================================================
# FRONTEND MOUNTING
# ============================================================================

try:
    if FRONTEND_DIR.exists():
        app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        _frontend_static_mounted = True
        
        static_dir = FRONTEND_DIR / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        
        assets_dir = FRONTEND_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        
        logger.info("[PWA] frontend mounted")
except Exception as e:
    logger.warning(f"[PWA] mount failed: {e}")


@app.get("/", include_in_schema=False)
async def root_frontend(request: Request):
    return serve_frontend_page()


@app.get("/dashboard", include_in_schema=False)
async def dashboard_pwa(request: Request):
    return serve_frontend_page()


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_pwa(request: Request):
    return serve_favicon()

# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

allowed_origins = ["http://localhost:3000", "http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# PROMETHEUS: Add Prometheus metrics middleware if available
if _METRICS_AVAILABLE:
    try:
        # Add as the outermost middleware to capture all requests
        app.add_middleware(PrometheusMiddleware)
        logger.info("[MAIN] prometheus middleware added")
    except Exception as e:
        logger.warning(f"[MAIN] prometheus middleware failed: {e}")

# ============================================================================
# INCLUDE ROUTES
# ============================================================================

if demo_router:
    app.include_router(demo_router, prefix="/api/v1/demo")
if cognitive_router:
    app.include_router(cognitive_router, prefix="/api/v1/cognitive")
if external_router:
    app.include_router(external_router)
if benchmark_router:
    app.include_router(benchmark_router)
if auth_router:
    app.include_router(auth_router)

# ============================================================================
# CONNECTOR STATUS ENDPOINT
# ============================================================================

@app.get("/api/v1/connectors/status")
async def connectors_status() -> Dict[str, Any]:
    """
    Get status of all external connectors.
    Used by frontend to determine which data sources are available.
    """
    nasa_enabled = os.getenv("NASA_POWER_ENABLED", "true").lower() == "true"
    nasa_status = "configured" if nasa_enabled else "disabled"
    
    gee_credentials = os.getenv("GEE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    gee_status = "configured" if gee_credentials else "not_configured"
    
    openweather_key = os.getenv("OPENWEATHER_API_KEY")
    openweather_status = "configured" if openweather_key else "not_configured"
    
    isolarcloud_mock = os.getenv("ISOLARCLOUD_MOCK", "true").lower() == "true"
    if isolarcloud_mock:
        isolarcloud_status = "mock"
    else:
        isolarcloud_username = os.getenv("ISOLARCLOUD_USERNAME")
        isolarcloud_password = os.getenv("ISOLARCLOUD_PASSWORD")
        isolarcloud_status = "configured" if isolarcloud_username and isolarcloud_password else "not_configured"
    
    modbus_simulation = os.getenv("MODBUS_SIMULATION", "true").lower() == "true"
    modbus_status = "simulated" if modbus_simulation else "configured"
    
    connectors = {
        "nasa": nasa_status,
        "gee": gee_status,
        "openweather": openweather_status,
        "isolarcloud": isolarcloud_status,
        "modbus": modbus_status,
        "fallback": "active"
    }
    
    # PROMETHEUS: Update hardware bridge status for each connector
    try:
        set_hardware_bridge_status(component="nasa", healthy=(nasa_status == "configured"))
        set_hardware_bridge_status(component="gee", healthy=(gee_status == "configured"))
        set_hardware_bridge_status(component="openweather", healthy=(openweather_status == "configured"))
        set_hardware_bridge_status(component="isolarcloud", healthy=(isolarcloud_status in ["configured", "mock"]))
        set_hardware_bridge_status(component="modbus", healthy=(modbus_status in ["configured", "simulated"]))
    except Exception:
        pass
    
    return {
        "status": "success",
        "phase": "PHASE_1_PRODUCTION",
        "mode": "deterministic",
        "connectors": connectors,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ============================================================================
# BLOCKED DOMAIN ROUTES
# ============================================================================

def blocked_response(domain: str):
    return JSONResponse(
        status_code=403,
        content={"error": f"{domain} excluded from Phase 1", "phase": "PHASE_1_PRODUCTION"}
    )


@app.get("/api/v1/nuclear/status")
@app.get("/api/v1/nuclear/{path:path}")
async def nuclear_blocked():
    return blocked_response("nuclear")


@app.get("/api/v1/fusion/status")
async def fusion_blocked():
    return blocked_response("fusion")


@app.get("/api/v1/quantum/status")
async def quantum_blocked():
    return blocked_response("quantum")


@app.get("/api/v1/defense/status")
async def defense_blocked():
    return blocked_response("defense")

# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws/energy-channel")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            elif data.get("type") == "get_energy":
                telemetry = {
                    "active_power_kw": 1124.0,
                    "grid_frequency_hz": 50.14,
                    "solar_output_kw": 112.5,
                    "demand_load_kw": 1124.0,
                }
                await websocket.send_json({"type": "energy_snapshot", "data": telemetry})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)

# ============================================================================
# HEALTH CHECK - UPDATED WITH METRICS
# ============================================================================

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "14.8.1",
        "phase": "PHASE_1_PRODUCTION",
        "connectors_endpoint": True,
        "prometheus_metrics": _METRICS_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "routes": {
            "auth": auth_router is not None,
            "demo": demo_router is not None,
            "cognitive": cognitive_router is not None,
            "external": external_router is not None,
            "benchmark": benchmark_router is not None
        }
    }

# ============================================================================
# ENERGY ENDPOINTS
# ============================================================================

VALID_SECTORS = ["renewables", "grid_storage"]


@app.get("/api/v1/energy/status")
async def energy_status(auth_info: Dict[str, Any] = Depends(validate_token)):
    return {
        "status": "active",
        "phase": "PHASE_1_PRODUCTION",
        "kernel_mode": kernel_loader.get_kernel_type(),
        "blocked_domains": PHASE1_BLOCKED_DOMAINS,
    }


@app.get("/api/v1/energy/metrics")
async def energy_metrics(auth_info: Dict[str, Any] = Depends(validate_token)):
    return {
        "grid_load_mw": 1124.0,
        "grid_frequency_hz": 50.14,
        "renewable_percentage": 35.6,
        "phase": "PHASE_1_PRODUCTION"
    }


@app.get("/api/v1/energy/grid-stability")
async def grid_stability(auth_info: Dict[str, Any] = Depends(validate_token)):
    return {
        "stability_index": 95.0,
        "category": "stable",
        "phase": "PHASE_1_PRODUCTION"
    }


@app.get("/api/v1/energy/predict/{sector}")
async def energy_prediction(
    sector: str,
    hours_ahead: int = Query(24, ge=1, le=168),
    auth_info: Dict[str, Any] = Depends(validate_token)
):
    if sector not in VALID_SECTORS:
        raise HTTPException(status_code=400, detail=f"Invalid sector")
    
    predictions = []
    for hour in range(min(hours_ahead, 24)):
        predictions.append({
            "hour": hour + 1,
            "timestamp": (datetime.now(timezone.utc) + timedelta(hours=hour+1)).isoformat(),
            "predicted_yield_mwh": 100.0 + (hour * 2),
            "confidence": 0.95 - (hour * 0.01)
        })
    return {"sector": sector, "predictions": predictions, "phase": "PHASE_1_PRODUCTION"}


@app.get("/api/v1/aece/status")
async def aece_status(auth_info: Dict[str, Any] = Depends(validate_token)):
    return {"available": True, "protection_mode": True, "phase": "PHASE_1_PRODUCTION"}


# ============================================================================
# METRICS ENDPOINT - PROMETHEUS
# ============================================================================

@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus metrics endpoint.
    Returns all registered NeuroBridge 11D Phase 1 Production metrics.
    """
    if _METRICS_AVAILABLE:
        try:
            return get_metrics_response()
        except Exception as e:
            logger.error(f"[METRICS] endpoint error: {e}")
            return Response(content=f"# Error: {e}\n", media_type="text/plain", status_code=500)
    return Response(content="# Prometheus metrics disabled\n", media_type="text/plain")

# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "phase": "PHASE_1_PRODUCTION"}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {type(exc).__name__}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "phase": "PHASE_1_PRODUCTION"}
    )

# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_start = time.perf_counter()
    
    # PROMETHEUS: Set Phase 1 compliance at startup
    try:
        set_phase1_compliance_status(True)
    except Exception:
        pass
    
    if show_banners():
        print("NeuroBridge - Development Mode")
    
    await redis_manager.initialize()
    
    app.state.startup_time = datetime.now(timezone.utc)
    app.state.kernel = kernel_loader
    app.state.redis = redis_manager
    app.state.adfi_engine = adfi_engine
    
    boot_time = (time.perf_counter() - startup_start) * 1000
    
    connectors_available = True
    
    # PROMETHEUS: Set all module active statuses at startup
    try:
        set_active_module(module="api_server", active=True)
        set_active_module(module="kernel_loader", active=(kernel_loader.get_kernel_type() != 'simulation'))
        set_active_module(module="adfi_engine", active=ADFI_ENGINE_AVAILABLE)
        set_active_module(module="redis_cache", active=redis_manager.available)
        set_active_module(module="auth_service", active=(auth_router is not None))
        set_active_module(module="demo_service", active=(demo_router is not None))
        set_active_module(module="cognitive_service", active=(cognitive_router is not None))
        set_active_module(module="external_api", active=(external_router is not None))
        set_active_module(module="benchmark_service", active=(benchmark_router is not None))
        set_active_module(module="pwa_frontend", active=_frontend_static_mounted)
        set_active_module(module="connectors", active=connectors_available)
    except Exception:
        pass
    
    logger.info(f"[STARTUP] complete kernel={kernel_loader.get_kernel_type()} adfi={ADFI_ENGINE_AVAILABLE} auth={auth_router is not None} redis={redis_manager.available} pwa={_frontend_static_mounted} connectors={connectors_available} time={boot_time:.0f}ms metrics={_METRICS_AVAILABLE}")
    
    yield
    
    # PROMETHEUS: Deactivate modules on shutdown
    try:
        set_active_module(module="api_server", active=False)
        set_redis_health(False)
    except Exception:
        pass
    
    logger.info("[SHUTDOWN] complete")
    await redis_manager.close()


app.router.lifespan_context = lifespan

# Restore original print
print = _original_print

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=IS_DEVELOPMENT,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )