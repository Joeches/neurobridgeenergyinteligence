
import math
import logging
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class GridStabilityMetrics:
    """Complete grid stability metrics"""
    stability_index: float  # 0-100
    frequency_quality: float  # 0-100
    voltage_quality: float  # 0-100
    balance_quality: float  # 0-100
    fluctuation_index: float  # 0-100
    risk_level: str  # low, medium, high, critical
    components: Dict[str, float]


@dataclass
class SolarEfficiencyMetrics:
    """Complete solar efficiency metrics"""
    efficiency_score: float  # 0-100
    irradiance_quality: float  # 0-100
    temperature_derating: float  # 0-100
    cloud_impact: float  # 0-100
    expected_output_kw: float
    actual_output_kw: float
    loss_percent: float


class EnergyMetricsEngine:
    """
    Core energy metrics calculation engine
    
    Grid Stability Index (GSI) formula:
    - Base 100
    - Penalty for frequency deviation (exponential)
    - Penalty for voltage deviation (linear)
    - Penalty for load-supply imbalance
    - Penalty for solar fluctuation variance
    
    Solar Efficiency Score (SES) formula:
    - Actual output / Expected output
    - Temperature derating factor
    - Irradiance quality factor
    - Cloud cover impact
    """
    
    def __init__(self):
        # Target values
        self.target_frequency_hz = 50.0
        self.target_voltage_v = 230.0
        self.frequency_tolerance = 0.5
        self.voltage_tolerance = 23.0  # 10% of 230V
        
        # Weights for composite score
        self.grid_weight = 0.6
        self.solar_weight = 0.4
        
        # Historical tracking
        self._frequency_history = []
        self._voltage_history = []
        self._solar_history = []
        self._max_history = 60  # Keep last 60 samples
        
        logger.info("[MetricsEngine] Initialized with physics-based formulas")
    
    # ========================================================================
    # GRID STABILITY INDEX (GSI)
    # ========================================================================
    
    def calculate_grid_stability_index(
        self,
        frequency_hz: float,
        voltage_v: float,
        supply_kw: float,
        demand_kw: float,
        solar_variance: Optional[float] = None
    ) -> GridStabilityMetrics:
        """
        Calculate Grid Stability Index (0-100)
        
        Formula:
        GSI = 100 - (F_penalty + V_penalty + B_penalty + S_penalty)
        
        Where:
        - F_penalty: Frequency deviation penalty (0-30)
        - V_penalty: Voltage deviation penalty (0-25)
        - B_penalty: Balance penalty (0-25)
        - S_penalty: Solar fluctuation penalty (0-20)
        """
        # Track history
        self._frequency_history.append(frequency_hz)
        self._voltage_history.append(voltage_v)
        if len(self._frequency_history) > self._max_history:
            self._frequency_history.pop(0)
        if len(self._voltage_history) > self._max_history:
            self._voltage_history.pop(0)
        
        # 1. Frequency quality (0-100, then convert to penalty)
        freq_deviation = abs(frequency_hz - self.target_frequency_hz)
        if freq_deviation <= 0.1:
            freq_quality = 100.0
            freq_penalty = 0
        elif freq_deviation <= 0.2:
            freq_quality = 90.0 - (freq_deviation - 0.1) * 100
            freq_penalty = 10 - (freq_quality - 80)
        elif freq_deviation <= 0.5:
            freq_quality = 80.0 - (freq_deviation - 0.2) * 100
            freq_penalty = 20 - (freq_quality - 60)
        else:
            freq_quality = max(0, 60.0 - (freq_deviation - 0.5) * 120)
            freq_penalty = min(40, 40 - (freq_quality - 20))
        
        freq_penalty = min(30, max(0, freq_penalty))
        
        # 2. Voltage quality
        voltage_deviation = abs(voltage_v - self.target_voltage_v)
        if voltage_deviation <= 5:
            voltage_quality = 100.0
            voltage_penalty = 0
        elif voltage_deviation <= 10:
            voltage_quality = 95.0 - (voltage_deviation - 5) * 3
            voltage_penalty = 5
        elif voltage_deviation <= 15:
            voltage_quality = 80.0 - (voltage_deviation - 10) * 4
            voltage_penalty = 15
        else:
            voltage_quality = max(0, 60.0 - (voltage_deviation - 15) * 4)
            voltage_penalty = min(25, 25)
        
        voltage_penalty = min(25, max(0, voltage_penalty))
        
        # 3. Load-Supply balance quality
        if demand_kw > 0:
            balance_ratio = supply_kw / demand_kw
            if 0.95 <= balance_ratio <= 1.05:
                balance_quality = 100.0
                balance_penalty = 0
            elif 0.90 <= balance_ratio <= 1.10:
                balance_quality = 90.0
                balance_penalty = 10
            elif 0.85 <= balance_ratio <= 1.15:
                balance_quality = 75.0
                balance_penalty = 25
            else:
                balance_quality = max(0, 60.0 - abs(1.0 - balance_ratio) * 100)
                balance_penalty = min(25, 25)
        else:
            balance_quality = 100.0
            balance_penalty = 0
        
        # 4. Solar fluctuation penalty (if variance provided)
        solar_penalty = 0
        fluctuation_index = 100.0
        
        if solar_variance is not None and len(self._solar_history) > 0:
            # Calculate variance of recent solar output
            if solar_variance > 100:  # High variance
                solar_penalty = 20
                fluctuation_index = 20
            elif solar_variance > 50:
                solar_penalty = 10
                fluctuation_index = 50
            elif solar_variance > 20:
                solar_penalty = 5
                fluctuation_index = 75
            else:
                fluctuation_index = 95
        
        # Calculate final stability index
        total_penalty = freq_penalty + voltage_penalty + balance_penalty + solar_penalty
        stability_index = max(0, min(100, 100 - total_penalty))
        
        # Determine risk level
        if stability_index >= 85:
            risk_level = "low"
        elif stability_index >= 70:
            risk_level = "medium"
        elif stability_index >= 50:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        return GridStabilityMetrics(
            stability_index=round(stability_index, 1),
            frequency_quality=round(freq_quality, 1),
            voltage_quality=round(voltage_quality, 1),
            balance_quality=round(balance_quality, 1),
            fluctuation_index=round(fluctuation_index, 1),
            risk_level=risk_level,
            components={
                "frequency_penalty": round(freq_penalty, 1),
                "voltage_penalty": round(voltage_penalty, 1),
                "balance_penalty": round(balance_penalty, 1),
                "solar_penalty": round(solar_penalty, 1)
            }
        )
    
    # ========================================================================
    # SOLAR EFFICIENCY SCORE (SES)
    # ========================================================================
    
    def calculate_solar_efficiency_score(
        self,
        actual_output_kw: float,
        irradiance_wm2: float,
        temperature_c: float,
        cloud_cover_percent: float = 0,
        panel_capacity_kw: float = 100.0
    ) -> SolarEfficiencyMetrics:
        """
        Calculate Solar Efficiency Score (0-100)
        
        Formula:
        SES = (actual / expected) × temp_factor × irradiance_factor × cloud_factor × 100
        
        Where:
        - expected = panel_capacity × (irradiance / 1000)
        - temp_factor = 1 - 0.004 × max(0, temp - 25)
        - irradiance_factor = min(1, irradiance / 1000)
        - cloud_factor = 1 - (cloud_cover / 100) × 0.8
        """
        # Track solar history
        self._solar_history.append(actual_output_kw)
        if len(self._solar_history) > self._max_history:
            self._solar_history.pop(0)
        
        # Calculate expected output
        expected_output = panel_capacity_kw * (irradiance_wm2 / 1000.0)
        
        # Calculate actual vs expected ratio
        if expected_output > 0:
            efficiency_ratio = min(1.0, actual_output_kw / expected_output)
        else:
            efficiency_ratio = 0.5
        
        # Temperature derating (-0.4% per °C above 25°C)
        if temperature_c > 25:
            temp_factor = 1.0 - ((temperature_c - 25) * 0.004)
        else:
            temp_factor = 1.0
        temp_factor = max(0.5, min(1.0, temp_factor))
        
        # Irradiance quality factor
        irradiance_factor = min(1.0, irradiance_wm2 / 1000.0)
        
        # Cloud cover impact
        cloud_factor = 1.0 - (cloud_cover_percent / 100.0) * 0.8
        cloud_factor = max(0.2, min(1.0, cloud_factor))
        
        # Calculate final efficiency score
        efficiency_score = efficiency_ratio * temp_factor * irradiance_factor * cloud_factor * 100
        
        # Calculate loss percentage
        loss_percent = (1 - (actual_output_kw / max(expected_output, 1))) * 100 if expected_output > 0 else 0
        loss_percent = max(0, min(100, loss_percent))
        
        return SolarEfficiencyMetrics(
            efficiency_score=round(efficiency_score, 1),
            irradiance_quality=round(irradiance_factor * 100, 1),
            temperature_derating=round(temp_factor * 100, 1),
            cloud_impact=round(cloud_factor * 100, 1),
            expected_output_kw=round(expected_output, 1),
            actual_output_kw=round(actual_output_kw, 1),
            loss_percent=round(loss_percent, 1)
        )
    
    # ========================================================================
    # COMPOSITE OPTIMIZATION SCORE
    # ========================================================================
    
    def calculate_composite_optimization_score(
        self,
        grid_stability: float,
        solar_efficiency: float,
        grid_weight: float = 0.6,
        solar_weight: float = 0.4
    ) -> float:
        """
        Calculate composite optimization score
        
        Score = (GSI × grid_weight) + (SES × solar_weight)
        """
        return (grid_stability * grid_weight) + (solar_efficiency * solar_weight)
    
    # ========================================================================
    # RISK SCORE CALCULATION
    # ========================================================================
    
    def calculate_risk_score(
        self,
        grid_stability: float,
        solar_efficiency: float,
        demand_trend: float = 0
    ) -> float:
        """
        Calculate risk score (0-1)
        
        Risk = (1 - GSI/100) × 0.7 + (1 - SES/100) × 0.3 + demand_trend × 0.1
        """
        grid_risk = (100 - grid_stability) / 100
        solar_risk = (100 - solar_efficiency) / 100
        
        risk = (grid_risk * 0.7) + (solar_risk * 0.3)
        
        # Add demand trend penalty if increasing
        if demand_trend > 0:
            risk += min(0.2, demand_trend * 0.1)
        
        return min(1.0, max(0.0, risk))
    
    # ========================================================================
    # UTILITY FUNCTIONS
    # ========================================================================
    
    def get_fluctuation_index(self) -> float:
        """
        Calculate solar fluctuation index based on recent history
        """
        if len(self._solar_history) < 3:
            return 100.0
        
        # Calculate variance of recent solar output
        mean = sum(self._solar_history) / len(self._solar_history)
        variance = sum((x - mean) ** 2 for x in self._solar_history) / len(self._solar_history)
        
        # Normalize to 0-100 (higher variance = lower index)
        max_variance = 2500  # 50kW variance max
        fluctuation_index = max(0, 100 - (variance / max_variance) * 100)
        
        return round(fluctuation_index, 1)
    
    def get_frequency_trend(self) -> str:
        """Determine frequency trend (increasing, decreasing, stable)"""
        if len(self._frequency_history) < 3:
            return "stable"
        
        recent = self._frequency_history[-5:]
        first = recent[0]
        last = recent[-1]
        
        if last > first + 0.1:
            return "increasing"
        elif last < first - 0.1:
            return "decreasing"
        return "stable"
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get engine statistics"""
        return {
            "frequency_history_length": len(self._frequency_history),
            "voltage_history_length": len(self._voltage_history),
            "solar_history_length": len(self._solar_history),
            "frequency_trend": self.get_frequency_trend(),
            "fluctuation_index": self.get_fluctuation_index(),
            "weights": {
                "grid_weight": self.grid_weight,
                "solar_weight": self.solar_weight
            }
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_metrics_engine: Optional[EnergyMetricsEngine] = None


def get_energy_metrics_engine() -> EnergyMetricsEngine:
    """Get global energy metrics engine instance"""
    global _metrics_engine
    if _metrics_engine is None:
        _metrics_engine = EnergyMetricsEngine()
    return _metrics_engine


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'EnergyMetricsEngine',
    'GridStabilityMetrics',
    'SolarEfficiencyMetrics',
    'get_energy_metrics_engine'
]