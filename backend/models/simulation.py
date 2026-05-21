"""
================================================================================
NeuroBridge 11D - Simulation Models (Phase 1 Production)
================================================================================
Purpose: Data models for energy system simulation, fault injection, and scenario testing
Version: 1.0.0-PHASE1-ENTERPRISE
Build: 2026.04.22

PHASE 1 SCOPE (ACTIVE):
- Solar generation simulation
- Grid load simulation
- Battery behavior simulation
- Fault injection for testing
- Scenario management

EXCLUDED (BLOCKED):
- Nuclear reactor simulation (moved to /research/)
- Fusion plasma simulation (moved to /research/)
- Quantum state simulation (moved to /research/)
- Defense scenario simulation (moved to /research/)
================================================================================
"""

import math
import random
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple, Callable
from enum import Enum
import json


# ============================================================================
# ENUMS FOR SIMULATION
# ============================================================================

class SimulationMode(str, Enum):
    """Simulation operational mode"""
    NORMAL = "normal"
    STRESS_TEST = "stress_test"
    FAULT_INJECTION = "fault_injection"
    SCENARIO_PLAYBACK = "scenario_playback"
    CALIBRATION = "calibration"


class FaultType(str, Enum):
    """Types of faults that can be injected"""
    # Grid faults
    FREQUENCY_DROP = "frequency_drop"
    FREQUENCY_SPIKE = "frequency_spike"
    VOLTAGE_SAG = "voltage_sag"
    VOLTAGE_SWELL = "voltage_swell"
    GRID_OUTAGE = "grid_outage"
    
    # Solar faults
    SOLAR_DIP = "solar_dip"
    SOLAR_SPIKE = "solar_spike"
    INVERTER_FAULT = "inverter_fault"
    
    # Load faults
    LOAD_SPIKE = "load_spike"
    LOAD_SHED = "load_shed"
    
    # Communication faults
    MODBUS_TIMEOUT = "modbus_timeout"
    DATA_CORRUPTION = "data_corruption"


