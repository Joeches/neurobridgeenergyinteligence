"""
================================================================================
NeuroBridge 11D - Optimization Routes (Phase 1 Production)
================================================================================
Purpose: Expose optimization metrics and reports via API
Endpoints:
- GET /api/v1/energy/status - Current system status
- GET /api/v1/energy/optimization-report - Detailed optimization report
- GET /api/v1/energy/metrics/live - Live metrics stream
- GET /api/v1/energy/grid-stability - Grid stability metrics (GSI)
- GET /api/v1/energy/solar-efficiency - Solar efficiency metrics (SES)
- GET /api/v1/energy/adfi/status - ADFI engine status
- POST /api/v1/energy/adfi/force-source - Force ADFI data source (CTO only)
- POST /api/v1/energy/generate-scenario - Generate synthetic scenario (CTO only)
================================================================================
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import asyncio
import json

from backend.core.optimization_metrics import get_metrics_engine
from backend.aece.decision_engine_v2 import get_decision_engine
from backend.aece.action_executor_v2 import get_action_executor
from backend.hardware.simulator_enhanced import get_simulator

# NEW IMPORTS FOR ADDED FUNCTIONALITY
from backend.core.energy_metrics_engine import get_energy_metrics_engine
from backend.ingestion.adfi_engine import get_adfi_engine
from backend.ingestion.huggingface_generator import get_hf_generator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/energy", tags=["energy-optimization"])


# =============================================================================
# AUTHENTICATION & AUTHORIZATION DEPENDENCIES
# =============================================================================

async def validate_token(auth_header: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate authentication token.
    In production, this would validate JWT tokens.
    For Phase 1, returns basic auth info.
    """
    # Phase 1 simplified auth - will be enhanced in production
    return {
        "authenticated": True,
        "user_id": "system",
        "role": "cto"  # For demo, all users have CTO access
    }


async def require_cto(auth_info: Dict[str, Any] = Depends(validate_token)) -> bool:
    """
    Require CTO-level authorization for sensitive operations.
    """
    if auth_info.get("role") != "cto":
        raise HTTPException(
            status_code=403,
            detail="CTO authorization required for this operation"
        )
    return True


# =============================================================================
# EXISTING ENDPOINTS (PRESERVED AND ENHANCED)
# =============================================================================

@router.get("/status")
async def get_energy_status(auth_info: Dict[str, Any] = Depends(validate_token)) -> Dict[str, Any]:
    """
    Get current energy system status including optimization metrics.
    """
    try:
        metrics_engine = get_metrics_engine()
        decision_engine = get_decision_engine()
        action_executor = get_action_executor()
        simulator = get_simulator()
        
        current_metrics = metrics_engine.get_current_metrics()
        trend = metrics_engine.get_optimization_trend()
        telemetry = simulator.get_telemetry()
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "optimization": {
                "current_score": current_metrics.get("optimization_score", 0) if current_metrics else 0,
                "grid_stability": current_metrics.get("grid_stability_score", 0) if current_metrics else 0,
                "solar_efficiency": current_metrics.get("solar_efficiency_score", 0) if current_metrics else 0,
                "trend": trend.value if hasattr(trend, 'value') else str(trend),
                "total_gain": metrics_engine.get_total_optimization_gain(),
                "actions_taken": metrics_engine.get_stats().get("total_actions", 0)
            },
            "telemetry": telemetry,
            "aece": {
                "last_decision": decision_engine.get_recent_decisions(1)[0] if decision_engine.get_recent_decisions(1) else None,
                "total_decisions": decision_engine.get_stats().get("total_decisions", 0),
                "actions_executed": action_executor.get_stats().get("total_actions", 0)
            }
        }
    except Exception as e:
        logger.error(f"Error in get_energy_status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve energy status: {str(e)}"
        )


@router.get("/optimization-report")
async def get_optimization_report(auth_info: Dict[str, Any] = Depends(validate_token)) -> Dict[str, Any]:
    """
    Get detailed optimization report with before/after comparisons.
    """
    try:
        metrics_engine = get_metrics_engine()
        decision_engine = get_decision_engine()
        action_executor = get_action_executor()
        
        stats = metrics_engine.get_stats()
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "current_optimization_score": stats.get("current", {}).get("optimization_score", 0) if stats.get("current") else 0,
                "total_actions": stats.get("total_actions", 0),
                "total_optimization_gain": stats.get("total_optimization_gain", 0.0),
                "average_gain_per_action": stats.get("average_gain_per_action", 0.0),
                "trend": stats.get("trend", "stable")
            },
            "recent_impacts": stats.get("recent_impacts", []),
            "aece_stats": decision_engine.get_stats(),
            "action_stats": action_executor.get_stats(),
            "weights": stats.get("weights", {})
        }
    except Exception as e:
        logger.error(f"Error in get_optimization_report: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve optimization report: {str(e)}"
        )


