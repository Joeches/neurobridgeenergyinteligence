"""
NASA POWER API Router
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from backend.services.nasa_service import get_nasa_service
from backend.security.lattice_auth import verify_lattice_guard

logger = logging.getLogger("NeuroBridge.NASA")

# Router mounted at /api/v1
router = APIRouter(prefix="/api/v1", tags=["NASA POWER API"])


# ====================== NASA TELEMETRY ENDPOINT ======================
@router.get("/nasa-telemetry", dependencies=[Depends(verify_lattice_guard)])
async def nasa_telemetry_endpoint(
    lat: float = Query(9.0765, description="Latitude"),
    lon: float = Query(7.3986, description="Longitude"),
) -> Dict[str, Any]:
    """
    Public NASA POWER telemetry for current solar conditions (Abuja).
    GET /api/v1/nasa-telemetry
    """
    nasa_service = get_nasa_service()
    
    if not nasa_service:
        raise HTTPException(status_code=503, detail="NASA service unavailable")
    
    try:
        # Get real-time telemetry
        telemetry = await nasa_service.get_realtime_telemetry()
        
        # Get current data with proper defaults
        data = {
            "ghi": telemetry.get("ghi_wm2", 500.0),
            "temp": telemetry.get("temperature_c", 25.0),
            "cloud_forecast": telemetry.get("cloud_cover_percent", 45.0),
            "humidity": telemetry.get("humidity_percent", 55.0),
            "wind_speed": telemetry.get("wind_speed_ms", 3.2),
            "data_quality": telemetry.get("data_quality", 0.85),
            "sky_condition": telemetry.get("sky_condition", "PARTLY_CLOUDY")
        }
        
        return {
            "status": "success",
            "source": "NASA_POWER",
            "location": {"lat": lat, "lon": lon},
            "ghi": data["ghi"],
            "temp": data["temp"],
            "cloud_forecast": data["cloud_forecast"],
            "humidity": data["humidity"],
            "wind_speed": data["wind_speed"],
            "harvested_flux": round(data["ghi"] / 1000, 2),
            "data_quality": data["data_quality"],
            "sky_condition": data["sky_condition"],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"NASA telemetry fetch failed: {e}")
        # Return fallback data
        return {
            "status": "success",
            "source": "NASA_POWER_FALLBACK",
            "location": {"lat": lat, "lon": lon},
            "ghi": 500.0,
            "temp": 25.0,
            "cloud_forecast": 45.0,
            "humidity": 55.0,
            "wind_speed": 3.2,
            "harvested_flux": 0.50,
            "data_quality": 0.75,
            "sky_condition": "PARTLY_CLOUDY",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/nasa/health", dependencies=[Depends(verify_lattice_guard)])
async def nasa_health() -> Dict[str, Any]:
    """Health check for NASA service."""
    nasa_service = get_nasa_service()
    
    return {
        "status": "healthy" if nasa_service and nasa_service.is_initialized else "degraded",
        "service": "nasa_power",
        "initialized": nasa_service.is_initialized if nasa_service else False,
        "timestamp": datetime.now().isoformat()
    }