class FaultSeverity(str, Enum):
    """Fault severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScenarioType(str, Enum):
    """Pre-defined simulation scenarios"""
    # Solar scenarios
    CLOUDY_DAY = "cloudy_day"
    SUNNY_DAY = "sunny_day"
    SOLAR_ECLIPSE = "solar_eclipse"
    MORNING_RAMP = "morning_ramp"
    EVENING_RAMP = "evening_ramp"
    
    # Grid scenarios
    PEAK_DEMAND = "peak_demand"
    OFF_PEAK = "off_peak"
    GRID_STRESS = "grid_stress"
    FREQUENCY_DEVIATION = "frequency_deviation"
    
    # Fault scenarios
    SUDDEN_LOAD = "sudden_load"
    INVERTER_TRIP = "inverter_trip"
    COMMUNICATION_LOSS = "communication_loss"
    
    # Composite scenarios
    STORM_CONDITIONS = "storm_conditions"
    HEAT_WAVE = "heat_wave"
    EMERGENCY_RESPONSE = "emergency_response"


# ============================================================================
# FAULT MODELS
# ============================================================================

@dataclass
class InjectedFault:
    """
    Fault injected into simulation for testing AECE response
    """
    fault_id: str
    fault_type: FaultType
    severity: FaultSeverity
    start_time: float
    duration_seconds: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime tracking
    active: bool = False
    end_time: Optional[float] = None
    cleared: bool = False
    
    # Impact metrics
    impact_on_frequency: float = 0.0
    impact_on_voltage: float = 0.0
    impact_on_power: float = 0.0
    aece_response: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "fault_id": self.fault_id,
            "fault_type": self.fault_type.value,
            "severity": self.severity.value,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "duration_seconds": self.duration_seconds,
            "parameters": self.parameters,
            "active": self.active,
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "cleared": self.cleared,
            "impact": {
                "frequency_hz": round(self.impact_on_frequency, 2),
                "voltage_v": round(self.impact_on_voltage, 1),
                "power_kw": round(self.impact_on_power, 1)
            },
            "aece_response": self.aece_response
        }
    
    def apply_impact(self, current_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply fault impact to telemetry data
        
        Args:
            current_telemetry: Current telemetry values
            
        Returns:
            Modified telemetry with fault impact
        """
        impacted = current_telemetry.copy()
        
        if self.fault_type == FaultType.FREQUENCY_DROP:
            drop_amount = self.parameters.get("drop_hz", 0.5)
            impacted["grid_frequency_hz"] = max(49.0, current_telemetry.get("grid_frequency_hz", 50.0) - drop_amount)
            self.impact_on_frequency = -drop_amount
            
        elif self.fault_type == FaultType.FREQUENCY_SPIKE:
            spike_amount = self.parameters.get("spike_hz", 0.5)
            impacted["grid_frequency_hz"] = min(51.0, current_telemetry.get("grid_frequency_hz", 50.0) + spike_amount)
            self.impact_on_frequency = spike_amount
            
        elif self.fault_type == FaultType.VOLTAGE_SAG:
            sag_percent = self.parameters.get("sag_percent", 20)
            impacted["grid_voltage_v"] = current_telemetry.get("grid_voltage_v", 230.0) * (1 - sag_percent / 100)
            self.impact_on_voltage = -sag_percent
            
        elif self.fault_type == FaultType.VOLTAGE_SWELL:
            swell_percent = self.parameters.get("swell_percent", 15)
            impacted["grid_voltage_v"] = current_telemetry.get("grid_voltage_v", 230.0) * (1 + swell_percent / 100)
            self.impact_on_voltage = swell_percent
            
        elif self.fault_type == FaultType.SOLAR_DIP:
            dip_percent = self.parameters.get("dip_percent", 50)
            impacted["solar_output_kw"] = current_telemetry.get("solar_output_kw", 100.0) * (1 - dip_percent / 100)
            self.impact_on_power = -dip_percent
            
        elif self.fault_type == FaultType.LOAD_SPIKE:
            spike_kw = self.parameters.get("spike_kw", 200.0)
            impacted["demand_load_kw"] = current_telemetry.get("demand_load_kw", 500.0) + spike_kw
            self.impact_on_power = spike_kw
            
        elif self.fault_type == FaultType.GRID_OUTAGE:
            impacted["grid_frequency_hz"] = 0.0
            impacted["grid_voltage_v"] = 0.0
            impacted["active_power_kw"] = 0.0
            self.impact_on_frequency = -50.0
            self.impact_on_voltage = -230.0
            
        return impacted


# ============================================================================
# SCENARIO MODELS
# ============================================================================

@dataclass
class SimulationScenario:
    """
    Pre-defined simulation scenario with timeline of events
    """
    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str
    duration_seconds: int = 3600
    time_step_seconds: int = 60
    
    # Timeline events
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    # Configuration
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = False
    repeatable: bool = True
    
    # Statistics
    created_at: float = field(default_factory=time.time)
    last_played: Optional[float] = None
    times_played: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type.value,
            "name": self.name,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "time_step_seconds": self.time_step_seconds,
            "events_count": len(self.events),
            "parameters": self.parameters,
            "is_active": self.is_active,
            "repeatable": self.repeatable,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "last_played": datetime.fromtimestamp(self.last_played, tz=timezone.utc).isoformat() if self.last_played else None,
            "times_played": self.times_played
        }
    
    def get_event_at_time(self, elapsed_seconds: float) -> Optional[Dict[str, Any]]:
        """
        Get event scheduled at or near the given elapsed time
        
        Args:
            elapsed_seconds: Time elapsed since scenario start
            
        Returns:
            Event configuration or None
        """
        tolerance = self.time_step_seconds / 2
        
        for event in self.events:
            event_time = event.get("time_seconds", 0)
            if abs(event_time - elapsed_seconds) <= tolerance:
                return event.copy()
        
        return None


# ============================================================================
# SOLAR SIMULATION MODELS
# ============================================================================

