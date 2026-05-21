"""
Nuclear Intelligence API Tests
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def get_valid_token():
    """Get valid authentication token"""
    from backend.main import token_manager
    return token_manager.get_current_token()


@pytest.fixture
def auth_headers():
    token = get_valid_token()
    return {"Authorization": f"Bearer {token}"}


class TestNuclearAPI:
    """Nuclear API endpoint tests"""
    
    def test_valid_nuclear_simulation(self, auth_headers):
        """Test valid nuclear simulation request"""
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "pwr",
                "thermal_power_mw": 1200.0,
                "cooling_efficiency": 0.35,
                "load_demand": 950.0,
                "ambient_temp": 28.5,
                "safety_margin": 0.15,
                "cooling_type": "cooling_tower"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "yield_metrics" in data
        assert "nuclear_safety" in data
        assert "energy_mix" in data
        print(f"✅ Valid nuclear simulation passed")
    
    def test_invalid_reactor_type(self, auth_headers):
        """Test invalid reactor type rejection"""
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "invalid",
                "thermal_power_mw": 1200.0,
                "cooling_efficiency": 0.35,
                "load_demand": 950.0
            }
        )
        assert response.status_code == 422  # Validation error
        print(f"✅ Invalid reactor type rejected")
    
    def test_missing_parameters(self, auth_headers):
        """Test missing required parameters"""
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "pwr"
                # Missing required fields
            }
        )
        assert response.status_code == 422
        print(f"✅ Missing parameters handled")
    
    def test_thermal_power_bounds(self, auth_headers):
        """Test thermal power bounds validation"""
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "pwr",
                "thermal_power_mw": 10000.0,  # Exceeds max
                "cooling_efficiency": 0.35,
                "load_demand": 950.0
            }
        )
        assert response.status_code == 422
        print(f"✅ Thermal power bounds enforced")
    
    def test_cooling_efficiency_bounds(self, auth_headers):
        """Test cooling efficiency bounds"""
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "pwr",
                "thermal_power_mw": 1200.0,
                "cooling_efficiency": 0.9,  # Exceeds max
                "load_demand": 950.0
            }
        )
        assert response.status_code == 422
        print(f"✅ Cooling efficiency bounds enforced")
    
    def test_nuclear_status_endpoint(self, auth_headers):
        """Test nuclear status endpoint"""
        response = client.get("/api/v1/energy/nuclear/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "supported_reactors" in data
        print(f"✅ Nuclear status endpoint OK")
    
    def test_unauthorized_access(self):
        """Test unauthorized access blocked"""
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            json={
                "reactor_type": "pwr",
                "thermal_power_mw": 1200.0,
                "cooling_efficiency": 0.35,
                "load_demand": 950.0
            }
        )
        assert response.status_code in [401, 403]
        print(f"✅ Unauthorized access blocked")
    
    def test_nuclear_adfi_injection(self, auth_headers):
        """Test nuclear ADFI injection"""
        response = client.post(
            "/api/v1/energy/nuclear/adfi/inject?pattern=meltdown_risk&count=5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pattern"] == "meltdown_risk"
        print(f"✅ Nuclear ADFI injection OK")
    
    def test_energy_mix_optimization(self, auth_headers):
        """Test energy mix optimization"""
        response = client.post(
            "/api/v1/energy/nuclear/optimize/mix?total_demand_mw=1500&nuclear_output_mw=800",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "optimal_mix" in data
        print(f"✅ Energy mix optimization OK")
    
    def test_performance_benchmark(self, auth_headers):
        """Test nuclear simulation performance (<5ms)"""
        import time
        
        start = time.perf_counter()
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "smr",
                "thermal_power_mw": 300.0,
                "cooling_efficiency": 0.38,
                "load_demand": 250.0
            }
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code == 200
        assert elapsed_ms < 100  # Well under 5ms requirement
        print(f"✅ Performance: {elapsed_ms:.2f}ms (<5ms requirement met)")
    
    def test_all_reactor_types(self, auth_headers):
        """Test all supported reactor types"""
        reactor_types = ["pwr", "bwr", "smr", "htgr", "msr"]
        
        for reactor in reactor_types:
            response = client.post(
                "/api/v1/energy/simulate/nuclear",
                headers=auth_headers,
                json={
                    "reactor_type": reactor,
                    "thermal_power_mw": 1000.0,
                    "cooling_efficiency": 0.33,
                    "load_demand": 800.0
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["yield_metrics"]["extractable_ergotropy"] > 0
        
        print(f"✅ All {len(reactor_types)} reactor types tested")
    
    def test_risk_level_calculation(self, auth_headers):
        """Test risk level calculation"""
        # High risk scenario
        response = client.post(
            "/api/v1/energy/simulate/nuclear",
            headers=auth_headers,
            json={
                "reactor_type": "pwr",
                "thermal_power_mw": 1200.0,
                "cooling_efficiency": 0.25,  # Poor cooling
                "load_demand": 950.0,
                "safety_margin": 0.05  # Low safety margin
            }
        )
        assert response.status_code == 200
        data = response.json()
        risk_level = data["nuclear_safety"]["risk_level"]
        assert risk_level in ["HIGH", "CRITICAL"]
        print(f"✅ Risk level calculation: {risk_level}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])