@router.get("/metrics/live")
async def get_live_metrics(auth_info: Dict[str, Any] = Depends(validate_token)) -> Dict[str, Any]:
    """
    Get live metrics snapshot (non-streaming version).
    """
    try:
        metrics_engine = get_metrics_engine()
        simulator = get_simulator()
        
        current_metrics = metrics_engine.get_current_metrics()
        telemetry = simulator.get_telemetry()
        
        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "optimization_metrics": current_metrics,
            "telemetry": telemetry,
            "grid_health": {
                "frequency": telemetry.get("grid_frequency_hz", 0),
                "voltage": telemetry.get("voltage_v", 0),
                "load_demand_kw": telemetry.get("demand_load_kw", 0),
                "supply_kw": telemetry.get("active_power_kw", 0) + telemetry.get("solar_output_kw", 0)
            }
        }
    except Exception as e:
        logger.error(f"Error in get_live_metrics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve live metrics: {str(e)}"
        )


# =============================================================================
# NEW ENDPOINTS: GRID STABILITY METRICS (GSI)
# =============================================================================

@router.get("/grid-stability")
async def get_grid_stability(auth_info: Dict[str, Any] = Depends(validate_token)) -> Dict[str, Any]:
    """
    Get detailed grid stability metrics (GSI)
    
    Returns:
        - grid_stability_index: Composite stability score (0-100)
        - risk_level: Low/Medium/High/Critical
        - frequency_quality: Frequency deviation quality score
        - voltage_quality: Voltage regulation quality score
        - balance_quality: Supply-demand balance quality score
        - fluctuation_index: Solar fluctuation impact index
        - components: Detailed component breakdown
    """
    try:
        metrics_engine = get_energy_metrics_engine()
        adfi_engine = get_adfi_engine()
        
        # Get latest telemetry with timeout protection
        telemetry = await asyncio.wait_for(
            adfi_engine.get_telemetry(),
            timeout=5.0
        )
        
        # Validate telemetry data
        if telemetry is None:
            raise HTTPException(
                status_code=503,
                detail="Telemetry data unavailable - ADFI engine not ready"
            )
        
        # Calculate supply and demand
        supply_kw = getattr(telemetry, 'active_power_kw', 0) + getattr(telemetry, 'solar_output_kw', 0)
        demand_kw = getattr(telemetry, 'demand_load_kw', 0)
        
        # Get fluctuation index with fallback
        try:
            fluctuation_index = metrics_engine.get_fluctuation_index()
        except Exception as e:
            logger.warning(f"Could not get fluctuation index: {e}")
            fluctuation_index = 0.0
        
        # Calculate grid stability
        stability = metrics_engine.calculate_grid_stability_index(
            frequency_hz=getattr(telemetry, 'grid_frequency_hz', 60.0),
            voltage_v=getattr(telemetry, 'grid_voltage_v', 240.0),
            supply_kw=supply_kw,
            demand_kw=demand_kw,
            solar_variance=fluctuation_index
        )
        
        # Extract stability attributes with safe access
        stability_index = getattr(stability, 'stability_index', 0.0)
        risk_level = getattr(stability, 'risk_level', 'Unknown')
        frequency_quality = getattr(stability, 'frequency_quality', 0.0)
        voltage_quality = getattr(stability, 'voltage_quality', 0.0)
        balance_quality = getattr(stability, 'balance_quality', 0.0)
        fluctuation_idx = getattr(stability, 'fluctuation_index', 0.0)
        components = getattr(stability, 'components', {})
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "stability": {
                "grid_stability_index": stability_index,
                "risk_level": risk_level,
                "frequency_quality": frequency_quality,
                "voltage_quality": voltage_quality,
                "balance_quality": balance_quality,
                "fluctuation_index": fluctuation_idx,
                "components": components
            },
            "telemetry_source": getattr(telemetry.source, 'value', 'unknown'),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except asyncio.TimeoutError:
        logger.error("Timeout getting telemetry for grid stability")
        raise HTTPException(
            status_code=504,
            detail="Telemetry request timeout - please try again"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_grid_stability: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate grid stability: {str(e)}"
        )


# =============================================================================
# NEW ENDPOINTS: SOLAR EFFICIENCY METRICS (SES)
# =============================================================================

