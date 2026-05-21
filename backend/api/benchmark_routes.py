from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.core.auth import AuthResult, require_api_key
from backend.core.benchmark_reporter import REPORT_DIR, build_benchmark_report
from backend.core.latency_metrics import get_latency_metrics


router = APIRouter(
    prefix="/api/v1/benchmarks",
    tags=["Benchmark Reports"],
)


@router.get("/health")
async def benchmark_health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "benchmark_reports",
        "report_dir": str(REPORT_DIR),
        "timestamp": int(time.time()),
    }


@router.get("/reports")
async def list_benchmark_reports(
    auth: AuthResult = Depends(require_api_key),
) -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    reports = []
    for file in sorted(REPORT_DIR.glob("*.json"), reverse=True):
        reports.append({
            "filename": file.name,
            "path": str(file),
            "size_bytes": file.stat().st_size,
            "modified_at": int(file.stat().st_mtime),
        })

    return {
        "status": "success",
        "authenticated": auth.valid,
        "reports": reports,
        "timestamp": int(time.time()),
    }


@router.get("/reports/{filename}")
async def get_benchmark_report(
    filename: str,
    auth: AuthResult = Depends(require_api_key),
) -> Dict[str, Any]:
    safe_name = Path(filename).name
    file = REPORT_DIR / safe_name

    if not file.exists() or file.suffix != ".json":
        raise HTTPException(status_code=404, detail="Benchmark report not found")

    return {
        "status": "success",
        "authenticated": auth.valid,
        "filename": safe_name,
        "report": json.loads(file.read_text(encoding="utf-8")),
        "timestamp": int(time.time()),
    }


@router.get("/latency")
async def benchmark_latency(
    auth: AuthResult = Depends(require_api_key),
) -> Dict[str, Any]:
    return {
        "status": "success",
        "authenticated": auth.valid,
        "latency": get_latency_metrics().summary(),
        "timestamp": int(time.time()),
    }


@router.post("/external-cognitive")
async def create_external_cognitive_benchmark_report(
    auth: AuthResult = Depends(require_api_key),
) -> Dict[str, Any]:
    latency_summary = get_latency_metrics().summary("/api/v1/external/cognitive/query")
    endpoint_data = latency_summary.get("/api/v1/external/cognitive/query", {})

    latencies = []
    if endpoint_data.get("count", 0) > 0:
        latencies = [
            endpoint_data.get("avg_ms", 0),
            endpoint_data.get("p95_ms", 0),
            endpoint_data.get("p99_ms", 0),
        ]

    result = build_benchmark_report(
        name="external_cognitive_observed_latency",
        latencies_ms=latencies,
        total_requests=endpoint_data.get("count", 0),
        success_count=endpoint_data.get("count", 0),
        failure_count=0,
        metadata={
            "source": "runtime_latency_metrics",
            "endpoint": "/api/v1/external/cognitive/query",
            "latency_summary": endpoint_data,
        },
    )

    return {
        "status": "success",
        "authenticated": auth.valid,
        **result,
        "timestamp": int(time.time()),
    }