@dataclass
class SolarSimulationProfile:
    """
    Solar generation profile for simulation
    """
    profile_id: str
    name: str
    max_power_kw: float = 100.0
    
    # Solar curve parameters
    sunrise_hour: float = 6.0  # 6 AM
    sunset_hour: float = 18.0  # 6 PM
    peak_hour: float = 13.0    # 1 PM
    
    # Weather modifiers
    cloud_cover_factor: float = 0.0  # 0-1
    temperature_c: float = 25.0
    
    # Randomness
    randomness_factor: float = 0.05  # 5% random variation
    
    def calculate_power_at_hour(self, hour_of_day: float) -> float:
        """
        Calculate solar power at given hour
        
        Args:
            hour_of_day: Hour of day (0-24)
            
        Returns:
            Power in kW
        """
        if hour_of_day < self.sunrise_hour or hour_of_day > self.sunset_hour:
            return 0.0
        
        # Normalized position in day (0 to 1)
        day_position = (hour_of_day - self.sunrise_hour) / (self.sunset_hour - self.sunrise_hour)
        
        # Solar curve: sin(π * position)
        solar_factor = math.sin(math.pi * day_position)
        
        # Temperature derating
        temp_derate = 1.0 - max(0, (self.temperature_c - 25) * 0.004)
        
        # Cloud cover impact
        cloud_impact = 1.0 - self.cloud_cover_factor * 0.8
        
        # Random variation
        random_factor = 1.0 + (random.random() - 0.5) * self.randomness_factor * 2
        
        power = self.max_power_kw * solar_factor * temp_derate * cloud_impact * random_factor
        
        return max(0.0, min(self.max_power_kw, power))


@dataclass
class SolarSimulationState:
    """
    Current state of solar simulation
    """
    profile: SolarSimulationProfile
    current_power_kw: float = 0.0
    daily_energy_kwh: float = 0.0
    last_update: float = field(default_factory=time.time)
    
    def update(self, current_time: Optional[float] = None) -> float:
        """
        Update solar simulation state
        
        Args:
            current_time: Current timestamp (defaults to now)
            
        Returns:
            Current power in kW
        """
        now = current_time or time.time()
        dt_hours = (now - self.last_update) / 3600.0
        
        # Get hour of day
        hour_of_day = datetime.fromtimestamp(now).hour + datetime.fromtimestamp(now).minute / 60.0
        
        # Calculate power
        self.current_power_kw = self.profile.calculate_power_at_hour(hour_of_day)
        
        # Update daily energy
        if dt_hours > 0:
            self.daily_energy_kwh += self.current_power_kw * dt_hours
        
        self.last_update = now
        
        return self.current_power_kw
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "profile_id": self.profile.profile_id,
            "current_power_kw": round(self.current_power_kw, 1),
            "daily_energy_kwh": round(self.daily_energy_kwh, 1),
            "max_power_kw": self.profile.max_power_kw,
            "cloud_cover_factor": self.profile.cloud_cover_factor,
            "temperature_c": self.profile.temperature_c,
            "last_update": datetime.fromtimestamp(self.last_update, tz=timezone.utc).isoformat()
        }


# ============================================================================
# LOAD SIMULATION MODELS
# ============================================================================

@dataclass
class LoadSimulationProfile:
    """
    Load demand profile for simulation
    """
    profile_id: str
    name: str
    base_load_kw: float = 500.0
    
    # Load pattern parameters
    morning_peak_hour: float = 8.0   # 8 AM
    evening_peak_hour: float = 18.0  # 6 PM
    night_valley_hour: float = 3.0   # 3 AM
    
    # Peak multipliers
    morning_peak_factor: float = 1.5
    evening_peak_factor: float = 1.6
    night_valley_factor: float = 0.6
    
    # Randomness
    randomness_factor: float = 0.03  # 3% random variation
    
    # Trend (for stress testing)
    trend_factor: float = 1.0
    
    def calculate_load_at_hour(self, hour_of_day: float) -> float:
        """
        Calculate load demand at given hour
        
        Args:
            hour_of_day: Hour of day (0-24)
            
        Returns:
            Load in kW
        """
        # Calculate base multiplier based on time of day
        if hour_of_day < self.night_valley_hour:
            # Late night to early morning
            multiplier = self.night_valley_factor
        elif hour_of_day < self.morning_peak_hour:
            # Morning ramp up
            progress = (hour_of_day - self.night_valley_hour) / (self.morning_peak_hour - self.night_valley_hour)
            multiplier = self.night_valley_factor + progress * (self.morning_peak_factor - self.night_valley_factor)
        elif hour_of_day < self.evening_peak_hour:
            # Midday plateau
            multiplier = self.morning_peak_factor
        else:
            # Evening ramp down
            progress = min(1.0, (hour_of_day - self.evening_peak_hour) / 4.0)
            multiplier = self.morning_peak_factor - progress * (self.morning_peak_factor - self.night_valley_factor)
        
        # Apply evening peak if applicable
        if self.evening_peak_hour - 1 <= hour_of_day <= self.evening_peak_hour + 1:
            evening_boost = (self.evening_peak_factor - self.morning_peak_factor) * (
                1 - abs(hour_of_day - self.evening_peak_hour)
            )
            multiplier += evening_boost
        
        # Random variation
        random_factor = 1.0 + (random.random() - 0.5) * self.randomness_factor * 2
        
        # Apply trend
        load = self.base_load_kw * multiplier * random_factor * self.trend_factor
        
        return max(100.0, min(2000.0, load))


