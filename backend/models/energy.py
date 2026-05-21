"""
================================================================================
NeuroBridge 11D - Energy Models (Phase 1 Production)
================================================================================
Purpose: Data models for energy optimization, telemetry, and grid stability
Version: 2.0.0-PHASE1-ENTERPRISE
Build: 2026.04.22

PHASE 1 SCOPE (ACTIVE):
- Solar Optimization Models
- Grid Stability Models
- Telemetry Data Models
- AECE Decision Models

EXCLUDED (BLOCKED):
- Nuclear models (moved to /research/)
- Fusion models (moved to /research/)
- Quantum models (moved to /research/)
- Defense models (moved to /research/)
================================================================================
"""

import math
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import json


# ============================================================================
# ENUMS FOR PHASE 1
# ============================================================================

class EnergySector(str, Enum):
    """Phase 1 allowed energy sectors"""
    RENEWABLES = "renewables"
    GRID_STORAGE = "grid_storage"


class GridStatus(str, Enum):
    """Grid operational status"""
    STABLE = "stable"
    WARNING = "warning"
    UNSTABLE = "unstable"
    CRITICAL = "critical"


class ControlAction(str, Enum):
    """AECE control actions"""
    NO_ACTION = "no_action"
    REDUCE_LOAD = "reduce_load"
    REDISTRIBUTE_ENERGY = "redistribute_energy"
    DISPATCH_BATTERY = "dispatch_battery"
    CHARGE_BATTERY = "charge_battery"
    SOLAR_REDIRECTION = "solar_redirection"
    TRIGGER_ALERT = "trigger_alert"


class RiskLevel(str, Enum):
    """Risk assessment levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# TELEMETRY MODELS
# ============================================================================

@dataclass
class TelemetryData:
    """
    Real-time telemetry from hardware (Modbus/Simulated)
    Phase 1: Solar and Grid metrics only
    """
    timestamp: float = field(default_factory=time.time)
    
    # Grid metrics
    grid_frequency_hz: float = 50.0
    grid_voltage_v: float = 230.0
    grid_current_a: float = 0.0
    active_power_kw: float = 0.0
    reactive_power_kvar: float = 0.0
    
    # Solar metrics
    solar_output_kw: float = 0.0
    solar_voltage_v: float = 400.0
    solar_current_a: float = 0.0
    solar_efficiency_percent: float = 0.0
    
    # Battery metrics (if available)
    battery_soc_percent: float = 50.0
    battery_power_kw: float = 0.0
    battery_temperature_c: float = 25.0
    
    # Environmental
    ambient_temperature_c: float = 25.0
    irradiance_wm2: float = 0.0
    
    # Quality indicators
    data_quality_score: float = 1.0
    data_source: str = "SIMULATED"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "grid": {
                "frequency_hz": round(self.grid_frequency_hz, 2),
                "voltage_v": round(self.grid_voltage_v, 1),
                "current_a": round(self.grid_current_a, 1),
                "active_power_kw": round(self.active_power_kw, 1),
                "reactive_power_kvar": round(self.reactive_power_kvar, 1)
            },
            "solar": {
                "output_kw": round(self.solar_output_kw, 1),
                "voltage_v": round(self.solar_voltage_v, 1),
                "current_a": round(self.solar_current_a, 1),
                "efficiency_percent": round(self.solar_efficiency_percent, 1)
            },
            "battery": {
                "soc_percent": round(self.battery_soc_percent, 1),
                "power_kw": round(self.battery_power_kw, 1),
                "temperature_c": round(self.battery_temperature_c, 1)
            },
            "environmental": {
                "temperature_c": round(self.ambient_temperature_c, 1),
                "irradiance_wm2": round(self.irradiance_wm2, 1)
            },
            "quality": {
                "data_quality_score": round(self.data_quality_score, 3),
                "data_source": self.data_source
            }
        }
    
    def is_valid(self) -> bool:
        """Validate telemetry data ranges"""
        valid = True
        
        # Grid frequency range (49.0 - 51.0 Hz)
        if not (49.0 <= self.grid_frequency_hz <= 51.0):
            valid = False
        
        # Grid voltage range (207 - 253 V for 230V nominal)
        if not (207 <= self.grid_voltage_v <= 253):
            valid = False
        
        # Solar efficiency range
        if not (0 <= self.solar_efficiency_percent <= 100):
            valid = False
        
        # Battery SOC range
        if not (0 <= self.battery_soc_percent <= 100):
            valid = False
        
        return valid


@dataclass
class SolarForecast:
    """
    Solar generation forecast
    Based on irradiance, weather, and time of day
    """
    timestamp: float = field(default_factory=time.time)
    forecast_hours: int = 24
    
    # Hourly predictions
    hourly_predictions_kwh: List[float] = field(default_factory=list)
    confidence_intervals: List[Tuple[float, float]] = field(default_factory=list)
    
    # Aggregated metrics
    total_daily_kwh: float = 0.0
    peak_hour: int = 0
    peak_power_kw: float = 0.0
    
    # Metadata
    weather_confidence: float = 0.85
    model_version: str = "2.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert forecast to dictionary"""
        hourly_data = []
        for i in range(min(len(self.hourly_predictions_kwh), self.forecast_hours)):
            hour_data = {
                "hour": i,
                "predicted_kwh": round(self.hourly_predictions_kwh[i], 2)
            }
            if i < len(self.confidence_intervals):
                hour_data["confidence_lower"] = round(self.confidence_intervals[i][0], 2)
                hour_data["confidence_upper"] = round(self.confidence_intervals[i][1], 2)
            hourly_data.append(hour_data)
        
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "forecast_hours": self.forecast_hours,
            "total_daily_kwh": round(self.total_daily_kwh, 1),
            "peak_hour": self.peak_hour,
            "peak_power_kw": round(self.peak_power_kw, 1),
            "weather_confidence": round(self.weather_confidence, 3),
            "hourly_forecast": hourly_data,
            "model_version": self.model_version
        }


@dataclass
class GridStabilityMetrics:
    """
    Grid stability calculation results
    """
    timestamp: float = field(default_factory=time.time)
    
    # Core metrics
    stability_score: float = 100.0  # 0-100, higher is better
    risk_score: float = 0.0  # 0-1, higher is riskier
    risk_level: RiskLevel = RiskLevel.LOW
    
    # Frequency metrics
    frequency_deviation_hz: float = 0.0
    frequency_quality_score: float = 100.0
    
    # Load metrics
    load_supply_imbalance_percent: float = 0.0
    demand_coverage_ratio: float = 1.0
    
    # Solar metrics
    solar_penetration_percent: float = 0.0
    solar_ramp_rate_kw_per_min: float = 0.0
    
    # Grid status
    status: GridStatus = GridStatus.STABLE
    alerts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "stability_score": round(self.stability_score, 1),
            "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "frequency": {
                "deviation_hz": round(self.frequency_deviation_hz, 3),
                "quality_score": round(self.frequency_quality_score, 1)
            },
            "load": {
                "imbalance_percent": round(self.load_supply_imbalance_percent, 1),
                "demand_coverage_ratio": round(self.demand_coverage_ratio, 3)
            },
            "solar": {
                "penetration_percent": round(self.solar_penetration_percent, 1),
                "ramp_rate_kw_per_min": round(self.solar_ramp_rate_kw_per_min, 2)
            },
            "alerts": self.alerts
        }


