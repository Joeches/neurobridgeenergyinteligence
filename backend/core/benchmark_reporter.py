from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Dict, Any, List


REPORT_DIR = Path("benchmarks/reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = int(round((p / 100) * (len(values) - 1)))
    return round(values[index], 3)


def build_benchmark_report(
    name: str,
    latencies_ms: List[float],
    total_requests: int,
    success_count: int,
    failure_count: int,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    report = {
        "name": name,
        "timestamp": int(time.time()),
        "total_requests": total_requests,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate_percent": round((success_count / max(total_requests, 1)) * 100, 2),
        "latency_ms": {
            "min": round(min(latencies_ms), 3) if latencies_ms else 0,
            "max": round(max(latencies_ms), 3) if latencies_ms else 0,
            "avg": round(statistics.mean(latencies_ms), 3) if latencies_ms else 0,
            "p50": percentile(latencies_ms, 50),
            "p95": percentile(latencies_ms, 95),
            "p99": percentile(latencies_ms, 99),
        },
        "metadata": metadata or {},
    }

    filename = REPORT_DIR / f"{name}_{report['timestamp']}.json"
    filename.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return {
        "report": report,
        "file": str(filename),
    }