@router.get("/solar-efficiency")
async def get_solar_efficiency(auth_info: Dict[str, Any] = Depends(validate_token)) -> Dict[str, Any]:
    """
    Get detailed solar efficiency metrics (SES)
    
    Returns:
        - solar_efficiency_score: Overall efficiency score (0-100)
        - irradiance_quality: Solar irradiance quality score
        - temperature_derating: Temperature-based derating factor
        - cloud_impact: Cloud cover impact score
        - expected_output_kw: Theoretical maximum output
        - actual_output_kw: Current measured output
        - loss_percent: Efficiency loss percentage
    """
    try:
        metrics_engine = get_energy_metrics_engine()
        adfi_engine = get_adfi_engine()
        
        # Get latest telemetry with timeout protection
        telemetry = await asyncio.wait_for(
            adfi_engine.get_telemetry(),
            timeout=5.0
        )
        
        # Validate telemetry data
        if telemetry is None:
            raise HTTPException(
                status_code=503,
                detail="Telemetry data unavailable - ADFI engine not ready"
            )
        
        # Panel capacity (100kW default for Phase 1)
        panel_capacity_kw = 100.0
        
        # Calculate solar efficiency
        efficiency = metrics_engine.calculate_solar_efficiency_score(
            actual_output_kw=getattr(telemetry, 'solar_output_kw', 0),
            irradiance_wm2=getattr(telemetry, 'irradiance_wm2', 0),
            temperature_c=getattr(telemetry, 'temperature_c', 25.0),
            cloud_cover_percent=getattr(telemetry, 'cloud_cover_percent', 0),
            panel_capacity_kw=panel_capacity_kw
        )
        
        # Extract efficiency attributes with safe access
        efficiency_score = getattr(efficiency, 'efficiency_score', 0.0)
        irradiance_quality = getattr(efficiency, 'irradiance_quality', 0.0)
        temperature_derating = getattr(efficiency, 'temperature_derating', 1.0)
        cloud_impact = getattr(efficiency, 'cloud_impact', 1.0)
        expected_output_kw = getattr(efficiency, 'expected_output_kw', 0.0)
        actual_output_kw = getattr(efficiency, 'actual_output_kw', 0.0)
        loss_percent = getattr(efficiency, 'loss_percent', 0.0)
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "efficiency": {
                "solar_efficiency_score": efficiency_score,
                "irradiance_quality": irradiance_quality,
                "temperature_derating": temperature_derating,
                "cloud_impact": cloud_impact,
                "expected_output_kw": expected_output_kw,
                "actual_output_kw": actual_output_kw,
                "loss_percent": loss_percent
            },
            "telemetry_source": getattr(telemetry.source, 'value', 'unknown'),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except asyncio.TimeoutError:
        logger.error("Timeout getting telemetry for solar efficiency")
        raise HTTPException(
            status_code=504,
            detail="Telemetry request timeout - please try again"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_solar_efficiency: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate solar efficiency: {str(e)}"
        )


# =============================================================================
# NEW ENDPOINTS: ADFI ENGINE STATUS
# =============================================================================

@router.get("/adfi/status")
async def get_adfi_status(auth_info: Dict[str, Any] = Depends(validate_token)) -> Dict[str, Any]:
    """
    Get ADFI engine status and source statistics
    
    Returns:
        - adfi_stats: ADFI engine operational statistics
        - hf_generator_stats: HuggingFace generator statistics
    """
    try:
        adfi_engine = get_adfi_engine()
        hf_generator = get_hf_generator()
        
        # Get statistics with error handling
        try:
            adfi_stats = adfi_engine.get_statistics()
        except Exception as e:
            logger.warning(f"Could not get ADFI statistics: {e}")
            adfi_stats = {"error": "Statistics unavailable", "status": "degraded"}
        
        try:
            hf_stats = hf_generator.get_statistics()
        except Exception as e:
            logger.warning(f"Could not get HF generator statistics: {e}")
            hf_stats = {"error": "Statistics unavailable", "status": "degraded"}
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "adfi_stats": adfi_stats,
            "hf_generator_stats": hf_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in get_adfi_status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve ADFI status: {str(e)}"
        )


# =============================================================================
# NEW ENDPOINTS: FORCE ADFI DATA SOURCE (CTO ONLY)
# =============================================================================

