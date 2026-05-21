"""
================================================================================
Project: NeuroBridge 11D Energy Intelligence Kernel
Component: Pytest Configuration & Fixtures (V3.0.0-QUANTUM)
Description: Enterprise-grade test configuration with comprehensive fixtures
             for all system components including security, API clients,
             database mocks, and performance testing utilities.
Author: Lead QA Architect
License: Sovereign Proprietary - Abuja Pilot Deployment
FIX: Corrected pytest_configure implementation, suppressed all warnings
================================================================================
"""

import os
import sys
import pytest
import asyncio
import logging
import json
import time
import warnings
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Generator, AsyncGenerator, List, Optional, Tuple
from pathlib import Path

# ============================================================================
# SUPPRESS NON-CRITICAL WARNINGS FOR CLEAN TEST OUTPUT
# ============================================================================

# Suppress requests/urllib3 dependency warnings
warnings.filterwarnings("ignore", category=UserWarning, module="requests")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="requests")
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")

# Suppress GEE deprecation warnings (from earthengine-api library)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="ee")
warnings.filterwarnings("ignore", category=FutureWarning, module="ee")

# Suppress general deprecation warnings from third-party libraries
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="numpy")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pandas")

# Suppress asyncio warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="asyncio")

# Keep critical warnings for debugging
warnings.filterwarnings("default", category=RuntimeWarning, module="backend")
warnings.filterwarnings("default", category=UserWarning, module="backend")

print("✅ Warning filters applied for clean test output")

# ============================================================================
# PATH CONFIGURATION
# ============================================================================

# Add project root to Python path
BASE_DIR = Path(__file__).parent.parent.absolute()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ============================================================================
# LOGGING CONFIGURATION FOR TESTS
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def configure_test_logging():
    """Configure logging for test environment with suppressed warnings"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Silence noisy loggers during tests
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Reduce GEE logging noise
    logging.getLogger("ee").setLevel(logging.ERROR)
    
    yield

# ============================================================================
# PYTEST CONFIGURATION - FIXED VERSION
# ============================================================================

def pytest_configure(config):
    """
    Configure pytest markers and warning filters.
    FIXED: Removed incorrect addini() call.
    """
    # Add custom markers
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security tests"
    )
    config.addinivalue_line(
        "markers", "adfi: marks tests as ADFI tests"
    )
    
    # Set warning filters via command line equivalent
    # This is handled by the warnings module above
    
    print("✅ Pytest markers configured")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names"""
    for item in items:
        # Add integration marker for test files with integration in name
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)
        
        # Add performance marker for performance tests
        if "performance" in item.nodeid.lower():
            item.add_marker(pytest.mark.performance)
        
        # Add security marker for security tests
        if "security" in item.nodeid.lower() or "auth" in item.nodeid.lower():
            item.add_marker(pytest.mark.security)

# ============================================================================
# SECURITY FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def lattice_session() -> str:
    """
    Create and inject a valid Lattice session for all tests.
    This ensures consistent authentication across the test suite.
    """
    from backend.utils.crypto_lattice import LatticeSecurityEngine
    
    # Generate high-entropy session
    engine = LatticeSecurityEngine()
    code, expiry = engine.provision_access()
    
    # Inject into class state
    LatticeSecurityEngine._active_code = code
    LatticeSecurityEngine._expiry_time = expiry
    
    # Update environment for subprocesses
    os.environ["CTO_ACCESS_CODE"] = code
    os.environ["SESSION_EXPIRY"] = expiry.isoformat()
    
    print(f"\n🔐 Lattice Session Created: {code[:12]}... (expires in 55 minutes)")
    
    return code

@pytest.fixture
def auth_headers(lattice_session: str) -> Dict[str, str]:
    """Return authentication headers with valid token"""
    return {"Authorization": f"Bearer {lattice_session}"}

@pytest.fixture
def invalid_auth_headers() -> Dict[str, str]:
    """Return invalid authentication headers for negative testing"""
    return {"Authorization": "Bearer INVALID_TOKEN_12345"}

@pytest.fixture
def malformed_auth_headers() -> Dict[str, str]:
    """Return malformed authentication headers"""
    return {"Authorization": "InvalidFormat"}

# ============================================================================
# APP & CLIENT FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def app(lattice_session: str):
    """
    FastAPI application instance with test configuration.
    Overrides app state with test session data.
    """
    from backend.main import app
    
    # Inject session into app state
    app.state.session_code = lattice_session
    app.state.test_mode = True
    
    # Set kernel to simulated mode for tests
    if hasattr(app.state, 'kernel'):
        app.state.kernel_status = "TEST_MODE"
    
    return app

