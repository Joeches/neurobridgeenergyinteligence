#!/usr/bin/env python3
"""
NeuroBridge 11D - Prometheus Metrics Verification Script
Phase 1 Production Validation

Validates that ALL required Prometheus metrics are exposed at GET /metrics.
Used for CI/CD gates, pre-deployment checks, and production health verification.

Usage:
    python scripts/verify_prometheus_metrics.py [--url URL] [--verbose] [--json]

Exit Codes:
    0 - All metrics found (PASS)
    1 - One or more metrics missing (FAIL)
    2 - Connection error (ERROR)
    3 - Timeout (TIMEOUT)
"""

import sys
import json
import time
import argparse
from typing import Dict, List, Tuple, Set
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from socket import timeout as SocketTimeout

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_METRICS_URL = "http://127.0.0.1:8000/metrics"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# ============================================================================
# REQUIRED METRICS - Phase 1 Production
# ============================================================================

REQUIRED_METRICS = {
    # ========================================================================
    # ADFI Observability
    # ========================================================================
    "adfi": [
        "neurobridge_adfi_ingestion_rate_total",
        "neurobridge_adfi_pipeline_latency_seconds",
        "neurobridge_adfi_deterministic_cycles_total",
        "neurobridge_adfi_source_health",
        "neurobridge_adfi_telemetry_packets_total",
    ],
    # ========================================================================
    # AECE Autonomous Control
    # ========================================================================
    "aece": [
        "neurobridge_aece_risk_score",
        "neurobridge_aece_control_actions_total",
        "neurobridge_aece_emergency_stop_state",
        "neurobridge_grid_stability_index",
        "neurobridge_solar_efficiency_score",
    ],
    # ========================================================================
    # External API Metrics
    # ========================================================================
    "external_api": [
        "neurobridge_api_requests_total",
        "neurobridge_api_latency_seconds",
        "neurobridge_investor_clients_active",
        "neurobridge_auth_failures_total",
        "neurobridge_onboarding_events_total",
    ],
    # ========================================================================
    # NeuroBridge 11D Overview
    # ========================================================================
    "overview": [
        "neurobridge_active_modules",
        "neurobridge_celery_queue_depth",
        "neurobridge_redis_health",
        "neurobridge_hardware_bridge_status",
        "neurobridge_prediction_accuracy",
        "neurobridge_phase1_compliance_status",
    ],
    # ========================================================================
    # Additional Phase 1 Production Metrics (optional but validated)
    # ========================================================================
    "production": [
        "neurobridge_api_request_duration_seconds",
        "neurobridge_celery_tasks_total",
        "neurobridge_celery_task_duration_seconds",
        "neurobridge_celery_queue_size",
        "neurobridge_celery_active_workers",
        "neurobridge_aece_actions_total",
        "neurobridge_aece_decision_latency_ms",
        "neurobridge_grid_risk_events_total",
        "neurobridge_energy_power_kw",
        "neurobridge_energy_frequency_hz",
        "neurobridge_system_cpu_percent",
        "neurobridge_system_memory_percent",
        "neurobridge_app_uptime_seconds",
        "neurobridge_redis_available",
        "neurobridge_api_requests_active",
        "neurobridge_websocket_connections",
    ],
}

# ============================================================================
# ANSI COLOR CODES
# ============================================================================

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def green(text): return f"{Colors.GREEN}{text}{Colors.RESET}"
def red(text): return f"{Colors.RED}{text}{Colors.RESET}"
def yellow(text): return f"{Colors.YELLOW}{text}{Colors.RESET}"
def cyan(text): return f"{Colors.CYAN}{text}{Colors.RESET}"
def bold(text): return f"{Colors.BOLD}{text}{Colors.RESET}"

# ============================================================================
# METRICS FETCHING
# ============================================================================