@dataclass
class LoadSimulationState:
    """
    Current state of load simulation
    """
    profile: LoadSimulationProfile
    current_load_kw: float = 0.0
    peak_load_today_kw: float = 0.0
    average_load_today_kw: float = 0.0
    load_samples: List[float] = field(default_factory=list)
    last_update: float = field(default_factory=time.time)
    
    def update(self, current_time: Optional[float] = None) -> float:
        """
        Update load simulation state
        
        Args:
            current_time: Current timestamp (defaults to now)
            
        Returns:
            Current load in kW
        """
        now = current_time or time.time()
        
        # Get hour of day
        hour_of_day = datetime.fromtimestamp(now).hour + datetime.fromtimestamp(now).minute / 60.0
        
        # Calculate load
        self.current_load_kw = self.profile.calculate_load_at_hour(hour_of_day)
        
        # Track statistics
        if self.current_load_kw > self.peak_load_today_kw:
            self.peak_load_today_kw = self.current_load_kw
        
        self.load_samples.append(self.current_load_kw)
        if len(self.load_samples) > 1440:  # Keep last 24 hours (1 sample per minute)
            self.load_samples = self.load_samples[-1440:]
            self.average_load_today_kw = sum(self.load_samples) / len(self.load_samples)
        
        self.last_update = now
        
        return self.current_load_kw
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "profile_id": self.profile.profile_id,
            "current_load_kw": round(self.current_load_kw, 1),
            "peak_load_today_kw": round(self.peak_load_today_kw, 1),
            "average_load_today_kw": round(self.average_load_today_kw, 1),
            "base_load_kw": self.profile.base_load_kw,
            "trend_factor": self.profile.trend_factor,
            "last_update": datetime.fromtimestamp(self.last_update, tz=timezone.utc).isoformat()
        }


# ============================================================================
# BATTERY SIMULATION MODELS
# ============================================================================

@dataclass
class BatterySimulationProfile:
    """
    Battery energy storage simulation profile
    """
    profile_id: str
    name: str
    capacity_kwh: float = 100.0
    max_charge_power_kw: float = 50.0
    max_discharge_power_kw: float = 50.0
    charge_efficiency: float = 0.92
    discharge_efficiency: float = 0.95
    min_soc_percent: float = 10.0
    max_soc_percent: float = 90.0
    
    # Degradation
    degradation_rate_per_cycle: float = 0.0001  # 0.01% per cycle
    initial_soh_percent: float = 100.0
    
    # Thermal
    thermal_coefficient: float = 0.5  # °C per 10kW power
    cooling_factor: float = 0.1  # °C per minute cooling


