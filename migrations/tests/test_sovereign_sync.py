"""
================================================================================
Project: NeuroBridge 11D Energy Intelligence Kernel
Component: Sovereign Integration Test Suite (V3.0.0-QUANTUM)
Description: Comprehensive integration testing for all system components
             including API endpoints, security, physics engine, data fusion,
             and real-time telemetry. Validates the complete system workflow
             for the Abuja Pilot Deployment.
Author: Lead Integration Architect
License: Sovereign Proprietary - Abuja Pilot Deployment
================================================================================
"""

import requests
import time
import os
import sys
import json
import asyncio
import websockets
import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
import concurrent.futures
import statistics

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api/v1"
WEBSOCKET_URL = f"ws://127.0.0.1:8000/api/v1/ws/telemetry"

# Test timeout configurations
CONNECTION_TIMEOUT = 10
RESPONSE_TIMEOUT = 30
WEBSOCKET_TIMEOUT = 5

# Performance thresholds
PERFORMANCE_THRESHOLDS = {
    "status_p95_ms": 100,
    "simulation_p95_ms": 500,
    "ingestion_p95_ms": 200,
    "success_rate": 0.95
}

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class TestResult:
    """Test result data structure"""
    name: str
    status: bool
    message: str
    duration_ms: float
    timestamp: str
    details: Dict[str, Any] = None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": "PASS" if self.status else "FAIL",
            "message": self.message,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "details": self.details or {}
        }

@dataclass
class TestSuiteResult:
    """Test suite result data structure"""
    suite_name: str
    start_time: str
    end_time: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    results: List[TestResult]
    summary: Dict[str, Any]

# ============================================================================
# TEST DATA GENERATORS
# ============================================================================