# ============================================================================
# OPTIMIZATION MODELS
# ============================================================================

@dataclass
class OptimizationMetrics:
    """
    Single source of truth for energy optimization
    """
    timestamp: float = field(default_factory=time.time)
    
    # Core optimization scores
    grid_stability_score: float = 100.0  # 0-100
    solar_efficiency_score: float = 100.0  # 0-100
    optimization_score: float = 100.0  # Weighted combination
    composite_risk_score: float = 0.0  # 0-1
    
    # Historical tracking
    previous_grid_score: Optional[float] = None
    previous_solar_score: Optional[float] = None
    previous_optimization_score: Optional[float] = None
    
    # Improvement tracking
    grid_improvement: float = 0.0
    solar_improvement: float = 0.0
    overall_improvement: float = 0.0
    
    # Action tracking
    last_action_id: Optional[str] = None
    last_action_type: Optional[str] = None
    actions_taken_count: int = 0
    successful_actions: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API"""
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "current": {
                "grid_stability": round(self.grid_stability_score, 1),
                "solar_efficiency": round(self.solar_efficiency_score, 1),
                "optimization": round(self.optimization_score, 1),
                "risk": round(self.composite_risk_score, 3)
            },
            "improvement": {
                "grid": round(self.grid_improvement, 1),
                "solar": round(self.solar_improvement, 1),
                "overall": round(self.overall_improvement, 1)
            },
            "actions": {
                "total": self.actions_taken_count,
                "successful": self.successful_actions,
                "success_rate": round(self.successful_actions / max(self.actions_taken_count, 1) * 100, 1),
                "last_action": {
                    "id": self.last_action_id,
                    "type": self.last_action_type
                } if self.last_action_id else None
            }
        }


@dataclass
class OptimizationDecision:
    """
    AECE decision record with impact tracking
    """
    decision_id: str
    action: ControlAction
    priority: str
    risk_level: RiskLevel
    risk_score_before: float
    reasoning: str
    expected_impact: Dict[str, float]
    triggered_rules: List[str]
    timestamp: float = field(default_factory=time.time)
    
    # Impact tracking (filled after execution)
    executed: bool = False
    execution_success: bool = False
    actual_impact: Dict[str, float] = field(default_factory=dict)
    execution_duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "decision_id": self.decision_id,
            "action": self.action.value,
            "priority": self.priority,
            "risk_level": self.risk_level.value,
            "risk_score_before": round(self.risk_score_before, 3),
            "reasoning": self.reasoning,
            "expected_impact": self.expected_impact,
            "triggered_rules": self.triggered_rules,
            "executed": self.executed,
            "execution_success": self.execution_success,
            "actual_impact": self.actual_impact,
            "execution_duration_ms": round(self.execution_duration_ms, 2),
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()
        }


@dataclass
class OptimizationReport:
    """
    Comprehensive optimization report
    """
    report_id: str
    generated_at: float = field(default_factory=time.time)
    period_start: Optional[float] = None
    period_end: Optional[float] = None
    
    # Summary metrics
    average_grid_stability: float = 0.0
    average_solar_efficiency: float = 0.0
    average_optimization_score: float = 0.0
    total_optimization_gain: float = 0.0
    
    # Action statistics
    total_actions: int = 0
    successful_actions: int = 0
    actions_by_type: Dict[str, int] = field(default_factory=dict)
    
    # Risk statistics
    risk_distribution: Dict[str, int] = field(default_factory=dict)
    critical_events: int = 0
    
    # Detailed entries
    decision_log: List[OptimizationDecision] = field(default_factory=list)
    metric_history: List[OptimizationMetrics] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "report_id": self.report_id,
            "generated_at": datetime.fromtimestamp(self.generated_at, tz=timezone.utc).isoformat(),
            "period_start": datetime.fromtimestamp(self.period_start, tz=timezone.utc).isoformat() if self.period_start else None,
            "period_end": datetime.fromtimestamp(self.period_end, tz=timezone.utc).isoformat() if self.period_end else None,
            "summary": {
                "average_grid_stability": round(self.average_grid_stability, 1),
                "average_solar_efficiency": round(self.average_solar_efficiency, 1),
                "average_optimization_score": round(self.average_optimization_score, 1),
                "total_optimization_gain": round(self.total_optimization_gain, 1)
            },
            "actions": {
                "total": self.total_actions,
                "successful": self.successful_actions,
                "success_rate": round(self.successful_actions / max(self.total_actions, 1) * 100, 1),
                "by_type": self.actions_by_type
            },
            "risk": {
                "distribution": self.risk_distribution,
                "critical_events": self.critical_events
            },
            "recent_decisions": [d.to_dict() for d in self.decision_log[-10:]],
            "phase": "PHASE_1_PRODUCTION"
        }


# ============================================================================
# PREDICTION MODELS
# ============================================================================

@dataclass
class EnergyPrediction:
    """
    Energy prediction for load and generation
    """
    timestamp: float = field(default_factory=time.time)
    prediction_horizon_hours: int = 24
    
    # Load predictions
    load_forecast_kw: List[float] = field(default_factory=list)
    load_confidence_lower: List[float] = field(default_factory=list)
    load_confidence_upper: List[float] = field(default_factory=list)
    
    # Solar predictions
    solar_forecast_kw: List[float] = field(default_factory=list)
    solar_confidence_lower: List[float] = field(default_factory=list)
    solar_confidence_upper: List[float] = field(default_factory=list)
    
    # Grid stability predictions
    stability_forecast: List[float] = field(default_factory=list)
    risk_forecast: List[float] = field(default_factory=list)
    
    # Peak predictions
    peak_load_hour: int = 0
    peak_load_kw: float = 0.0
    peak_solar_hour: int = 0
    peak_solar_kw: float = 0.0
    
    # Metadata
    model_version: str = "2.0.0"
    prediction_quality: float = 0.85
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        hourly_predictions = []
        for i in range(min(len(self.load_forecast_kw), self.prediction_horizon_hours)):
            hour_data = {
                "hour": i,
                "timestamp": (datetime.fromtimestamp(self.timestamp, tz=timezone.utc) + timedelta(hours=i)).isoformat(),
                "load_kw": round(self.load_forecast_kw[i], 1) if i < len(self.load_forecast_kw) else 0,
                "solar_kw": round(self.solar_forecast_kw[i], 1) if i < len(self.solar_forecast_kw) else 0,
                "stability_score": round(self.stability_forecast[i], 1) if i < len(self.stability_forecast) else 0,
                "risk_score": round(self.risk_forecast[i], 3) if i < len(self.risk_forecast) else 0
            }
            if i < len(self.load_confidence_lower):
                hour_data["load_confidence"] = {
                    "lower": round(self.load_confidence_lower[i], 1),
                    "upper": round(self.load_confidence_upper[i], 1)
                }
            if i < len(self.solar_confidence_lower):
                hour_data["solar_confidence"] = {
                    "lower": round(self.solar_confidence_lower[i], 1),
                    "upper": round(self.solar_confidence_upper[i], 1)
                }
            hourly_predictions.append(hour_data)
        
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "prediction_horizon_hours": self.prediction_horizon_hours,
            "peak_load": {
                "hour": self.peak_load_hour,
                "kw": round(self.peak_load_kw, 1)
            },
            "peak_solar": {
                "hour": self.peak_solar_hour,
                "kw": round(self.peak_solar_kw, 1)
            },
            "hourly_predictions": hourly_predictions,
            "model_version": self.model_version,
            "prediction_quality": round(self.prediction_quality, 3)
        }


# ============================================================================
# ALERT MODELS
# ============================================================================

@dataclass
class EnergyAlert:
    """
    Alert generated by AECE or monitoring system
    """
    alert_id: str
    severity: str  # info, warning, error, critical
    title: str
    message: str
    source: str  # AECE, MONITORING, PREDICTION
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved: bool = False
    resolution_timestamp: Optional[float] = None
    resolution_note: Optional[str] = None
    
    # Context data
    related_metrics: Dict[str, Any] = field(default_factory=dict)
    related_decision_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "resolution_timestamp": datetime.fromtimestamp(self.resolution_timestamp, tz=timezone.utc).isoformat() if self.resolution_timestamp else None,
            "resolution_note": self.resolution_note,
            "related_decision_id": self.related_decision_id
        }


# ============================================================================
# SIMULATION MODELS
# ============================================================================

@dataclass
class SimulationConfig:
    """
    Configuration for energy simulation
    """
    simulation_id: str
    sector: EnergySector = EnergySector.RENEWABLES
    duration_seconds: int = 3600
    time_step_seconds: int = 60
    
    # Initial conditions
    initial_load_kw: float = 500.0
    initial_solar_kw: float = 100.0
    initial_battery_soc: float = 50.0
    initial_grid_frequency: float = 50.0
    
    # Parameters
    load_variance: float = 0.1
    solar_variance: float = 0.15
    fault_probability: float = 0.001
    
    # Simulation mode
    use_quantum_kernel: bool = False
    enable_fault_injection: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "simulation_id": self.simulation_id,
            "sector": self.sector.value,
            "duration_seconds": self.duration_seconds,
            "time_step_seconds": self.time_step_seconds,
            "initial_conditions": {
                "load_kw": round(self.initial_load_kw, 1),
                "solar_kw": round(self.initial_solar_kw, 1),
                "battery_soc_percent": round(self.initial_battery_soc, 1),
                "grid_frequency_hz": round(self.initial_grid_frequency, 2)
            },
            "parameters": {
                "load_variance": self.load_variance,
                "solar_variance": self.solar_variance,
                "fault_probability": self.fault_probability
            },
            "features": {
                "use_quantum_kernel": self.use_quantum_kernel,
                "enable_fault_injection": self.enable_fault_injection
            }
        }


@dataclass
class SimulationResult:
    """
    Result of an energy simulation
    """
    simulation_id: str
    status: str  # running, completed, failed
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    # Time series data
    timestamps: List[float] = field(default_factory=list)
    load_values: List[float] = field(default_factory=list)
    solar_values: List[float] = field(default_factory=list)
    grid_frequency_values: List[float] = field(default_factory=list)
    battery_soc_values: List[float] = field(default_factory=list)
    
    # Statistics
    total_energy_kwh: float = 0.0
    average_grid_frequency: float = 50.0
    min_grid_frequency: float = 50.0
    max_grid_frequency: float = 50.0
    total_faults: int = 0
    
    # AECE decisions during simulation
    decisions_taken: List[OptimizationDecision] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        # Limit time series to last 100 points for API response
        max_points = 100
        step = max(1, len(self.timestamps) // max_points) if len(self.timestamps) > max_points else 1
        
        time_series = []
        for i in range(0, len(self.timestamps), step):
            time_series.append({
                "timestamp": datetime.fromtimestamp(self.timestamps[i], tz=timezone.utc).isoformat(),
                "load_kw": round(self.load_values[i], 1) if i < len(self.load_values) else 0,
                "solar_kw": round(self.solar_values[i], 1) if i < len(self.solar_values) else 0,
                "grid_frequency_hz": round(self.grid_frequency_values[i], 2) if i < len(self.grid_frequency_values) else 50.0,
                "battery_soc_percent": round(self.battery_soc_values[i], 1) if i < len(self.battery_soc_values) else 50.0
            })
        
        return {
            "simulation_id": self.simulation_id,
            "status": self.status,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "duration_seconds": round(self.end_time - self.start_time, 2) if self.end_time else 0,
            "statistics": {
                "total_energy_kwh": round(self.total_energy_kwh, 1),
                "average_grid_frequency_hz": round(self.average_grid_frequency, 2),
                "min_grid_frequency_hz": round(self.min_grid_frequency, 2),
                "max_grid_frequency_hz": round(self.max_grid_frequency, 2),
                "total_faults": self.total_faults
            },
            "time_series": time_series,
            "decisions_taken": len(self.decisions_taken),
            "phase": "PHASE_1_PRODUCTION"
        }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def calculate_optimization_score(grid_stability: float, solar_efficiency: float, grid_weight: float = 0.6) -> float:
    """
    Calculate unified optimization score from component scores
    
    Args:
        grid_stability: Grid stability score (0-100)
        solar_efficiency: Solar efficiency score (0-100)
        grid_weight: Weight for grid stability (0-1), solar weight = 1 - grid_weight
    
    Returns:
        Optimization score (0-100)
    """
    solar_weight = 1.0 - grid_weight
    return (grid_stability * grid_weight) + (solar_efficiency * solar_weight)


def calculate_risk_score_from_metrics(
    grid_stability: float,
    solar_efficiency: float,
    demand_load_ratio: float = 0.5
) -> float:
    """
    Calculate risk score from metrics
    
    Args:
        grid_stability: Grid stability score (0-100)
        solar_efficiency: Solar efficiency score (0-100)
        demand_load_ratio: Current demand / capacity ratio (0-1)
    
    Returns:
        Risk score (0-1)
    """
    # Normalize scores
    grid_risk = (100 - grid_stability) / 100
    solar_risk = (100 - solar_efficiency) / 100
    
    # Weighted combination
    composite_risk = (grid_risk * 0.6) + (solar_risk * 0.2) + (demand_load_ratio * 0.2)
    
    return min(1.0, max(0.0, composite_risk))


def get_risk_level_from_score(risk_score: float) -> RiskLevel:
    """
    Get risk level from numeric risk score
    
    Args:
        risk_score: Risk score between 0 and 1
    
    Returns:
        RiskLevel enum value
    """
    if risk_score >= 0.85:
        return RiskLevel.CRITICAL
    elif risk_score >= 0.65:
        return RiskLevel.HIGH
    elif risk_score >= 0.35:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW


def get_grid_status_from_stability(stability_score: float) -> GridStatus:
    """
    Get grid status from stability score
    
    Args:
        stability_score: Grid stability score (0-100)
    
    Returns:
        GridStatus enum value
    """
    if stability_score >= 90:
        return GridStatus.STABLE
    elif stability_score >= 70:
        return GridStatus.WARNING
    elif stability_score >= 50:
        return GridStatus.UNSTABLE
    else:
        return GridStatus.CRITICAL


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    'EnergySector',
    'GridStatus',
    'ControlAction',
    'RiskLevel',
    
    # Telemetry Models
    'TelemetryData',
    'SolarForecast',
    'GridStabilityMetrics',
    
    # Optimization Models
    'OptimizationMetrics',
    'OptimizationDecision',
    'OptimizationReport',
    
    # Prediction Models
    'EnergyPrediction',
    
    # Alert Models
    'EnergyAlert',
    
    # Simulation Models
    'SimulationConfig',
    'SimulationResult',
    
    # Utility Functions
    'calculate_optimization_score',
    'calculate_risk_score_from_metrics',
    'get_risk_level_from_score',
    'get_grid_status_from_stability',
]

# ============================================================================
# CONTINUATION - ADDITIONAL ENERGY MODELS
# ============================================================================

@dataclass
class EnergySystemState:
    """
    Complete energy system state snapshot
    Used for AECE decision making and optimization
    """
    timestamp: float = field(default_factory=time.time)
    
    # Grid state
    grid_frequency_hz: float = 50.0
    grid_voltage_v: float = 230.0
    grid_frequency_deviation: float = 0.0
    grid_quality_score: float = 100.0
    
    # Load state
    total_load_kw: float = 0.0
    peak_load_kw: float = 0.0
    load_trend: str = "stable"  # increasing, decreasing, stable
    
    # Generation state
    total_generation_kw: float = 0.0
    solar_generation_kw: float = 0.0
    battery_power_kw: float = 0.0
    generation_mix: Dict[str, float] = field(default_factory=dict)
    
    # Balance metrics
    supply_demand_balance_kw: float = 0.0
    balance_percent: float = 100.0
    deficit_alert: bool = False
    surplus_alert: bool = False
    
    # Stability indicators
    voltage_stability_index: float = 1.0
    frequency_stability_index: float = 1.0
    overall_stability_index: float = 1.0
    
    # AECE state
    protection_mode_active: bool = False
    last_action_timestamp: Optional[float] = None
    pending_decisions: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API"""
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "grid": {
                "frequency_hz": round(self.grid_frequency_hz, 2),
                "voltage_v": round(self.grid_voltage_v, 1),
                "frequency_deviation_hz": round(self.grid_frequency_deviation, 3),
                "quality_score": round(self.grid_quality_score, 1)
            },
            "load": {
                "total_kw": round(self.total_load_kw, 1),
                "peak_kw": round(self.peak_load_kw, 1),
                "trend": self.load_trend
            },
            "generation": {
                "total_kw": round(self.total_generation_kw, 1),
                "solar_kw": round(self.solar_generation_kw, 1),
                "battery_kw": round(self.battery_power_kw, 1),
                "mix": self.generation_mix
            },
            "balance": {
                "supply_demand_balance_kw": round(self.supply_demand_balance_kw, 1),
                "balance_percent": round(self.balance_percent, 1),
                "deficit_alert": self.deficit_alert,
                "surplus_alert": self.surplus_alert
            },
            "stability": {
                "voltage_index": round(self.voltage_stability_index, 3),
                "frequency_index": round(self.frequency_stability_index, 3),
                "overall_index": round(self.overall_stability_index, 3)
            },
            "aece": {
                "protection_mode_active": self.protection_mode_active,
                "last_action_timestamp": datetime.fromtimestamp(self.last_action_timestamp, tz=timezone.utc).isoformat() if self.last_action_timestamp else None,
                "pending_decisions": self.pending_decisions
            }
        }
    
    def calculate_stability_index(self) -> float:
        """
        Calculate overall stability index based on current metrics
        Returns value between 0 and 1 (1 = perfect stability)
        """
        # Frequency component (50Hz nominal)
        freq_quality = 1.0 - min(0.5, abs(self.grid_frequency_hz - 50.0) / 2.0)
        
        # Voltage component (230V nominal)
        voltage_quality = 1.0 - min(0.5, abs(self.grid_voltage_v - 230.0) / 46.0)
        
        # Balance component
        balance_quality = self.balance_percent / 100.0
        
        # Weighted average
        self.voltage_stability_index = voltage_quality
        self.frequency_stability_index = freq_quality
        self.overall_stability_index = (freq_quality * 0.4 + voltage_quality * 0.3 + balance_quality * 0.3)
        
        return self.overall_stability_index


