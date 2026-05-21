"""
Energy Kernel - Python Implementation (Production Ready)
Fallback when C++ kernel is unavailable
"""

import math
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class EnergyPredictor:
    """Energy prediction kernel - Python implementation"""
    
    def __init__(self):
        logger.info("[PythonKernel] EnergyPredictor initialized")
    
    def predict_yield(self, features: List[float]) -> float:
        """
        Predict energy yield from features
        
        Expected features (11 values):
        [irradiance_norm, temp_deviation, cloud_norm, efficiency, area_norm, ...]
        """
        if len(features) < 3:
            return 100.0
        
        # Extract meaningful features
        irradiance_norm = features[0] if len(features) > 0 else 0.85
        temp_deviation = features[1] if len(features) > 1 else 0.0
        cloud_norm = features[2] if len(features) > 2 else 0.0
        
        # Physics-based calculation
        stc_irradiance = 1000.0
        panel_area = 100.0
        panel_efficiency = 0.18
        
        irradiance_wm2 = irradiance_norm * stc_irradiance
        temperature_c = 25 + (temp_deviation * 25)
        cloud_percent = cloud_norm * 100
        
        # Solar power calculation
        irradiance_factor = irradiance_wm2 / stc_irradiance
        temp_derate = 1.0 - max(0, (temperature_c - 25) * 0.004)
        cloud_factor = 1.0 - (cloud_percent / 100) * 0.8
        
        power_kw = (irradiance_wm2 * panel_area * panel_efficiency) / 1000.0
        power_kw *= irradiance_factor * temp_derate * cloud_factor
        
        return max(0.0, min(200.0, power_kw))
    
    def calculate_stability(self, features: List[float]) -> float:
        """Calculate grid stability"""
        if len(features) < 4:
            return 95.0
        
        freq_norm = features[0] if len(features) > 0 else 0.0
        volt_norm = features[1] if len(features) > 1 else 0.0
        demand_norm = features[2] if len(features) > 2 else 0.5
        solar_norm = features[3] if len(features) > 3 else 0.2
        
        freq_hz = 50 + (freq_norm * 0.5)
        volt_v = 230 + (volt_norm * 23)
        
        score = 100.0
        score -= min(40, abs(freq_hz - 50) / 0.5 * 20)
        score -= min(30, abs(volt_v - 230) / 23 * 15)
        
        total_supply = 500 + (solar_norm * 500)
        demand = demand_norm * 1000
        if demand > 0:
            imbalance = abs(total_supply - demand) / demand
            score -= min(30, imbalance * 40)
        
        return max(0, min(100, score))


# This is the class the kernel loader expects
EnergyKernel = EnergyPredictor