def fetch_metrics(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Tuple[bool, str, str]:
    """
    Fetch metrics from the Prometheus endpoint with retries.
    
    Returns:
        Tuple of (success: bool, raw_text: str, error_message: str)
    """
    last_error = ""
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = Request(url)
            request.add_header('Accept', 'text/plain')
            request.add_header('User-Agent', 'NeuroBridge-Metrics-Verifier/1.0')
            
            response = urlopen(request, timeout=timeout)
            raw_text = response.read().decode('utf-8')
            
            if not raw_text.strip():
                return False, "", f"Empty response from {url}"
            
            return True, raw_text, ""
            
        except HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
        except URLError as e:
            last_error = f"Connection error: {e.reason}"
        except SocketTimeout:
            last_error = f"Timeout after {timeout}s"
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
        
        if attempt < MAX_RETRIES:
            print(yellow(f"  Retry {attempt}/{MAX_RETRIES} in {RETRY_DELAY_SECONDS}s..."))
            time.sleep(RETRY_DELAY_SECONDS)
    
    return False, "", last_error


def parse_metric_names(raw_text: str) -> Set[str]:
    """
    Parse raw Prometheus metrics output and extract metric names.
    Handles TYPE, HELP, and actual metric lines.
    """
    metric_names = set()
    
    for line in raw_text.splitlines():
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue
        
        # Extract metric name (before first { or space)
        if '{' in line:
            metric_name = line.split('{', 1)[0]
        else:
            parts = line.split()
            if len(parts) >= 1:
                metric_name = parts[0]
            else:
                continue
        
        if metric_name and not metric_name.startswith('#'):
            metric_names.add(metric_name)
    
    return metric_names


# ============================================================================
# VERIFICATION
# ============================================================================

def verify_metrics(available_metrics: Set[str]) -> Dict[str, Dict]:
    """
    Verify all required metrics against available metrics.
    
    Returns:
        Dict with category results:
        {
            "category_name": {
                "total": int,
                "found": int,
                "missing": [str],
                "found_list": [str],
                "passed": bool
            }
        }
    """
    results = {}
    
    for category, required_list in REQUIRED_METRICS.items():
        found_list = []
        missing_list = []
        
        for metric_name in required_list:
            if metric_name in available_metrics:
                found_list.append(metric_name)
            else:
                missing_list.append(metric_name)
        
        results[category] = {
            "total": len(required_list),
            "found": len(found_list),
            "missing": missing_list,
            "found_list": found_list,
            "passed": len(missing_list) == 0
        }
    
    return results


def print_results(results: Dict[str, Dict], verbose: bool = False):
    """Print formatted verification results."""
    total_required = sum(r["total"] for r in results.values())
    total_found = sum(r["found"] for r in results.values())
    total_missing = total_required - total_found
    all_passed = all(r["passed"] for r in results.values())
    
    # Header
    print()
    print(bold("=" * 72))
    print(bold("  NeuroBridge 11D - Prometheus Metrics Verification"))
    print(bold("  Phase 1 Production"))
    print(bold("=" * 72))
    print()
    
    # Category results
    category_names = {
        "adfi": "ADFI Observability",
        "aece": "AECE Autonomous Control",
        "external_api": "External API Metrics",
        "overview": "NeuroBridge 11D Overview",
        "production": "Production System Metrics",
    }
    
    for category, result in results.items():
        cat_name = category_names.get(category, category.replace('_', ' ').title())
        status = green("✓ PASS") if result["passed"] else red("✗ FAIL")
        ratio = f"{result['found']}/{result['total']}"
        
        print(f"  {status}  {bold(cat_name):<40} [{ratio}]")
        
        if verbose and result["missing"]:
            for metric in result["missing"]:
                print(f"         {red('✗')} {red(metric)}")
        
        if verbose and result["found_list"]:
            for metric in result["found_list"]:
                print(f"         {green('✓')} {green(metric)}")
        
        print()
    
    # Summary
    print(bold("-" * 72))
    print(f"  Total Required: {total_required}")
    print(f"  Total Found:    {green(str(total_found))}")
    print(f"  Total Missing:  {red(str(total_missing)) if total_missing > 0 else green('0')}")
    
    if all_passed:
        print()
        print(green(bold("  ✅ ALL METRICS VERIFIED - PHASE 1 PRODUCTION COMPLIANT")))
    else:
        print()
        print(red(bold("  ❌ VERIFICATION FAILED - MISSING REQUIRED METRICS")))
    
    print(bold("=" * 72))
    print()
    
    return all_passed


def output_json(results: Dict[str, Dict], metrics_url: str):
    """Output results as JSON for CI/CD integration."""
    total_required = sum(r["total"] for r in results.values())
    total_found = sum(r["found"] for r in results.values())
    all_passed = all(r["passed"] for r in results.values())
    
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics_url": metrics_url,
        "phase": "PHASE_1_PRODUCTION",
        "verdict": "PASS" if all_passed else "FAIL",
        "summary": {
            "total_required": total_required,
            "total_found": total_found,
            "total_missing": total_required - total_found,
            "all_passed": all_passed,
        },
        "categories": results,
        "missing_metrics": [],
    }
    
    for category, result in results.items():
        output["missing_metrics"].extend(
            [{"category": category, "metric": m} for m in result["missing"]]
        )
    
    print(json.dumps(output, indent=2))


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="NeuroBridge 11D Prometheus Metrics Verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/verify_prometheus_metrics.py
  python scripts/verify_prometheus_metrics.py --url http://localhost:8000/metrics
  python scripts/verify_prometheus_metrics.py --verbose
  python scripts/verify_prometheus_metrics.py --json
  python scripts/verify_prometheus_metrics.py --url http://api.neurobridge.ng/metrics --json
        """
    )
    parser.add_argument(
        "--url", "-u",
        default=DEFAULT_METRICS_URL,
        help=f"Metrics endpoint URL (default: {DEFAULT_METRICS_URL})"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all found and missing metric names"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON (for CI/CD)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=REQUEST_TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {REQUEST_TIMEOUT_SECONDS})"
    )
    
    args = parser.parse_args()
    
    # Fetch metrics
    if not args.json:
        print(cyan(f"\n  Fetching metrics from: {args.url}"))
        print(cyan(f"  Timeout: {args.timeout}s\n"))
    
    success, raw_text, error = fetch_metrics(args.url, args.timeout)
    
    if not success:
        if args.json:
            print(json.dumps({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "metrics_url": args.url,
                "verdict": "ERROR",
                "error": error,
            }, indent=2))
        else:
            print(red(bold(f"\n  ❌ ERROR: Failed to fetch metrics")))
            print(red(f"     {error}"))
            print(red(f"\n  Check that the API server is running and the metrics endpoint is accessible."))
        sys.exit(2)
    
    # Parse metric names
    available_metrics = parse_metric_names(raw_text)
    
    if not args.json:
        print(f"  Metrics endpoint returned {bold(str(len(available_metrics)))} metric names")
    
    # Verify
    results = verify_metrics(available_metrics)
    
    if args.json:
        output_json(results, args.url)
    else:
        all_passed = print_results(results, args.verbose)
    
    # Exit code
    all_passed = all(r["passed"] for r in results.values())
    
    if all_passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()