@dataclass
class BatteryState:
    """
    Battery Energy Storage System (BESS) state
    Phase 1: Simulated battery for grid stabilization
    """
    timestamp: float = field(default_factory=time.time)
    battery_id: str = "default"
    
    # Core metrics
    state_of_charge_percent: float = 50.0
    state_of_health_percent: float = 95.0
    power_kw: float = 0.0  # Positive = discharge, Negative = charge
    energy_kwh: float = 0.0
    capacity_kwh: float = 100.0
    
    # Thermal metrics
    temperature_c: float = 25.0
    max_temperature_c: float = 45.0
    thermal_warning: bool = False
    
    # Operational limits
    max_charge_power_kw: float = 50.0
    max_discharge_power_kw: float = 50.0
    min_soc_percent: float = 10.0
    max_soc_percent: float = 90.0
    
    # Status flags
    charging: bool = False
    discharging: bool = False
    idle: bool = True
    fault: bool = False
    fault_code: Optional[str] = None
    
    # Cycle tracking
    cycle_count: int = 0
    total_energy_charged_kwh: float = 0.0
    total_energy_discharged_kwh: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "battery_id": self.battery_id,
            "state": {
                "soc_percent": round(self.state_of_charge_percent, 1),
                "soh_percent": round(self.state_of_health_percent, 1),
                "power_kw": round(self.power_kw, 1),
                "energy_kwh": round(self.energy_kwh, 1),
                "capacity_kwh": round(self.capacity_kwh, 1)
            },
            "thermal": {
                "temperature_c": round(self.temperature_c, 1),
                "max_temperature_c": round(self.max_temperature_c, 1),
                "thermal_warning": self.thermal_warning
            },
            "limits": {
                "max_charge_kw": round(self.max_charge_power_kw, 1),
                "max_discharge_kw": round(self.max_discharge_power_kw, 1),
                "min_soc_percent": self.min_soc_percent,
                "max_soc_percent": self.max_soc_percent
            },
            "status": {
                "charging": self.charging,
                "discharging": self.discharging,
                "idle": self.idle,
                "fault": self.fault,
                "fault_code": self.fault_code
            },
            "cycles": {
                "cycle_count": self.cycle_count,
                "total_charged_kwh": round(self.total_energy_charged_kwh, 1),
                "total_discharged_kwh": round(self.total_energy_discharged_kwh, 1)
            }
        }
    
    def can_charge(self, power_kw: float) -> bool:
        """Check if battery can accept charge"""
        if self.fault:
            return False
        if self.state_of_charge_percent >= self.max_soc_percent:
            return False
        if power_kw > self.max_charge_power_kw:
            return False
        if self.temperature_c > self.max_temperature_c - 5:
            return False
        return True
    
    def can_discharge(self, power_kw: float) -> bool:
        """Check if battery can discharge"""
        if self.fault:
            return False
        if self.state_of_charge_percent <= self.min_soc_percent:
            return False
        if power_kw > self.max_discharge_power_kw:
            return False
        if self.temperature_c > self.max_temperature_c - 5:
            return False
        return True