@pytest.fixture
def client(app):
    """
    Test client with proper startup/shutdown handling.
    """
    from fastapi.testclient import TestClient
    
    app.dependency_overrides = {}
    
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def async_client(app):
    """
    Async test client for WebSocket and async endpoint testing.
    """
    from httpx import AsyncClient
    
    return AsyncClient(app=app, base_url="http://test")

# ============================================================================
# DATABASE & CACHE FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis client for testing"""
    class MockRedis:
        def __init__(self):
            self.data = {}
        
        async def get(self, key):
            return self.data.get(key)
        
        async def set(self, key, value):
            self.data[key] = value
            return True
        
        async def delete(self, key):
            self.data.pop(key, None)
            return True
        
        async def close(self):
            pass
    
    mock = MockRedis()
    monkeypatch.setattr("redis.asyncio.from_url", lambda *args, **kwargs: mock)
    return mock

# ============================================================================
# NASA & GEE MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_nasa_data() -> Dict[str, Any]:
    """Mock NASA POWER API response"""
    return {
        "thermal_ambient": 28.5,
        "solar_flux_ergotropy": 0.85,
        "humidity_index": 65.0,
        "wind_vibration_hz": 4.5,
        "pressure_mb": 1013.0,
        "sync_status": "ONLINE",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@pytest.fixture
def mock_gee_data() -> Dict[str, Any]:
    """Mock Google Earth Engine data"""
    return {
        "node_id": "ABUJA-ALPHA-CORE",
        "telemetry": {
            "avg_thermal_gradient": 29.5,
            "environmental_stability_index": 0.65,
            "resolution": "10m_Sovereign"
        },
        "coordinates": {"lat": 9.0765, "lon": 7.3986},
        "status": "CALIBRATED"
    }

@pytest.fixture
def mock_environmental_data(mock_nasa_data, mock_gee_data) -> Dict[str, Any]:
    """Combined mock environmental data"""
    return {
        "atmospheric": {
            "temp_2m": mock_nasa_data["thermal_ambient"],
            "humidity_2m": mock_nasa_data["humidity_index"]
        },
        "solar": {
            "allsky_sfc_sw_dwn": mock_nasa_data["solar_flux_ergotropy"]
        },
        "wind": {
            "speed_10m": mock_nasa_data["wind_vibration_hz"]
        },
        "data_sources": {
            "nasa": True,
            "gee": True
        }
    }

# ============================================================================
# SENSOR TELEMETRY FIXTURES
# ============================================================================

@pytest.fixture
def valid_sensor_telemetry() -> Dict[str, Any]:
    """Valid sensor telemetry payload"""
    return {
        "sensor_id": "ABJ-GRID-01",
        "thermal_load": 32.5,
        "vibration_hz": 50.0,
        "ergotropy_flux": 120.5,
        "hardware_hash": "sha3_f7e8c9a1b2_SOVEREIGN",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@pytest.fixture
def anomaly_sensor_telemetry() -> Dict[str, Any]:
    """Anomaly sensor telemetry (high temperature, high vibration)"""
    return {
        "sensor_id": "ABJ-GRID-01",
        "thermal_load": 85.0,
        "vibration_hz": 150.0,
        "ergotropy_flux": 85.2,
        "hardware_hash": "sha3_f7e8c9a1b2_SOVEREIGN",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@pytest.fixture
def invalid_sensor_telemetry() -> Dict[str, Any]:
    """Invalid sensor telemetry (negative values, invalid hash)"""
    return {
        "sensor_id": "INVALID",
        "thermal_load": -10.0,
        "vibration_hz": -5.0,
        "ergotropy_flux": -20.0,
        "hardware_hash": "invalid_hash",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ============================================================================
# SIMULATION FIXTURES
# ============================================================================

@pytest.fixture
def simulation_request() -> Dict[str, Any]:
    """Standard simulation request payload"""
    return {
        "context": "Abuja-Pilot-Alpha",
        "auto_field": True,
        "parameters": {
            "test_mode": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }

@pytest.fixture
def simulation_response() -> Dict[str, Any]:
    """Mock simulation response"""
    return {
        "mode": "TEST_11D",
        "status": "SUCCESS",
        "simulation_id": "TEST-001",
        "physics_intelligence": {
            "structural_stability": 98.5,
            "convergence_validated": True,
            "failure_probability": 0.023,
            "entropy": 0.045
        },
        "yield_metrics": {
            "extractable_ergotropy": 142.5,
            "efficiency_gain": 5.2,
            "confidence_score": 0.96
        },
        "performance_metrics": {
            "processing_time_ms": 45.2,
            "kernel_mode": "TEST"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ============================================================================
# ADFI FIXTURES
# ============================================================================

@pytest.fixture
def adfi_config() -> Dict[str, Any]:
    """ADFI configuration for testing"""
    return {
        "count": 3,
        "sector": "energy_grid",
        "pattern": "normal",
        "interval_seconds": 0.1,
        "inject_to_backend": False
    }

@pytest.fixture
def adfi_packet() -> Dict[str, Any]:
    """Mock ADFI telemetry packet"""
    return {
        "packet_id": "ADFI-TEST-001",
        "sensor_id": "ABJ-GRID-01",
        "thermal_load": 32.5,
        "vibration_hz": 50.0,
        "ergotropy_flux": 120.5,
        "grid_frequency": 50.02,
        "structural_stability": 98.5,
        "hardware_hash": "sha3_test_hash_SOVEREIGN",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.95,
        "quality_score": 0.93,
        "pattern_type": "normal"
    }

# ============================================================================
# REPORTING FIXTURES
# ============================================================================

@pytest.fixture
def report_payload() -> Dict[str, Any]:
    """Report generation payload"""
    return {
        "simulation_data": {
            "simulation_id": "TEST-001",
            "yield_metrics": {"extractable_ergotropy": 142.5},
            "physics_intelligence": {"structural_stability": 98.5}
        },
        "metadata": {
            "report_type": "executive_summary",
            "format": "pdf"
        },
        "stakeholder_id": "CTO_TEST",
        "format": "json"
    }

# ============================================================================
# PERFORMANCE & LOAD TESTING FIXTURES
# ============================================================================

@pytest.fixture
def performance_metrics() -> Dict[str, Any]:
    """Performance metrics tracking"""
    return {
        "requests": [],
        "start_time": time.time(),
        "thresholds": {
            "p95_latency_ms": 500,
            "error_rate": 0.05,
            "throughput_rps": 100
        }
    }

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

@pytest.fixture
def wait_for_async():
    """Helper to wait for async operations"""
    async def _wait(seconds: float = 0.1):
        await asyncio.sleep(seconds)
    return _wait

@pytest.fixture
def capture_logs(caplog):
    """Capture logs for assertion testing"""
    caplog.set_level(logging.INFO)
    return caplog

# ============================================================================
# TEST DATA GENERATOR
# ============================================================================

class TestDataGenerator:
    """Helper class for generating test data"""
    
    @staticmethod
    def generate_sensor_telemetry(sensor_id: str = "ABJ-GRID-01") -> Dict[str, Any]:
        """Generate random sensor telemetry"""
        import random
        return {
            "sensor_id": sensor_id,
            "thermal_load": round(25 + random.random() * 30, 2),
            "vibration_hz": round(45 + random.random() * 30, 2),
            "ergotropy_flux": round(80 + random.random() * 100, 2),
            "hardware_hash": f"sha3_{random.randint(1000, 9999)}_TEST",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @staticmethod
    def generate_batch_telemetry(count: int = 5) -> List[Dict[str, Any]]:
        """Generate batch of sensor telemetry"""
        return [TestDataGenerator.generate_sensor_telemetry(f"ABJ-GRID-{i+1:02d}") 
                for i in range(min(count, 10))]

# ============================================================================
# SESSION & LIFECYCLE MANAGEMENT
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def test_session_setup(lattice_session):
    """Setup test session environment"""
    print("\n" + "="*80)
    print("  🧪 NEUROBRIDGE 11D TEST SUITE v3.0.0-QUANTUM")
    print("  📍 Abuja Pilot Deployment - Test Environment")
    print("="*80)
    print(f"  🔐 Session: {lattice_session[:12]}...")
    print(f"  🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    
    yield
    
    print("\n" + "="*80)
    print("  ✅ Test Suite Complete")
    print(f"  🕐 Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

# ============================================================================
# CLEANUP FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Clean up test data after each test"""
    yield
    # Clean up any test artifacts
    import shutil
    test_exports = BASE_DIR / "exports" / "test_reports"
    if test_exports.exists():
        shutil.rmtree(test_exports, ignore_errors=True)
    
    test_logs = BASE_DIR / "logs" / "test"
    if test_logs.exists():
        shutil.rmtree(test_logs, ignore_errors=True)

# ============================================================================
# ASYNC FIXTURE SUPPORT
# ============================================================================

@pytest.fixture
def event_loop():
    """Create an event loop for async fixtures"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ============================================================================
# EXPORT FOR USE IN TESTS
# ============================================================================

__all__ = [
    # Fixtures
    'lattice_session', 'auth_headers', 'invalid_auth_headers', 'malformed_auth_headers',
    'app', 'client', 'async_client',
    'mock_redis', 'mock_nasa_data', 'mock_gee_data', 'mock_environmental_data',
    'valid_sensor_telemetry', 'anomaly_sensor_telemetry', 'invalid_sensor_telemetry',
    'simulation_request', 'simulation_response',
    'adfi_config', 'adfi_packet',
    'report_payload', 'performance_metrics',
    'wait_for_async', 'capture_logs',
    'test_data_generator',
    # Utilities
    'TestDataGenerator'
]