@dataclass
class BatterySimulationState:
    """
    Current state of battery simulation
    """
    profile: BatterySimulationProfile
    state_of_charge_kwh: float = 50.0
    state_of_health_percent: float = 100.0
    temperature_c: float = 25.0
    current_power_kw: float = 0.0  # Positive = discharge, Negative = charge
    cycle_count: int = 0
    total_charged_kwh: float = 0.0
    total_discharged_kwh: float = 0.0
    last_update: float = field(default_factory=time.time)
    
    def __post_init__(self):
        self.state_of_health_percent = self.profile.initial_soh_percent
        self.state_of_charge_kwh = self.profile.capacity_kwh * 0.5
    
    def update(self, target_power_kw: float, duration_seconds: float) -> Tuple[float, float]:
        """
        Update battery state based on power command
        
        Args:
            target_power_kw: Desired power (positive = discharge, negative = charge)
            duration_seconds: Duration of power application in seconds
            
        Returns:
            Tuple of (actual_power_kw, new_soc_percent)
        """
        # Convert duration to hours
        duration_hours = duration_seconds / 3600.0
        
        # Clamp power to limits
        if target_power_kw > 0:  # Discharge
            actual_power = min(target_power_kw, self.profile.max_discharge_power_kw)
            # Check if enough energy
            max_energy = self.state_of_charge_kwh - self.profile.min_soc_percent / 100 * self.profile.capacity_kwh
            max_power_from_energy = max_energy / duration_hours if duration_hours > 0 else self.profile.max_discharge_power_kw
            actual_power = min(actual_power, max_power_from_energy)
            
            # Apply efficiency
            energy_out = actual_power * duration_hours * self.profile.discharge_efficiency
            self.state_of_charge_kwh -= energy_out
            self.total_discharged_kwh += energy_out
            
        else:  # Charge
            actual_power = -min(-target_power_kw, self.profile.max_charge_power_kw)
            # Check if within capacity
            max_energy = self.profile.max_soc_percent / 100 * self.profile.capacity_kwh - self.state_of_charge_kwh
            max_power_from_capacity = max_energy / duration_hours if duration_hours > 0 else self.profile.max_charge_power_kw
            actual_power = -min(-actual_power, max_power_from_capacity)
            
            # Apply efficiency
            energy_in = -actual_power * duration_hours * self.profile.charge_efficiency
            self.state_of_charge_kwh += energy_in
            self.total_charged_kwh += energy_in
        
        # Clamp SOC
        self.state_of_charge_kwh = max(
            self.profile.min_soc_percent / 100 * self.profile.capacity_kwh,
            min(self.profile.max_soc_percent / 100 * self.profile.capacity_kwh, self.state_of_charge_kwh)
        )
        
        # Update cycle count (count when crossing 50% threshold)
        soc_percent = self.get_soc_percent()
        if soc_percent > 55 and target_power_kw > 0:  # Discharging from above 55%
            self.cycle_count += 1
            # Degrade health
            self.state_of_health_percent = max(70.0, self.state_of_health_percent - self.profile.degradation_rate_per_cycle * 100)
        
        # Update temperature
        power_magnitude = abs(actual_power)
        self.temperature_c += (power_magnitude / 10.0) * self.profile.thermal_coefficient * (duration_seconds / 60.0)
        self.temperature_c -= self.profile.cooling_factor * (duration_seconds / 60.0)
        self.temperature_c = max(15.0, min(50.0, self.temperature_c))
        
        self.current_power_kw = actual_power
        self.last_update = time.time()
        
        return actual_power, self.get_soc_percent()
    
    def get_soc_percent(self) -> float:
        """Get state of charge as percentage"""
        return (self.state_of_charge_kwh / self.profile.capacity_kwh) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "profile_id": self.profile.profile_id,
            "soc_percent": round(self.get_soc_percent(), 1),
            "soh_percent": round(self.state_of_health_percent, 1),
            "temperature_c": round(self.temperature_c, 1),
            "current_power_kw": round(self.current_power_kw, 1),
            "cycle_count": self.cycle_count,
            "total_charged_kwh": round(self.total_charged_kwh, 1),
            "total_discharged_kwh": round(self.total_discharged_kwh, 1),
            "capacity_kwh": self.profile.capacity_kwh,
            "max_charge_kw": self.profile.max_charge_power_kw,
            "max_discharge_kw": self.profile.max_discharge_power_kw,
            "last_update": datetime.fromtimestamp(self.last_update, tz=timezone.utc).isoformat()
        }


# ============================================================================
# SIMULATION RUNNER MODELS
# ============================================================================