@dataclass
class InverterState:
    """
    Solar inverter state and telemetry
    Phase 1: For solar optimization
    """
    timestamp: float = field(default_factory=time.time)
    inverter_id: str = "default"
    
    # Electrical metrics
    dc_voltage_v: float = 400.0
    dc_current_a: float = 0.0
    ac_voltage_v: float = 230.0
    ac_current_a: float = 0.0
    ac_power_kw: float = 0.0
    ac_frequency_hz: float = 50.0
    
    # Efficiency
    efficiency_percent: float = 95.0
    power_factor: float = 0.95
    
    # Thermal
    temperature_c: float = 45.0
    heatsink_temperature_c: float = 50.0
    
    # Status
    status: str = "online"  # online, offline, fault, derating
    fault_code: Optional[str] = None
    derating_percent: float = 0.0
    
    # Production
    daily_production_kwh: float = 0.0
    monthly_production_kwh: float = 0.0
    total_production_kwh: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "inverter_id": self.inverter_id,
            "dc": {
                "voltage_v": round(self.dc_voltage_v, 1),
                "current_a": round(self.dc_current_a, 1)
            },
            "ac": {
                "voltage_v": round(self.ac_voltage_v, 1),
                "current_a": round(self.ac_current_a, 1),
                "power_kw": round(self.ac_power_kw, 1),
                "frequency_hz": round(self.ac_frequency_hz, 2)
            },
            "performance": {
                "efficiency_percent": round(self.efficiency_percent, 1),
                "power_factor": round(self.power_factor, 3)
            },
            "thermal": {
                "temperature_c": round(self.temperature_c, 1),
                "heatsink_temperature_c": round(self.heatsink_temperature_c, 1)
            },
            "status": {
                "state": self.status,
                "fault_code": self.fault_code,
                "derating_percent": round(self.derating_percent, 1)
            },
            "production": {
                "daily_kwh": round(self.daily_production_kwh, 1),
                "monthly_kwh": round(self.monthly_production_kwh, 1),
                "total_kwh": round(self.total_production_kwh, 1)
            }
        }
    
    def calculate_efficiency(self) -> float:
        """
        Calculate AC to DC efficiency ratio
        """
        if self.dc_power_kw > 0:
            self.efficiency_percent = (self.ac_power_kw / self.dc_power_kw) * 100
        else:
            self.efficiency_percent = 0.0
        return self.efficiency_percent


