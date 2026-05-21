"""
================================================================================
NeuroBridge 11D - Nuclear Energy Intelligence Model
Uranium Layer - Safe, Simulation-Only Nuclear Energy Modeling
================================================================================
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone


class ReactorType(str, Enum):
    """Supported nuclear reactor types"""
    PWR = "pwr"      # Pressurized Water Reactor
    BWR = "bwr"      # Boiling Water Reactor
    SMR = "smr"      # Small Modular Reactor
    HTGR = "htgr"    # High-Temperature Gas Reactor
    MSR = "msr"      # Molten Salt Reactor


class CoolingSystem(str, Enum):
    """Cooling system types"""
    ONCE_THROUGH = "once_through"
    COOLING_TOWER = "cooling_tower"
    DRY_COOLING = "dry_cooling"
    HYBRID = "hybrid"


class NuclearInput(BaseModel):
    """Nuclear simulation input parameters"""
    
    reactor_type: ReactorType = Field(
        default=ReactorType.PWR,
        description="Type of nuclear reactor"
    )
    thermal_power_mw: float = Field(
        default=1000.0,
        ge=10.0,
        le=5000.0,
        description="Thermal power output in MW"
    )
    cooling_efficiency: float = Field(
        default=0.33,
        ge=0.2,
        le=0.45,
        description="Cooling system efficiency (0-1)"
    )
    load_demand: float = Field(
        default=800.0,
        ge=0,
        description="Current grid load demand in MW"
    )
    ambient_temp: Optional[float] = Field(
        default=None,
        ge=-20,
        le=50,
        description="Ambient temperature in Celsius (auto-fetched if not provided)"
    )
    safety_margin: Optional[float] = Field(
        default=0.15,
        ge=0.05,
        le=0.30,
        description="Safety margin factor"
    )
    cooling_type: CoolingSystem = Field(
        default=CoolingSystem.COOLING_TOWER,
        description="Cooling system type"
    )
    fuel_burnup_gwdt: Optional[float] = Field(
        default=45.0,
        ge=30,
        le=65,
        description="Fuel burnup in GWd/tU"
    )
    
    @validator('thermal_power_mw')
    def validate_thermal_power(cls, v):
        """Validate thermal power based on reactor type"""
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "reactor_type": "pwr",
                "thermal_power_mw": 1200.0,
                "cooling_efficiency": 0.35,
                "load_demand": 950.0,
                "ambient_temp": 28.5,
                "safety_margin": 0.15,
                "cooling_type": "cooling_tower",
                "fuel_burnup_gwdt": 45.0
            }
        }


class NuclearOutput(BaseModel):
    """Nuclear simulation output"""
    
    electrical_output_mw: float
    thermal_efficiency_percent: float
    stability_score: float
    failure_probability: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    cooling_performance: float
    safety_factor: float
    fuel_efficiency: float
    co2_saved_kg: float
    grid_stability_contribution: float


class NuclearSimulationResponse(BaseModel):
    """Complete nuclear simulation API response"""
    
    success: bool
    simulation_id: str
    mode: str  # SIMULATED / QUANTUM_NATIVE
    yield_metrics: Dict[str, Any]
    physics_intelligence: Dict[str, Any]
    nuclear_safety: Dict[str, Any]
    data_sources: list
    context: str
    kernel_native: bool
    timestamp: str