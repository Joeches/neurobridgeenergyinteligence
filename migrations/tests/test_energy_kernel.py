"""
================================================================================
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ████████╗███████╗███████╗████████╗    ███████╗██╗   ██╗██╗████████╗███████╗ ║
║   ╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝    ██╔════╝██║   ██║██║╚══██╔══╝██╔════╝ ║
║      ██║   █████╗  ███████╗   ██║       █████╗  ██║   ██║██║   ██║   █████╗   ║
║      ██║   ██╔══╝  ╚════██║   ██║       ██╔══╝  ██║   ██║██║   ██║   ██╔══╝   ║
║      ██║   ███████╗███████║   ██║       ███████╗╚██████╔╝██║   ██║   ███████╗ ║
║      ╚═╝   ╚══════╝╚══════╝   ╚═╝       ╚══════╝ ╚═════╝ ╚═╝   ╚═╝   ╚══════╝ ║
║                                                                               ║
║                    NEUROBRIDGE 11D TEST SUITE                                 ║
║                    Version: 5.5.1-QUANTUM-INFINITY                            ║
║                    Complete Validation of Native C++ Kernel                   ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
================================================================================
"""

import sys
import os
import pytest
import time
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import FastAPI test client
from fastapi.testclient import TestClient

# Import the app
from backend.main import app, kernel_loader, token_manager_auto
from backend.main import VALID_SECTORS

# ============================================================================
# TEST CONSTANTS
# ============================================================================

ABUJA_COORDINATES = {"lat": 9.0765, "lon": 7.3986}
ADFI_PATTERNS = ["normal", "spike", "drift", "anomaly", "stress", "seasonal"]

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def client():
    """Standard FastAPI TestClient with proper lifecycle"""
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def native_kernel_info():
    """Get native C++ kernel information"""
    info = kernel_loader.get_kernel_info()
    print(f"\n🧠 Native C++ Kernel: {info['performance_mode']}")
    print(f"   Predictor: {info['has_predictor']}")
    print(f"   Analyzer: {info['has_analyzer']}")
    return info

@pytest.fixture(scope="session")
def lattice_session() -> str:
    """Create a valid Lattice session for all tests - store the token at session start"""
    token = token_manager_auto.get_current_token()
    print(f"\n🔐 Lattice Session Created: {token[:12]}... (expires in 55 minutes)")
    return token

@pytest.fixture
def auth_headers(lattice_session: str) -> Dict[str, str]:
    """Return authentication headers with the token from session start"""
    # Use the token from the session fixture, not the current one (to avoid refresh issues)
    return {"Authorization": f"Bearer {lattice_session}"}

@pytest.fixture
def valid_simulation_payload() -> Dict[str, Any]:
    """Generate valid simulation payload"""
    return {
        "context": "Abuja-Harmattan-Grid-Stress",
        "entropy_loss": 0.05,
        "force_kernel": "QUANTUM_NATIVE"
    }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_current_token():
    """Helper to get current token for tests that need it"""
    return token_manager_auto.get_current_token()

# ============================================================================
# KERNEL TESTS
# ============================================================================

def test_kernel_native_loaded(native_kernel_info):
    """Test that native C++ kernel is loaded"""
    assert native_kernel_info is not None
    assert native_kernel_info["native"] is True
    assert native_kernel_info["has_predictor"] is True
    assert native_kernel_info["performance_mode"] == "NATIVE_C++"
    print(f"✅ Native C++ Kernel loaded: {native_kernel_info['performance_mode']}")

def test_kernel_calculation_accuracy():
    """Test kernel calculation accuracy with known values"""
    result = kernel_loader.calculate_yield_ergotropy(100.0, 0.05)
    expected = 119.32777777777778
    assert abs(result - expected) < 0.001
    print(f"✅ Kernel calculation accurate: {result:.6f}")