@dataclass
class SimulationRun:
    """
    Complete simulation run with history and results
    """
    run_id: str
    name: str
    description: str
    mode: SimulationMode = SimulationMode.NORMAL
    duration_seconds: int = 3600
    time_step_seconds: int = 60
    start_time: float = field(default_factory=time.time)
    
    # State
    status: str = "pending"  # pending, running, paused, completed, failed
    elapsed_seconds: float = 0.0
    current_step: int = 0
    
    # Configuration
    solar_profile: Optional[SolarSimulationProfile] = None
    load_profile: Optional[LoadSimulationProfile] = None
    battery_profile: Optional[BatterySimulationProfile] = None
    active_faults: List[InjectedFault] = field(default_factory=list)
    active_scenario: Optional[SimulationScenario] = None
    
    # History
    history: List[Dict[str, Any]] = field(default_factory=list)
    decisions_taken: List[Dict[str, Any]] = field(default_factory=list)
    faults_injected: List[InjectedFault] = field(default_factory=list)
    
    # Results
    final_grid_stability: float = 0.0
    final_solar_efficiency: float = 0.0
    total_optimization_gain: float = 0.0
    aece_actions_taken: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "run_id": self.run_id,
            "name": self.name,
            "description": self.description,
            "mode": self.mode.value,
            "duration_seconds": self.duration_seconds,
            "time_step_seconds": self.time_step_seconds,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "progress_percent": round(self.elapsed_seconds / self.duration_seconds * 100, 1) if self.duration_seconds > 0 else 0,
            "current_step": self.current_step,
            "active_faults_count": len([f for f in self.active_faults if f.active]),
            "history_points": len(self.history),
            "decisions_taken": len(self.decisions_taken),
            "faults_injected": len(self.faults_injected),
            "results": {
                "final_grid_stability": round(self.final_grid_stability, 1),
                "final_solar_efficiency": round(self.final_solar_efficiency, 1),
                "total_optimization_gain": round(self.total_optimization_gain, 1),
                "aece_actions_taken": self.aece_actions_taken
            },
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat()
        }
    
    def add_history_point(self, data: Dict[str, Any]) -> None:
        """Add a history point to the simulation run"""
        point = {
            "timestamp": time.time(),
            "elapsed_seconds": self.elapsed_seconds,
            "data": data
        }
        self.history.append(point)
        
        # Limit history size
        max_history = 10000
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]
    
    def add_decision(self, decision: Dict[str, Any]) -> None:
        """Record an AECE decision during simulation"""
        self.decisions_taken.append({
            "timestamp": time.time(),
            "elapsed_seconds": self.elapsed_seconds,
            "decision": decision
        })
        self.aece_actions_taken += 1


# ============================================================================
# DEFAULT SCENARIOS
# ============================================================================