class TestDataGenerator:
    """Generate realistic test data for integration testing"""
    
    @staticmethod
    def get_valid_telemetry(sensor_id: str = "ABJ-GRID-01") -> Dict:
        """Generate valid sensor telemetry"""
        return {
            "sensor_id": sensor_id,
            "thermal_load": 32.5,
            "vibration_hz": 50.0,
            "ergotropy_flux": 120.5,
            "hardware_hash": "sha3_f7e8c9a1b2_SOVEREIGN",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @staticmethod
    def get_anomaly_telemetry(severity: str = "high") -> Dict:
        """Generate anomalous telemetry for testing"""
        base = TestDataGenerator.get_valid_telemetry()
        if severity == "high":
            base["thermal_load"] = 85.0
            base["vibration_hz"] = 150.0
            base["ergotropy_flux"] = 85.2
        elif severity == "medium":
            base["thermal_load"] = 55.0
            base["vibration_hz"] = 90.0
            base["ergotropy_flux"] = 100.0
        else:
            base["thermal_load"] = 42.0
            base["vibration_hz"] = 70.0
            base["ergotropy_flux"] = 110.0
        return base
    
    @staticmethod
    def get_simulation_request(context: str = "Abuja-Pilot-Alpha") -> Dict:
        """Generate simulation request"""
        return {
            "context": context,
            "auto_field": True,
            "parameters": {
                "test_mode": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

# ============================================================================
# SOVEREIGN TESTER CLASS
# ============================================================================

class SovereignTester:
    """
    Enterprise-grade integration testing suite for NeuroBridge 11D system.
    Validates all components including API endpoints, security, physics engine,
    data fusion, and real-time telemetry.
    """
    
    def __init__(self, verbose: bool = True):
        """Initialize the Sovereign Test Suite"""
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.session_token = None
        self.start_time = None
        self.end_time = None
        
        # Load environment variables
        load_dotenv()
        self.cto_code = os.getenv("CTO_ACCESS_CODE")
        
        # Performance metrics storage
        self.performance_metrics = {
            "endpoints": {},
            "latencies": [],
            "timestamps": []
        }
        
        # Colors for output
        self.colors = {
            "green": "\033[92m",
            "red": "\033[91m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "reset": "\033[0m",
            "bold": "\033[1m"
        }
        
        self._log_header()
    
    def _log(self, message: str, color: str = "reset", end: str = "\n"):
        """Log with color formatting"""
        if self.verbose:
            print(f"{self.colors.get(color, '')}{message}{self.colors['reset']}", end=end)
    
    def _log_header(self):
        """Display test suite header"""
        print("\n" + "═"*80)
        print(f" {self.colors['bold']}🧠 NEUROBRIDGE 11D: SOVEREIGN INTEGRATION TEST SUITE{self.colors['reset']}")
        print(f" {self.colors['blue']}📡 Version: 3.0.0-QUANTUM{self.colors['reset']}")
        print(f" {self.colors['blue']}⏱️  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{self.colors['reset']}")
        print(f" {self.colors['blue']}📍 Deployment: Abuja Pilot Zone{self.colors['reset']}")
        print("═"*80 + "\n")
    
    def _log_result(self, test_name: str, passed: bool, message: str, duration_ms: float = 0):
        """Log individual test result"""
        symbol = "✅" if passed else "❌"
        color = "green" if passed else "red"
        status = "PASSED" if passed else "FAILED"
        
        duration_str = f" [{duration_ms:.0f}ms]" if duration_ms > 0 else ""
        self._log(f"{symbol} {test_name.ljust(35)} | {status}{duration_str}", color)
        if not passed and message:
            self._log(f"   └─ {message}", "yellow")
    
    def _record_result(self, test_name: str, passed: bool, message: str = "", 
                       duration_ms: float = 0, details: Dict = None):
        """Record test result"""
        result = TestResult(
            name=test_name,
            status=passed,
            message=message,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details
        )
        self.results.append(result)
        self._log_result(test_name, passed, message, duration_ms)
        return result
    
    def _measure_performance(self, endpoint: str, duration_ms: float):
        """Track performance metrics"""
        if endpoint not in self.performance_metrics["endpoints"]:
            self.performance_metrics["endpoints"][endpoint] = []
        self.performance_metrics["endpoints"][endpoint].append(duration_ms)
        self.performance_metrics["latencies"].append(duration_ms)
    
    def _get_performance_stats(self, endpoint: str = None) -> Dict:
        """Calculate performance statistics"""
        if endpoint and endpoint in self.performance_metrics["endpoints"]:
            data = self.performance_metrics["endpoints"][endpoint]
        else:
            data = self.performance_metrics["latencies"]
        
        if not data:
            return {"min": 0, "max": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0}
        
        sorted_data = sorted(data)
        return {
            "min": round(min(data), 2),
            "max": round(max(data), 2),
            "mean": round(statistics.mean(data), 2),
            "p50": round(sorted_data[int(len(sorted_data) * 0.50)], 2),
            "p95": round(sorted_data[int(len(sorted_data) * 0.95)], 2),
            "p99": round(sorted_data[int(len(sorted_data) * 0.99)], 2),
            "count": len(data)
        }
    
    def _check_system_connectivity(self) -> bool:
        """Check if the system is reachable"""
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=CONNECTION_TIMEOUT)
            return response.status_code == 200
        except:
            return False
    
    # ============================================================================
    # TEST METHODS
    # ============================================================================
    
    def test_health_check(self) -> bool:
        """Test system health endpoint"""
        test_name = "HEALTH_CHECK"
        start_time = time.perf_counter()
        
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=CONNECTION_TIMEOUT)
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("health", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                self._record_result(test_name, True, f"Status: {data.get('status')}", duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_api_status(self) -> bool:
        """Test API status endpoint"""
        test_name = "API_STATUS"
        start_time = time.perf_counter()
        
        try:
            response = requests.get(f"{API_BASE}/status", timeout=CONNECTION_TIMEOUT)
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("api_status", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                self._record_result(test_name, True, 
                                   f"Kernel: {data.get('kernel', 'N/A')}, Status: {data.get('status')}", 
                                   duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_quantum_health(self) -> bool:
        """Test quantum health endpoint"""
        test_name = "QUANTUM_HEALTH"
        start_time = time.perf_counter()
        
        try:
            response = requests.get(f"{API_BASE}/quantum/health", timeout=CONNECTION_TIMEOUT)
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("quantum_health", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                quantum_state = data.get("quantum_state", {})
                self._record_result(test_name, True, 
                                   f"Coherent: {quantum_state.get('kernel_active', False)}", 
                                   duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_energy_status(self) -> bool:
        """Test energy kernel status endpoint"""
        test_name = "ENERGY_STATUS"
        start_time = time.perf_counter()
        
        try:
            response = requests.get(f"{API_BASE}/energy/status", timeout=CONNECTION_TIMEOUT)
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("energy_status", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                self._record_result(test_name, True, 
                                   f"Status: {data.get('status', 'N/A')}, Kernel: {data.get('kernel_available', False)}", 
                                   duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_security_wall(self) -> bool:
        """Test security authentication wall"""
        test_name = "SECURITY_WALL"
        start_time = time.perf_counter()
        
        try:
            payload = TestDataGenerator.get_simulation_request()
            response = requests.post(
                f"{API_BASE}/energy/simulate/renewables",
                json=payload,
                timeout=CONNECTION_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Should return 401/403 without authentication
            passed = response.status_code in [401, 403]
            self._record_result(test_name, passed, 
                               f"Response: {response.status_code} (Expected 401/403)", 
                               duration_ms)
            return passed
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_lattice_authentication(self) -> bool:
        """Test lattice authentication with valid token"""
        test_name = "LATTICE_AUTH"
        start_time = time.perf_counter()
        
        if not self.cto_code:
            self._record_result(test_name, False, "No CTO code found in .env", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.cto_code}"}
            payload = TestDataGenerator.get_simulation_request()
            response = requests.post(
                f"{API_BASE}/energy/simulate/renewables",
                json=payload,
                headers=headers,
                timeout=CONNECTION_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            passed = response.status_code == 200
            self._record_result(test_name, passed, 
                               f"Token: {self.cto_code[:12]}... | Response: {response.status_code}", 
                               duration_ms)
            self.session_token = self.cto_code if passed else None
            return passed
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_simulation_endpoint(self) -> bool:
        """Test energy simulation endpoint"""
        test_name = "SIMULATION"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            payload = TestDataGenerator.get_simulation_request()
            
            response = requests.post(
                f"{API_BASE}/energy/simulate/renewables",
                json=payload,
                headers=headers,
                timeout=RESPONSE_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("simulation", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                yield_val = data.get("yield_metrics", {}).get("extractable_ergotropy", 0)
                stability = data.get("physics_intelligence", {}).get("structural_stability", 0)
                
                self._record_result(test_name, True, 
                                   f"Yield: {yield_val} MWh, Stability: {stability}%", 
                                   duration_ms,
                                   details={"yield": yield_val, "stability": stability})
                return True
            else:
                error = response.json().get("detail", "Unknown error")
                self._record_result(test_name, False, f"HTTP {response.status_code}: {error}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_sensor_ingestion(self) -> bool:
        """Test sensor data ingestion"""
        test_name = "SENSOR_INGESTION"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            telemetry = TestDataGenerator.get_valid_telemetry()
            
            response = requests.post(
                f"{API_BASE}/sensors/ingest",
                json=telemetry,
                headers=headers,
                timeout=RESPONSE_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("sensor_ingestion", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                vector = data.get("calibrated_11d_vector", [])
                self._record_result(test_name, True, 
                                   f"11D Vector Length: {len(vector)}", 
                                   duration_ms)
                return True
            else:
                error = response.json().get("detail", "Unknown error")
                self._record_result(test_name, False, f"HTTP {response.status_code}: {error}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_anomaly_detection(self) -> bool:
        """Test anomaly detection capability"""
        test_name = "ANOMALY_DETECTION"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            telemetry = TestDataGenerator.get_anomaly_telemetry("high")
            
            response = requests.post(
                f"{API_BASE}/sensors/ingest",
                json=telemetry,
                headers=headers,
                timeout=RESPONSE_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                is_anomaly = data.get("anomaly_alert", False)
                status = data.get("status", "")
                
                passed = is_anomaly or "ANOMALY" in status
                self._record_result(test_name, passed, 
                                   f"Anomaly: {is_anomaly}, Status: {status}", 
                                   duration_ms)
                return passed
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_grid_metrics(self) -> bool:
        """Test grid metrics endpoint"""
        test_name = "GRID_METRICS"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.get(
                f"{API_BASE}/energy/metrics",
                headers=headers,
                timeout=CONNECTION_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._measure_performance("grid_metrics", duration_ms)
            
            if response.status_code == 200:
                data = response.json()
                self._record_result(test_name, True, 
                                   f"Load: {data.get('grid_load_mw', 0)} MW, Frequency: {data.get('grid_frequency_hz', 0)} Hz", 
                                   duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_sensor_health(self) -> bool:
        """Test sensor health endpoint"""
        test_name = "SENSOR_HEALTH"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.get(
                f"{API_BASE}/sensors/health/ABJ-GRID-01",
                headers=headers,
                timeout=CONNECTION_TIMEOUT
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                self._record_result(test_name, True, 
                                   f"Status: {data.get('status', 'N/A')}, Quality: {data.get('signal_quality', 0)}", 
                                   duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"HTTP {response.status_code}", duration_ms)
                return False
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    def test_websocket_connection(self) -> bool:
        """Test WebSocket connection for real-time telemetry"""
        test_name = "WEBSOCKET"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        async def test_ws():
            try:
                ws_url = f"{WEBSOCKET_URL}?token={self.session_token}"
                async with websockets.connect(ws_url, timeout=WEBSOCKET_TIMEOUT) as websocket:
                    message = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                    return True, json.loads(message)
            except Exception as e:
                return False, str(e)
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, result = loop.run_until_complete(test_ws())
            loop.close()
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            if success:
                self._record_result(test_name, True, 
                                   f"Message received: {list(result.keys()) if isinstance(result, dict) else 'OK'}", 
                                   duration_ms)
                return True
            else:
                self._record_result(test_name, False, f"Connection failed: {result}", duration_ms)
                return False
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_result(test_name, False, str(e), duration_ms)
            return False
    
    def test_performance_benchmark(self) -> bool:
        """Run performance benchmark on critical endpoints"""
        test_name = "PERFORMANCE_BENCHMARK"
        start_time = time.perf_counter()
        
        if not self.session_token:
            self._record_result(test_name, False, "No valid session token", 0)
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            endpoints = [
                f"{API_BASE}/energy/status",
                f"{API_BASE}/energy/metrics",
                f"{API_BASE}/sensors/health/ABJ-GRID-01"
            ]
            
            latencies = []
            for endpoint in endpoints:
                req_start = time.perf_counter()
                response = requests.get(endpoint, headers=headers, timeout=CONNECTION_TIMEOUT)
                latency = (time.perf_counter() - req_start) * 1000
                latencies.append(latency)
                self._measure_performance(endpoint.split('/')[-1], latency)
            
            avg_latency = sum(latencies) / len(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
            
            passed = p95_latency < PERFORMANCE_THRESHOLDS["status_p95_ms"]
            self._record_result(test_name, passed, 
                               f"Avg: {avg_latency:.0f}ms, P95: {p95_latency:.0f}ms", 
                               (time.perf_counter() - start_time) * 1000)
            return passed
        except Exception as e:
            self._record_result(test_name, False, str(e), (time.perf_counter() - start_time) * 1000)
            return False
    
    # ============================================================================
    # MAIN EXECUTION
    # ============================================================================
    
    def run_suite(self) -> TestSuiteResult:
        """Run the complete test suite"""
        self.start_time = datetime.now()
        
        # Define test order with dependencies
        tests = [
            ("Connectivity Check", self.test_health_check, False),
            ("API Status", self.test_api_status, False),
            ("Quantum Health", self.test_quantum_health, False),
            ("Energy Status", self.test_energy_status, False),
            ("Security Wall", self.test_security_wall, False),
            ("Lattice Authentication", self.test_lattice_authentication, True),
            ("Simulation Endpoint", self.test_simulation_endpoint, True),
            ("Sensor Ingestion", self.test_sensor_ingestion, True),
            ("Anomaly Detection", self.test_anomaly_detection, True),
            ("Grid Metrics", self.test_grid_metrics, True),
            ("Sensor Health", self.test_sensor_health, True),
            ("WebSocket Connection", self.test_websocket_connection, True),
            ("Performance Benchmark", self.test_performance_benchmark, True)
        ]
        
        for test_name, test_func, requires_auth in tests:
            if requires_auth and not self.session_token:
                self._record_result(test_name, False, "Skipped - Authentication required", 0)
                continue
            test_func()
        
        self.end_time = datetime.now()
        return self._generate_report()
    
    def _generate_report(self) -> TestSuiteResult:
        """Generate comprehensive test report"""
        passed = sum(1 for r in self.results if r.status)
        failed = sum(1 for r in self.results if not r.status)
        
        summary = {
            "total_duration_ms": (self.end_time - self.start_time).total_seconds() * 1000,
            "success_rate": (passed / len(self.results) * 100) if self.results else 0,
            "performance_stats": {
                "endpoints": self._get_performance_stats(),
                "by_endpoint": {ep: self._get_performance_stats(ep) 
                                for ep in self.performance_metrics["endpoints"]}
            }
        }
        
        return TestSuiteResult(
            suite_name="Sovereign Integration Test Suite",
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat(),
            total_tests=len(self.results),
            passed=passed,
            failed=failed,
            skipped=0,
            results=self.results,
            summary=summary
        )
    
    def print_summary(self, result: TestSuiteResult):
        """Print test summary with detailed results"""
        print("\n" + "═"*80)
        print(f" {self.colors['bold']}🏁 TEST SUMMARY{self.colors['reset']}")
        print("═"*80)
        print(f" 📊 Total Tests: {result.total_tests}")
        print(f" {self.colors['green']}✅ Passed: {result.passed}{self.colors['reset']}")
        print(f" {self.colors['red']}❌ Failed: {result.failed}{self.colors['reset']}")
        print(f" 📈 Success Rate: {result.summary['success_rate']:.1f}%")
        print(f" ⏱️  Total Duration: {result.summary['total_duration_ms']:.0f}ms")
        
        # Performance Summary
        perf = result.summary['performance_stats']
        print(f"\n {self.colors['bold']}⚡ PERFORMANCE METRICS{self.colors['reset']}")
        print(f"   P50: {perf['p50']:.0f}ms | P95: {perf['p95']:.0f}ms | P99: {perf['p99']:.0f}ms")
        
        # Failed tests details
        if result.failed > 0:
            print(f"\n {self.colors['yellow']}⚠️ FAILED TESTS{self.colors['reset']}")
            for r in self.results:
                if not r.status:
                    print(f"   ❌ {r.name}: {r.message}")
        
        print("\n" + "═"*80 + "\n")
    
    def save_report(self, result: TestSuiteResult, filename: str = "test_report.json"):
        """Save test report to file"""
        report = {
            "suite": result.suite_name,
            "start_time": result.start_time,
            "end_time": result.end_time,
            "summary": result.summary,
            "results": [r.to_dict() for r in result.results]
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        self._log(f"\n📄 Report saved to: {filename}", "blue")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="NeuroBridge 11D Sovereign Integration Tests")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (minimal output)")
    parser.add_argument("--report", "-r", default="test_report.json", help="Report filename")
    args = parser.parse_args()
    
    # Run tests
    tester = SovereignTester(verbose=not args.quiet)
    result = tester.run_suite()
    tester.print_summary(result)
    
    # Save report
    if args.report:
        tester.save_report(result, args.report)
    
    # Exit with appropriate code
    sys.exit(0 if result.failed == 0 else 1)