@dataclass
class WeatherImpact:
    """
    Weather impact assessment on solar generation
    """
    timestamp: float = field(default_factory=time.time)
    location_lat: float = 9.0765
    location_lon: float = 7.3986
    
    # Weather conditions
    temperature_c: float = 25.0
    irradiance_wm2: float = 850.0
    cloud_cover_percent: float = 25.0
    wind_speed_ms: float = 3.0
    humidity_percent: float = 55.0
    
    # Impact metrics
    solar_efficiency_impact: float = 1.0  # 0-1 multiplier
    expected_generation_kw: float = 0.0
    actual_generation_kw: float = 0.0
    generation_loss_percent: float = 0.0
    
    # Forecasting
    forecast_hours: List[int] = field(default_factory=list)
    forecast_irradiance: List[float] = field(default_factory=list)
    forecast_efficiency: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        forecast_data = []
        for i in range(min(len(self.forecast_hours), 24)):
            forecast_data.append({
                "hour": self.forecast_hours[i],
                "irradiance_wm2": round(self.forecast_irradiance[i], 1) if i < len(self.forecast_irradiance) else 0,
                "efficiency_multiplier": round(self.forecast_efficiency[i], 3) if i < len(self.forecast_efficiency) else 1.0
            })
        
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "location": {
                "lat": self.location_lat,
                "lon": self.location_lon
            },
            "current": {
                "temperature_c": round(self.temperature_c, 1),
                "irradiance_wm2": round(self.irradiance_wm2, 1),
                "cloud_cover_percent": round(self.cloud_cover_percent, 1),
                "wind_speed_ms": round(self.wind_speed_ms, 1),
                "humidity_percent": round(self.humidity_percent, 1)
            },
            "impact": {
                "solar_efficiency_impact": round(self.solar_efficiency_impact, 3),
                "expected_generation_kw": round(self.expected_generation_kw, 1),
                "actual_generation_kw": round(self.actual_generation_kw, 1),
                "generation_loss_percent": round(self.generation_loss_percent, 1)
            },
            "forecast": forecast_data
        }
    
    def calculate_efficiency_impact(self) -> float:
        """
        Calculate solar efficiency impact based on weather conditions
        Returns multiplier between 0 and 1
        """
        impact = 1.0
        
        # Temperature impact (PV cells lose efficiency above 25°C)
        if self.temperature_c > 25:
            temp_impact = 1.0 - ((self.temperature_c - 25) * 0.004)
            impact *= max(0.5, temp_impact)
        
        # Cloud cover impact
        cloud_impact = 1.0 - (self.cloud_cover_percent / 100.0)
        impact *= max(0.1, cloud_impact)
        
        # Irradiance impact (relative to STC 1000 W/m²)
        irradiance_impact = min(1.0, self.irradiance_wm2 / 1000.0)
        impact *= irradiance_impact
        
        self.solar_efficiency_impact = max(0.0, min(1.0, impact))
        return self.solar_efficiency_impact


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_telemetry(telemetry: TelemetryData) -> Tuple[bool, List[str]]:
    """
    Validate telemetry data and return validation results
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check frequency range
    if not (49.0 <= telemetry.grid_frequency_hz <= 51.0):
        errors.append(f"Grid frequency out of range: {telemetry.grid_frequency_hz} Hz")
    
    # Check voltage range
    if not (207 <= telemetry.grid_voltage_v <= 253):
        errors.append(f"Grid voltage out of range: {telemetry.grid_voltage_v} V")
    
    # Check solar output (can't exceed max theoretical)
    max_solar_kw = telemetry.irradiance_wm2 / 1000.0 * 100  # Simplified
    if telemetry.solar_output_kw > max_solar_kw + 10:
        errors.append(f"Solar output exceeds theoretical maximum: {telemetry.solar_output_kw} kW")
    
    # Check battery SOC
    if not (0 <= telemetry.battery_soc_percent <= 100):
        errors.append(f"Battery SOC out of range: {telemetry.battery_soc_percent}%")
    
    # Check data quality
    if telemetry.data_quality_score < 0.5:
        errors.append(f"Data quality too low: {telemetry.data_quality_score}")
    
    return len(errors) == 0, errors


def validate_optimization_metrics(metrics: OptimizationMetrics) -> Tuple[bool, List[str]]:
    """
    Validate optimization metrics ranges
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if not (0 <= metrics.grid_stability_score <= 100):
        errors.append(f"Grid stability score out of range: {metrics.grid_stability_score}")
    
    if not (0 <= metrics.solar_efficiency_score <= 100):
        errors.append(f"Solar efficiency score out of range: {metrics.solar_efficiency_score}")
    
    if not (0 <= metrics.optimization_score <= 100):
        errors.append(f"Optimization score out of range: {metrics.optimization_score}")
    
    if not (0 <= metrics.composite_risk_score <= 1):
        errors.append(f"Risk score out of range: {metrics.composite_risk_score}")
    
    return len(errors) == 0, errors


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_empty_telemetry() -> TelemetryData:
    """Create empty telemetry with default values"""
    return TelemetryData(
        timestamp=time.time(),
        grid_frequency_hz=50.0,
        grid_voltage_v=230.0,
        active_power_kw=0.0,
        solar_output_kw=0.0,
        battery_soc_percent=50.0,
        irradiance_wm2=0.0,
        data_source="EMPTY"
    )


