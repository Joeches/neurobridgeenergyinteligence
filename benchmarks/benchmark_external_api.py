import time
import requests
from backend.core.benchmark_reporter import build_benchmark_report


BASE_URL = "http://127.0.0.1:8000"
API_KEY = "PASTE_TEST_API_KEY_HERE"


def run():
    latencies = []
    success = 0
    failure = 0

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "query": "Analyze grid stability and solar risk",
        "metrics": {
            "actual_kw": 8.5,
            "expected_kw": 10,
            "temperature_c": 32,
            "irradiance_quality": 0.91,
            "frequency_hz": 49.8,
            "voltage_v": 228,
            "load_balance": 0.93,
        },
    }

    for _ in range(100):
        start = time.perf_counter()
        try:
            r = requests.post(
                f"{BASE_URL}/api/v1/external/cognitive/query",
                headers=headers,
                json=payload,
                timeout=10,
            )
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

            if r.status_code == 200:
                success += 1
            else:
                failure += 1
        except Exception:
            failure += 1

    result = build_benchmark_report(
        name="external_cognitive_api",
        latencies_ms=latencies,
        total_requests=100,
        success_count=success,
        failure_count=failure,
        metadata={"endpoint": "/api/v1/external/cognitive/query"},
    )

    print(result)


if __name__ == "__main__":
    run()