@router.post("/adfi/force-source")
async def force_adfi_source(
    source: str = Query(..., description="Data source: hardware, api_live, api_cached, synthetic, fallback"),
    auth_info: Dict[str, Any] = Depends(validate_token),
    cto_authorized: bool = Depends(require_cto)
) -> Dict[str, Any]:
    """
    Force ADFI to use a specific data source (CTO only)
    
    Sources:
        - hardware: Direct hardware telemetry
        - api_live: Live API data
        - api_cached: Cached API data
        - synthetic: Generated synthetic data
        - fallback: Emergency fallback data
    
    Requires CTO-level authorization.
    """
    try:
        from backend.ingestion.adfi_engine import DataSource
        
        source_map = {
            "hardware": DataSource.HARDWARE,
            "api_live": DataSource.API_LIVE,
            "api_cached": DataSource.API_CACHED,
            "synthetic": DataSource.SYNTHETIC,
            "fallback": DataSource.FALLBACK
        }
        
        # Validate source parameter
        if source not in source_map:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source. Options: {list(source_map.keys())}"
            )
        
        adfi_engine = get_adfi_engine()
        
        # Force telemetry from specified source with timeout
        telemetry = await asyncio.wait_for(
            adfi_engine.get_telemetry(force_source=source_map[source]),
            timeout=10.0
        )
        
        if telemetry is None:
            raise HTTPException(
                status_code=503,
                detail=f"Failed to get telemetry from source: {source}"
            )
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "forced_source": source,
            "telemetry": telemetry.to_dict() if hasattr(telemetry, 'to_dict') else {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout forcing telemetry from source: {source}")
        raise HTTPException(
            status_code=504,
            detail=f"Timeout forcing telemetry from source: {source}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in force_adfi_source: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to force data source: {str(e)}"
        )


# =============================================================================
# NEW ENDPOINTS: GENERATE SYNTHETIC SCENARIO (CTO ONLY)
# =============================================================================

@router.post("/generate-scenario")
async def generate_scenario(
    scenario_type: str = Query("sunny_day", description="Scenario type: sunny_day, cloudy_day, grid_stress, fault_injection"),
    duration_seconds: int = Query(300, ge=60, le=3600, description="Scenario duration in seconds (60-3600)"),
    auth_info: Dict[str, Any] = Depends(validate_token),
    cto_authorized: bool = Depends(require_cto)
) -> Dict[str, Any]:
    """
    Generate a synthetic scenario for testing (CTO only)
    
    Scenarios:
        - sunny_day: High solar output, stable grid
        - cloudy_day: Variable solar output, minor fluctuations
        - grid_stress: Grid frequency/voltage disturbances
        - fault_injection: Simulated equipment faults
    
    Requires CTO-level authorization.
    """
    try:
        # Validate scenario type
        valid_scenarios = ["sunny_day", "cloudy_day", "grid_stress", "fault_injection"]
        if scenario_type not in valid_scenarios:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scenario_type. Options: {valid_scenarios}"
            )
        
        # Validate duration
        if duration_seconds < 60 or duration_seconds > 3600:
            raise HTTPException(
                status_code=400,
                detail="duration_seconds must be between 60 and 3600"
            )
        
        hf_generator = get_hf_generator()
        
        # Generate scenario with timeout protection
        results = await asyncio.wait_for(
            asyncio.to_thread(
                hf_generator.generate_scenario,
                scenario_type=scenario_type,
                duration_seconds=duration_seconds,
                step_seconds=10
            ),
            timeout=30.0
        )
        
        if not results:
            raise HTTPException(
                status_code=503,
                detail="Failed to generate scenario - no data points returned"
            )
        
        # Convert results to serializable format
        sample_data = []
        for r in results[:5]:
            if hasattr(r, '__dict__'):
                sample_data.append(r.__dict__)
            elif isinstance(r, dict):
                sample_data.append(r)
            else:
                sample_data.append(str(r))
        
        return {
            "success": True,
            "phase": "PHASE_1_PRODUCTION",
            "scenario_type": scenario_type,
            "duration_seconds": duration_seconds,
            "data_points": len(results),
            "sample": sample_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout generating scenario: {scenario_type}")
        raise HTTPException(
            status_code=504,
            detail=f"Scenario generation timeout for type: {scenario_type}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_scenario: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate scenario: {str(e)}"
        )


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for the optimization routes.
    """
    return {
        "status": "healthy",
        "service": "optimization_routes",
        "phase": "PHASE_1_PRODUCTION",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoints_available": [
            "/status",
            "/optimization-report",
            "/metrics/live",
            "/grid-stability",
            "/solar-efficiency",
            "/adfi/status",
            "/adfi/force-source",
            "/generate-scenario"
        ]
    }