def create_optimization_metrics_from_telemetry(
    telemetry: TelemetryData,
    expected_solar_kw: float = 100.0
) -> OptimizationMetrics:
    """
    Create optimization metrics from telemetry data
    """
    from backend.core.optimization_metrics import get_metrics_engine
    
    metrics_engine = get_metrics_engine()
    
    snapshot = metrics_engine.capture_snapshot(
        active_power_kw=telemetry.active_power_kw,
        grid_frequency_hz=telemetry.grid_frequency_hz,
        demand_load_kw=telemetry.active_power_kw,  # Simplified
        solar_output_kw=telemetry.solar_output_kw,
        expected_solar_kw=expected_solar_kw,
        voltage_v=telemetry.grid_voltage_v,
        irradiance_wm2=telemetry.irradiance_wm2,
        temperature_c=telemetry.ambient_temperature_c
    )
    
    return OptimizationMetrics(
        timestamp=snapshot.timestamp,
        grid_stability_score=snapshot.grid_stability_score,
        solar_efficiency_score=snapshot.solar_efficiency_score,
        optimization_score=snapshot.optimization_score,
        composite_risk_score=snapshot.risk_score
    )


# ============================================================================
# EXPORTS (ADDITIONAL)
# ============================================================================

__all__.extend([
    # Additional models
    'EnergySystemState',
    'BatteryState',
    'InverterState',
    'WeatherImpact',
    
    # Validation functions
    'validate_telemetry',
    'validate_optimization_metrics',
    
    # Factory functions
    'create_empty_telemetry',
    'create_optimization_metrics_from_telemetry',
])

# ============================================================================
# CONTINUATION - COMPLETE ENERGY MODELS
# ============================================================================

# ============================================================================
# LOAD PROFILE MODELS
# ============================================================================