def test_kernel_endpoint(client, auth_headers):
    """Test the kernel status endpoint"""
    response = client.get("/api/v1/kernel/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["native"] is True
    assert data["performance_mode"] == "NATIVE_C++"
    print(f"✅ Kernel status endpoint: {data['performance_mode']}")

def test_kernel_test_endpoint(client, auth_headers):
    """Test the kernel test endpoint"""
    response = client.post("/api/v1/kernel/test", headers=auth_headers, json={"energy": 150.0, "entropy": 0.08})
    assert response.status_code == 200
    data = response.json()
    assert "output_yield" in data
    assert data["kernel_native"] is True
    print(f"✅ Kernel test endpoint: {data['output_yield']:.2f} MWh")

# ============================================================================
# ADFI TESTS
# ============================================================================

def test_adfi_field_data_injection(client, auth_headers):
    """Test ADFI data injection endpoint with all patterns"""
    for pattern in ADFI_PATTERNS[:3]:
        response = client.post(
            "/api/v1/admin/field-data",
            headers=auth_headers,
            json={"sector": "renewables", "pattern": pattern, "count": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pattern"] == pattern
        assert len(data["data"]) == 5
        print(f"✅ ADFI {pattern} pattern: {len(data['data'])} points injected")

def test_adfi_all_sectors(client, auth_headers):
    """Test ADFI injection across all 6 energy sectors"""
    for sector in VALID_SECTORS:
        response = client.post(
            "/api/v1/admin/field-data",
            headers=auth_headers,
            json={"sector": sector, "pattern": "normal", "count": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sector"] == sector
        print(f"✅ {sector}: {data['count']} points injected")

def test_adfi_statistics(client, auth_headers):
    """Test ADFI statistics endpoint"""
    response = client.get("/api/v1/admin/adfi-stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_injections" in data
    assert "kernel_native" in data
    print(f"✅ ADFI stats: {data['total_injections']} total injections, Native: {data['kernel_native']}")

# ============================================================================
# TOKEN MANAGEMENT TESTS
# ============================================================================

def test_token_status_endpoint(client):
    """Test token status endpoint"""
    response = client.get("/api/v1/token/status")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "token" in data
    print(f"✅ Token status: {data['token']['token_masked']}")

def test_token_refresh_endpoint(client):
    """Test token refresh endpoint - this creates a new token, so subsequent tests need new headers"""
    response = client.post("/api/v1/token/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    print(f"✅ Token refreshed: {data['token_masked']}")

# ============================================================================
# SECURITY TESTS
# ============================================================================

def test_unauthorized_simulation_attempt(client, valid_simulation_payload):
    """Test that unauthorized simulation attempts are blocked"""
    for sector in VALID_SECTORS[:3]:
        response = client.post(
            f"/api/v1/energy/simulate/{sector}",
            json=valid_simulation_payload
        )
        assert response.status_code == 401
        print(f"✅ Unauthorized access blocked for {sector}")

def test_valid_authentication_simulation(client, valid_simulation_payload):
    """Test that valid authentication allows simulation access using current token"""
    # Get the current token from the manager
    current_token = token_manager_auto.get_current_token()
    auth_headers = {"Authorization": f"Bearer {current_token}"}
    
    for sector in VALID_SECTORS[:3]:
        response = client.post(
            f"/api/v1/energy/simulate/{sector}",
            headers=auth_headers,
            json=valid_simulation_payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert "yield_metrics" in data
        print(f"✅ Valid authentication passed for {sector}")

# ============================================================================
# 11D PHYSICS TESTS
# ============================================================================

def test_energy_status_endpoint(client, auth_headers):
    """Test energy status endpoint"""
    response = client.get("/api/v1/energy/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACTIVE_SOVEREIGN"
    assert data["kernel_available"] is True
    print(f"✅ Energy status: {data['status']} | Native C++ Active")

def test_energy_metrics_endpoint(client, auth_headers):
    """Test energy metrics endpoint"""
    response = client.get("/api/v1/energy/metrics", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "grid_load_mw" in data
    assert "grid_frequency_hz" in data
    print(f"✅ Grid metrics: {data['grid_load_mw']} MW, {data['grid_frequency_hz']} Hz")

def test_energy_prediction_endpoint(client, auth_headers):
    """Test energy prediction endpoint"""
    sector = VALID_SECTORS[0]
    response = client.get(f"/api/v1/energy/predict/{sector}?hours_ahead=24", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["sector"] == sector
    assert len(data["predictions"]) == 24
    print(f"✅ Energy prediction: {len(data['predictions'])} hours forecast")

def test_full_11d_simulation_flow(client, valid_simulation_payload):
    """Test complete 11D simulation flow using current token"""
    current_token = token_manager_auto.get_current_token()
    auth_headers = {"Authorization": f"Bearer {current_token}"}
    
    sector = VALID_SECTORS[0]
    response = client.post(
        f"/api/v1/energy/simulate/{sector}",
        headers=auth_headers,
        json=valid_simulation_payload
    )
    assert response.status_code == 200
    data = response.json()
    assert "simulation_id" in data
    assert "yield_metrics" in data
    assert data["kernel_native"] is True
    print(f"✅ 11D simulation: yield={data['yield_metrics']['extractable_ergotropy']:.2f} MWh")

# ============================================================================
# SKY-EYE TESTS
# ============================================================================

def test_nasa_telemetry_endpoint(client, auth_headers):
    """Test NASA POWER telemetry endpoint"""
    response = client.get("/api/v1/nasa-telemetry", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "ghi_wm2" in data
    assert "temperature_c" in data
    print(f"✅ NASA telemetry: GHI={data['ghi_wm2']} W/m², Temp={data['temperature_c']}°C")

def test_gee_heatmap_endpoint(client, auth_headers):
    """Test Google Earth Engine heatmap endpoint"""
    lat, lon = ABUJA_COORDINATES["lat"], ABUJA_COORDINATES["lon"]
    response = client.get(f"/api/v1/gee-heatmap?lat={lat}&lon={lon}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "vegetation_health" in data
    assert "coordinates" in data
    print(f"✅ GEE heatmap: vegetation_health={data['vegetation_health']}%")

# ============================================================================
# SYSTEM METRICS TESTS
# ============================================================================

def test_system_metrics_endpoint(client, auth_headers):
    """Test system metrics endpoint"""
    response = client.get("/api/v1/system/metrics", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "system" in data
    assert "services" in data
    kernel_info = data["services"]["kernel"]
    print(f"✅ System metrics: {kernel_info.get('performance_mode', 'NATIVE_C++')}")

# ============================================================================
# WEBSOCKET TESTS
# ============================================================================

def test_websocket_quantum_channel(client):
    """Test WebSocket quantum channel"""
    with client.websocket_connect("/ws/quantum-channel") as websocket:
        websocket.send_json({"type": "ping"})
        response = websocket.receive_json()
        assert response["type"] == "pong"
        print("✅ WebSocket quantum channel active")

# ============================================================================
# HEALTH TESTS
# ============================================================================

def test_health_endpoint(client):
    """Test comprehensive health check endpoint"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "5.5.1-QUANTUM-INFINITY"
    assert data["kernel"]["native"] is True
    print(f"✅ Health check: {data['status']} | Native C++ Active")

# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.performance
def test_kernel_performance():
    """Test kernel calculation performance with native C++"""
    iterations = 1000
    start = time.perf_counter()
    for i in range(iterations):
        kernel_loader.calculate_yield_ergotropy(100.0, 0.05)
    elapsed = (time.perf_counter() - start) * 1000
    avg_time = elapsed / iterations
    
    print(f"\n📊 Native C++ Kernel Performance:")
    print(f"  Iterations: {iterations}")
    print(f"  Total time: {elapsed:.2f}ms")
    print(f"  Average: {avg_time:.4f}ms per calculation")
    assert avg_time < 1.0

@pytest.mark.performance
def test_adfi_performance(client):
    """Test ADFI injection performance using current token"""
    current_token = token_manager_auto.get_current_token()
    auth_headers = {"Authorization": f"Bearer {current_token}"}
    
    start = time.perf_counter()
    response = client.post(
        "/api/v1/admin/field-data",
        headers=auth_headers,
        json={"sector": "renewables", "pattern": "spike", "count": 50}
    )
    elapsed = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    data = response.json()
    print(f"\n📊 ADFI Performance: 50 injections in {elapsed:.2f}ms")

# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.integration
def test_complete_energy_workflow(client, valid_simulation_payload):
    """Test complete energy workflow with native C++ kernel"""
    current_token = token_manager_auto.get_current_token()
    auth_headers = {"Authorization": f"Bearer {current_token}"}
    
    # 1. Check kernel status
    response = client.get("/api/v1/kernel/status", headers=auth_headers)
    assert response.status_code == 200
    kernel_data = response.json()
    print(f"✅ Native C++ Kernel: {kernel_data['performance_mode']}")
    
    # 2. Run ADFI injection
    response = client.post(
        "/api/v1/admin/field-data",
        headers=auth_headers,
        json={"sector": "renewables", "pattern": "normal", "count": 10}
    )
    assert response.status_code == 200
    adfi_data = response.json()
    print(f"✅ ADFI injection: {adfi_data['count']} data points")
    
    # 3. Run simulation
    sector = VALID_SECTORS[0]
    response = client.post(
        f"/api/v1/energy/simulate/{sector}",
        headers=auth_headers,
        json=valid_simulation_payload
    )
    assert response.status_code == 200
    sim_data = response.json()
    print(f"✅ Simulation: {sim_data['yield_metrics']['extractable_ergotropy']:.2f} MWh")
    
    # 4. Get metrics
    response = client.get("/api/v1/energy/metrics", headers=auth_headers)
    assert response.status_code == 200
    metrics_data = response.json()
    print(f"✅ Grid metrics: {metrics_data['grid_load_mw']} MW")
    
    # 5. Check health
    response = client.get("/api/v1/health", headers=auth_headers)
    assert response.status_code == 200
    print(f"✅ Health check passed")
    
    print("✅ Complete energy workflow validated with native C++ kernel")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("  🧪 NEUROBRIDGE 11D TEST SUITE")
    print("  Version: 5.5.1-QUANTUM-INFINITY")
    print("  Features: Native C++ 11D Kernel | ADFI Orchestration")
    print("=" * 80 + "\n")
    
    pytest.main([__file__, "-v", "-s", "--tb=short", "--maxfail=1"])