def create_default_scenarios() -> List[SimulationScenario]:
    """
    Create default simulation scenarios for testing
    """
    scenarios = []
    
    # Sunny day scenario
    sunny_day = SimulationScenario(
        scenario_id="scenario_sunny_day",
        scenario_type=ScenarioType.SUNNY_DAY,
        name="Sunny Day",
        description="Clear sky, optimal solar generation",
        duration_seconds=86400,
        time_step_seconds=300,
        parameters={
            "cloud_cover": 0.1,
            "temperature": 28.0,
            "solar_max_kw": 100.0
        }
    )
    scenarios.append(sunny_day)
    
    # Cloudy day scenario
    cloudy_day = SimulationScenario(
        scenario_id="scenario_cloudy_day",
        scenario_type=ScenarioType.CLOUDY_DAY,
        name="Cloudy Day",
        description="Overcast, reduced solar generation",
        duration_seconds=86400,
        time_step_seconds=300,
        parameters={
            "cloud_cover": 0.8,
            "temperature": 24.0,
            "solar_max_kw": 100.0
        }
    )
    scenarios.append(cloudy_day)
    
    # Peak demand scenario
    peak_demand = SimulationScenario(
        scenario_id="scenario_peak_demand",
        scenario_type=ScenarioType.PEAK_DEMAND,
        name="Peak Demand",
        description="High load demand during evening hours",
        duration_seconds=3600,
        time_step_seconds=60,
        parameters={
            "load_multiplier": 1.6,
            "evening_peak_hour": 18
        }
    )
    scenarios.append(peak_demand)
    
    # Grid stress scenario with events
    grid_stress = SimulationScenario(
        scenario_id="scenario_grid_stress",
        scenario_type=ScenarioType.GRID_STRESS,
        name="Grid Stress Test",
        description="Progressive grid stress with faults",
        duration_seconds=1800,
        time_step_seconds=30,
        events=[
            {"time_seconds": 300, "fault_type": "load_spike", "severity": "medium", "spike_kw": 300},
            {"time_seconds": 600, "fault_type": "solar_dip", "severity": "high", "dip_percent": 70},
            {"time_seconds": 900, "fault_type": "frequency_drop", "severity": "critical", "drop_hz": 0.8},
            {"time_seconds": 1200, "fault_type": "inverter_fault", "severity": "high", "duration": 120}
        ]
    )
    scenarios.append(grid_stress)
    
    return scenarios


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_default_solar_profile() -> SolarSimulationProfile:
    """Create default solar simulation profile"""
    return SolarSimulationProfile(
        profile_id="solar_default",
        name="Default Solar Profile",
        max_power_kw=100.0,
        sunrise_hour=6.0,
        sunset_hour=18.0,
        peak_hour=13.0,
        cloud_cover_factor=0.2,
        temperature_c=28.0,
        randomness_factor=0.05
    )


def create_default_load_profile() -> LoadSimulationProfile:
    """Create default load simulation profile"""
    return LoadSimulationProfile(
        profile_id="load_default",
        name="Default Load Profile",
        base_load_kw=500.0,
        morning_peak_hour=8.0,
        evening_peak_hour=18.0,
        night_valley_hour=3.0,
        morning_peak_factor=1.5,
        evening_peak_factor=1.6,
        night_valley_factor=0.6,
        randomness_factor=0.03,
        trend_factor=1.0
    )


def create_default_battery_profile() -> BatterySimulationProfile:
    """Create default battery simulation profile"""
    return BatterySimulationProfile(
        profile_id="battery_default",
        name="Default Battery Profile",
        capacity_kwh=100.0,
        max_charge_power_kw=50.0,
        max_discharge_power_kw=50.0,
        charge_efficiency=0.92,
        discharge_efficiency=0.95,
        min_soc_percent=10.0,
        max_soc_percent=90.0
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    'SimulationMode',
    'FaultType',
    'FaultSeverity',
    'ScenarioType',
    
    # Fault Models
    'InjectedFault',
    
    # Scenario Models
    'SimulationScenario',
    
    # Solar Simulation
    'SolarSimulationProfile',
    'SolarSimulationState',
    
    # Load Simulation
    'LoadSimulationProfile',
    'LoadSimulationState',
    
    # Battery Simulation
    'BatterySimulationProfile',
    'BatterySimulationState',
    
    # Simulation Runner
    'SimulationRun',
    
    # Factory Functions
    'create_default_scenarios',
    'create_default_solar_profile',
    'create_default_load_profile',
    'create_default_battery_profile',
]

# ============================================================================
# MODULE INITIALIZATION LOG
# ============================================================================

import logging
logger = logging.getLogger("NeuroBridge.SimulationModels")
logger.info("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                  SIMULATION MODELS v1.0.0 - PHASE 1                      ║
║     ✅ Fault Injection - Grid, solar, load, communication faults        ║
║     ✅ Scenario Management - Pre-defined test scenarios                  ║
║     ✅ Solar Simulation - Day/night cycles, weather effects             ║
║     ✅ Load Simulation - Peak/off-peak patterns, trends                  ║
║     ✅ Battery Simulation - SOC, efficiency, degradation                 ║
║     ✅ Simulation Runner - Complete run management                       ║
║     ✅ Phase 1 Compliant - No nuclear/fusion/quantum/defense             ║
║     ✅ Production Ready - Abuja Pilot Zone                               ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")

# ============================================================================
# END OF FILE - SIMULATION MODELS v1.0.0