@dataclass
class LoadProfile:
    """
    Load profile for demand forecasting and analysis
    Phase 1: For grid stability and load balancing
    """
    profile_id: str
    timestamp: float = field(default_factory=time.time)
    
    # Time series data
    timestamps: List[float] = field(default_factory=list)
    load_values_kw: List[float] = field(default_factory=list)
    
    # Statistical metrics
    average_load_kw: float = 0.0
    peak_load_kw: float = 0.0
    min_load_kw: float = 0.0
    load_factor: float = 0.0  # average/peak ratio
    load_variance: float = 0.0
    
    # Temporal characteristics
    peak_hour: int = 0
    off_peak_hour: int = 0
    morning_ramp_rate_kw_per_min: float = 0.0
    evening_ramp_rate_kw_per_min: float = 0.0
    
    # Classification
    profile_type: str = "typical"  # residential, commercial, industrial, typical
    day_type: str = "weekday"  # weekday, weekend, holiday
    season: str = "summer"  # summer, winter, spring, autumn
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API"""
        # Sample time series for API response (max 96 points for 24h at 15min intervals)
        max_points = 96
        step = max(1, len(self.timestamps) // max_points) if len(self.timestamps) > max_points else 1
        
        time_series = []
        for i in range(0, len(self.timestamps), step):
            hour_of_day = datetime.fromtimestamp(self.timestamps[i], tz=timezone.utc).hour
            time_series.append({
                "hour": hour_of_day,
                "timestamp": datetime.fromtimestamp(self.timestamps[i], tz=timezone.utc).isoformat(),
                "load_kw": round(self.load_values_kw[i], 1) if i < len(self.load_values_kw) else 0
            })
        
        return {
            "profile_id": self.profile_id,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "statistics": {
                "average_kw": round(self.average_load_kw, 1),
                "peak_kw": round(self.peak_load_kw, 1),
                "min_kw": round(self.min_load_kw, 1),
                "load_factor": round(self.load_factor, 3),
                "variance": round(self.load_variance, 1)
            },
            "temporal": {
                "peak_hour": self.peak_hour,
                "off_peak_hour": self.off_peak_hour,
                "morning_ramp_rate_kw_per_min": round(self.morning_ramp_rate_kw_per_min, 2),
                "evening_ramp_rate_kw_per_min": round(self.evening_ramp_rate_kw_per_min, 2)
            },
            "classification": {
                "profile_type": self.profile_type,
                "day_type": self.day_type,
                "season": self.season
            },
            "time_series": time_series[:max_points]
        }
    
    def calculate_statistics(self) -> None:
        """Calculate statistical metrics from time series data"""
        if not self.load_values_kw:
            return
        
        self.average_load_kw = sum(self.load_values_kw) / len(self.load_values_kw)
        self.peak_load_kw = max(self.load_values_kw)
        self.min_load_kw = min(self.load_values_kw)
        self.load_factor = self.average_load_kw / self.peak_load_kw if self.peak_load_kw > 0 else 0
        
        # Calculate variance
        variance_sum = sum((x - self.average_load_kw) ** 2 for x in self.load_values_kw)
        self.load_variance = variance_sum / len(self.load_values_kw)
        
        # Find peak hour
        if self.timestamps:
            peak_index = self.load_values_kw.index(self.peak_load_kw)
            if peak_index < len(self.timestamps):
                self.peak_hour = datetime.fromtimestamp(self.timestamps[peak_index], tz=timezone.utc).hour


@dataclass
class DemandResponseEvent:
    """
    Demand response event for load management
    Phase 1: For grid stability during peak demand
    """
    event_id: str
    timestamp: float = field(default_factory=time.time)
    
    # Event details
    event_type: str = "load_shedding"  # load_shedding, load_shifting, peak_reduction
    priority: str = "normal"  # critical, high, normal, low
    status: str = "pending"  # pending, active, completed, cancelled, failed
    
    # Target specifications
    target_reduction_kw: float = 0.0
    actual_reduction_kw: float = 0.0
    target_duration_seconds: int = 3600
    actual_duration_seconds: int = 0
    
    # Timing
    scheduled_start: float = 0.0
    scheduled_end: float = 0.0
    actual_start: Optional[float] = None
    actual_end: Optional[float] = None
    
    # Participants
    affected_zones: List[str] = field(default_factory=list)
    affected_customers: int = 0
    
    # Results
    success: bool = False
    failure_reason: Optional[str] = None
    grid_improvement: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "event_id": self.event_id,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "event_type": self.event_type,
            "priority": self.priority,
            "status": self.status,
            "targets": {
                "reduction_kw": round(self.target_reduction_kw, 1),
                "actual_reduction_kw": round(self.actual_reduction_kw, 1),
                "duration_seconds": self.target_duration_seconds,
                "actual_duration_seconds": self.actual_duration_seconds
            },
            "timing": {
                "scheduled_start": datetime.fromtimestamp(self.scheduled_start, tz=timezone.utc).isoformat() if self.scheduled_start else None,
                "scheduled_end": datetime.fromtimestamp(self.scheduled_end, tz=timezone.utc).isoformat() if self.scheduled_end else None,
                "actual_start": datetime.fromtimestamp(self.actual_start, tz=timezone.utc).isoformat() if self.actual_start else None,
                "actual_end": datetime.fromtimestamp(self.actual_end, tz=timezone.utc).isoformat() if self.actual_end else None
            },
            "participants": {
                "affected_zones": self.affected_zones,
                "affected_customers": self.affected_customers
            },
            "results": {
                "success": self.success,
                "failure_reason": self.failure_reason,
                "grid_improvement": round(self.grid_improvement, 1)
            }
        }


# ============================================================================
# HISTORICAL DATA MODELS
# ============================================================================

@dataclass
class HistoricalDataPoint:
    """
    Single historical data point for trend analysis
    """
    timestamp: float
    metric_name: str
    metric_value: float
    unit: str
    source: str
    quality_score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "metric_name": self.metric_name,
            "metric_value": round(self.metric_value, 3),
            "unit": self.unit,
            "source": self.source,
            "quality_score": round(self.quality_score, 3)
        }


@dataclass
class HistoricalTrend:
    """
    Historical trend analysis for metrics
    """
    metric_name: str
    data_points: List[HistoricalDataPoint] = field(default_factory=list)
    
    # Trend analysis
    trend_direction: str = "stable"  # increasing, decreasing, stable
    trend_rate: float = 0.0  # change per hour
    volatility: float = 0.0  # standard deviation
    seasonality_factor: float = 0.0
    
    # Time-based aggregates
    daily_average: float = 0.0
    weekly_average: float = 0.0
    monthly_average: float = 0.0
    
    # Extremes
    max_value: float = 0.0
    min_value: float = 0.0
    max_timestamp: Optional[float] = None
    min_timestamp: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        # Sample data points for API
        max_points = 100
        step = max(1, len(self.data_points) // max_points) if len(self.data_points) > max_points else 1
        sampled_points = self.data_points[::step][:max_points]
        
        return {
            "metric_name": self.metric_name,
            "trend": {
                "direction": self.trend_direction,
                "rate_per_hour": round(self.trend_rate, 3),
                "volatility": round(self.volatility, 3),
                "seasonality_factor": round(self.seasonality_factor, 3)
            },
            "averages": {
                "daily": round(self.daily_average, 1),
                "weekly": round(self.weekly_average, 1),
                "monthly": round(self.monthly_average, 1)
            },
            "extremes": {
                "max_value": round(self.max_value, 1),
                "min_value": round(self.min_value, 1),
                "max_timestamp": datetime.fromtimestamp(self.max_timestamp, tz=timezone.utc).isoformat() if self.max_timestamp else None,
                "min_timestamp": datetime.fromtimestamp(self.min_timestamp, tz=timezone.utc).isoformat() if self.min_timestamp else None
            },
            "data_points": [p.to_dict() for p in sampled_points],
            "total_points": len(self.data_points)
        }
    
    def calculate_trend(self) -> None:
        """Calculate trend statistics from data points"""
        if len(self.data_points) < 2:
            return
        
        # Sort by timestamp
        sorted_points = sorted(self.data_points, key=lambda x: x.timestamp)
        
        # Extract values
        timestamps = [p.timestamp for p in sorted_points]
        values = [p.metric_value for p in sorted_points]
        
        # Calculate trend using linear regression
        n = len(timestamps)
        if n > 1:
            x_mean = sum(timestamps) / n
            y_mean = sum(values) / n
            
            numerator = sum((timestamps[i] - x_mean) * (values[i] - y_mean) for i in range(n))
            denominator = sum((timestamps[i] - x_mean) ** 2 for i in range(n))
            
            if denominator != 0:
                self.trend_rate = numerator / denominator * 3600  # per hour
            
            # Determine direction
            if self.trend_rate > 0.01:
                self.trend_direction = "increasing"
            elif self.trend_rate < -0.01:
                self.trend_direction = "decreasing"
            else:
                self.trend_direction = "stable"
        
        # Calculate volatility (standard deviation)
        if n > 1:
            variance = sum((v - y_mean) ** 2 for v in values) / n
            self.volatility = variance ** 0.5
        
        # Find extremes
        self.max_value = max(values)
        self.min_value = min(values)
        self.max_timestamp = timestamps[values.index(self.max_value)]
        self.min_timestamp = timestamps[values.index(self.min_value)]


# ============================================================================
# KPI AND PERFORMANCE MODELS
# ============================================================================

@dataclass
class KeyPerformanceIndicator:
    """
    Key Performance Indicator for energy system
    Phase 1: Solar and grid KPIs only
    """
    kpi_id: str
    name: str
    category: str  # solar, grid, optimization, reliability
    unit: str
    current_value: float = 0.0
    target_value: float = 100.0
    previous_value: float = 0.0
    improvement_percent: float = 0.0
    
    # Time series
    historical_values: List[float] = field(default_factory=list)
    historical_timestamps: List[float] = field(default_factory=list)
    
    # Status
    status: str = "unknown"  # excellent, good, fair, poor, critical
    alert_threshold: Optional[float] = None
    warning_threshold: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        # Sample historical data
        max_points = 30
        step = max(1, len(self.historical_values) // max_points) if len(self.historical_values) > max_points else 1
        sampled_history = [
            {
                "timestamp": datetime.fromtimestamp(self.historical_timestamps[i], tz=timezone.utc).isoformat(),
                "value": round(self.historical_values[i], 1)
            }
            for i in range(0, len(self.historical_values), step)
        ][:max_points]
        
        return {
            "kpi_id": self.kpi_id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "current": {
                "value": round(self.current_value, 1),
                "target": round(self.target_value, 1),
                "achievement_percent": round(self.current_value / self.target_value * 100, 1) if self.target_value > 0 else 0
            },
            "trend": {
                "previous_value": round(self.previous_value, 1),
                "improvement_percent": round(self.improvement_percent, 1)
            },
            "status": self.status,
            "thresholds": {
                "alert": self.alert_threshold,
                "warning": self.warning_threshold
            },
            "historical": sampled_history
        }
    
    def update_status(self) -> None:
        """Update KPI status based on current value and thresholds"""
        if self.alert_threshold and self.current_value <= self.alert_threshold:
            self.status = "critical"
        elif self.warning_threshold and self.current_value <= self.warning_threshold:
            self.status = "poor"
        elif self.current_value >= self.target_value * 0.9:
            self.status = "excellent"
        elif self.current_value >= self.target_value * 0.75:
            self.status = "good"
        elif self.current_value >= self.target_value * 0.6:
            self.status = "fair"
        else:
            self.status = "poor"


# ============================================================================
# CONFIGURATION MODELS
# ============================================================================

@dataclass
class SystemConfig:
    """
    System configuration for energy optimization
    """
    config_id: str
    version: str = "2.0.0"
    timestamp: float = field(default_factory=time.time)
    environment: str = "production"
    
    # Grid parameters
    nominal_frequency_hz: float = 50.0
    frequency_tolerance_hz: float = 0.5
    nominal_voltage_v: float = 230.0
    voltage_tolerance_percent: float = 10.0
    
    # Optimization weights
    grid_stability_weight: float = 0.6
    solar_efficiency_weight: float = 0.4
    
    # Thresholds
    grid_stability_warning: float = 70.0
    grid_stability_critical: float = 50.0
    solar_efficiency_warning: float = 60.0
    solar_efficiency_critical: float = 40.0
    
    # AECE parameters
    risk_medium_threshold: float = 0.35
    risk_high_threshold: float = 0.65
    risk_critical_threshold: float = 0.85
    
    # Cooldown periods (seconds)
    load_reduction_cooldown: int = 30
    energy_redistribution_cooldown: int = 60
    battery_dispatch_cooldown: int = 120
    solar_redirection_cooldown: int = 60
    
    # Feature flags
    enable_auto_control: bool = True
    enable_predictive_control: bool = True
    enable_battery_optimization: bool = True
    enable_alerts: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "config_id": self.config_id,
            "version": self.version,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "environment": self.environment,
            "grid": {
                "nominal_frequency_hz": self.nominal_frequency_hz,
                "frequency_tolerance_hz": self.frequency_tolerance_hz,
                "nominal_voltage_v": self.nominal_voltage_v,
                "voltage_tolerance_percent": self.voltage_tolerance_percent
            },
            "optimization_weights": {
                "grid_stability": self.grid_stability_weight,
                "solar_efficiency": self.solar_efficiency_weight
            },
            "thresholds": {
                "grid_stability": {
                    "warning": self.grid_stability_warning,
                    "critical": self.grid_stability_critical
                },
                "solar_efficiency": {
                    "warning": self.solar_efficiency_warning,
                    "critical": self.solar_efficiency_critical
                },
                "risk": {
                    "medium": self.risk_medium_threshold,
                    "high": self.risk_high_threshold,
                    "critical": self.risk_critical_threshold
                }
            },
            "cooldown_seconds": {
                "load_reduction": self.load_reduction_cooldown,
                "energy_redistribution": self.energy_redistribution_cooldown,
                "battery_dispatch": self.battery_dispatch_cooldown,
                "solar_redirection": self.solar_redirection_cooldown
            },
            "features": {
                "auto_control": self.enable_auto_control,
                "predictive_control": self.enable_predictive_control,
                "battery_optimization": self.enable_battery_optimization,
                "alerts": self.enable_alerts
            }
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_solar_expected_output(
    rated_power_kw: float,
    irradiance_wm2: float,
    temperature_c: float,
    efficiency_factor: float = 0.85
) -> float:
    """
    Calculate expected solar output based on conditions
    
    Args:
        rated_power_kw: Rated power of solar array (kWp)
        irradiance_wm2: Current irradiance (W/m²)
        temperature_c: Ambient temperature (°C)
        efficiency_factor: System efficiency factor (0-1)
    
    Returns:
        Expected output in kW
    """
    # Standard test condition: 1000 W/m² at 25°C
    irradiance_factor = irradiance_wm2 / 1000.0
    
    # Temperature derating (approx -0.4% per °C above 25°C)
    temp_derate = 1.0 - max(0, (temperature_c - 25) * 0.004)
    
    expected = rated_power_kw * irradiance_factor * temp_derate * efficiency_factor
    
    return max(0, min(rated_power_kw, expected))


def calculate_grid_frequency_response(
    supply_kw: float,
    demand_kw: float,
    inertia_constant: float = 10.0
) -> float:
    """
    Calculate grid frequency response to supply-demand imbalance
    
    Args:
        supply_kw: Total generation supply (kW)
        demand_kw: Total load demand (kW)
        inertia_constant: Grid inertia constant (seconds)
    
    Returns:
        Frequency deviation from nominal (Hz)
    """
    imbalance_mw = (supply_kw - demand_kw) / 1000.0  # Convert to MW
    max_capacity_mw = 100.0  # Assumed grid capacity
    
    # Frequency deviation: 1% imbalance ≈ 0.5Hz deviation
    deviation = (imbalance_mw / max_capacity_mw) * 0.5
    
    # Limit to reasonable range
    return max(-1.0, min(1.0, deviation))


def calculate_load_forecast_simple(
    historical_load: List[float],
    hour_of_day: int,
    day_of_week: int,
    trend_factor: float = 1.0
) -> float:
    """
    Simple load forecasting based on historical patterns
    
    Args:
        historical_load: Historical load values
        hour_of_day: Current hour (0-23)
        day_of_week: Current day of week (0-6, Monday=0)
        trend_factor: Trend multiplier
    
    Returns:
        Forecasted load in kW
    """
    if not historical_load:
        return 500.0  # Default
    
    # Base from historical average
    base_load = sum(historical_load) / len(historical_load)
    
    # Hourly pattern (typical)
    hourly_pattern = [
        0.65, 0.60, 0.55, 0.50, 0.50, 0.55,  # 0-5
        0.70, 0.85, 0.95, 0.98, 1.00, 1.02,  # 6-11
        1.00, 0.98, 0.95, 0.92, 0.90, 0.95,  # 12-17
        1.05, 1.10, 1.08, 1.00, 0.85, 0.75   # 18-23
    ]
    
    # Weekly pattern (weekday vs weekend)
    if day_of_week >= 5:  # Weekend
        weekend_factor = 0.85
    else:
        weekend_factor = 1.0
    
    # Calculate forecast
    forecast = base_load * hourly_pattern[hour_of_day] * weekend_factor * trend_factor
    
    return max(100.0, min(2000.0, forecast))


# ============================================================================
# EXPORTS (FINAL)
# ============================================================================

__all__.extend([
    # Load Profile Models
    'LoadProfile',
    'DemandResponseEvent',
    
    # Historical Data Models
    'HistoricalDataPoint',
    'HistoricalTrend',
    
    # KPI Models
    'KeyPerformanceIndicator',
    
    # Configuration Models
    'SystemConfig',
    
    # Helper Functions
    'calculate_solar_expected_output',
    'calculate_grid_frequency_response',
    'calculate_load_forecast_simple',
])

# ============================================================================
# MODULE INITIALIZATION LOG
# ============================================================================

logger = logging.getLogger("NeuroBridge.EnergyModels")
logger.info("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                    ENERGY MODELS v2.0.0 - PHASE 1                        ║
║     ✅ Telemetry Models - Solar and Grid metrics                         ║
║     ✅ Optimization Models - Single source of truth                      ║
║     ✅ AECE Decision Models - Impact tracking                            ║
║     ✅ Battery Models - Simulated BESS                                   ║
║     ✅ Inverter Models - Solar inverter telemetry                        ║
║     ✅ Weather Impact Models - Solar efficiency forecasting              ║
║     ✅ Load Profile Models - Demand analysis                             ║
║     ✅ Historical Trend Models - Performance tracking                    ║
║     ✅ KPI Models - Business metrics                                     ║
║     ✅ Phase 1 Compliant - No nuclear/fusion/quantum/defense             ║
║     ✅ Production Ready - Abuja Pilot Zone                               ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")

# ============================================================================
# END OF FILE - ENERGY MODELS v2.0.0
# ============================================================================