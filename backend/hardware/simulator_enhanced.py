"""
================================================================================
NeuroBridge 11D - Enhanced Modbus Simulator (Phase 1 Production)
================================================================================
Purpose: Realistic solar, load, and fault simulation
Features:
- Day/night cycle simulation
- Load spikes
- Fault injection
- Realistic solar curve
================================================================================
"""

import time
import math
import random
import threading
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class EnhancedModbusSimulator:
    """
    Realistic Modbus simulator with:
    - Solar production based on time of day
    - Load spikes based on demand patterns
    - Fault injection for testing AECE response
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._running = False
        self._thread = None
        
        # Current values
        self._active_power_kw = 500.0
        self._grid_frequency_hz = 50.0
        self._demand_load_kw = 500.0
        self._solar_output_kw = 0.0
        self._battery_soc_percent = 50.0
        self._voltage_v = 230.0
        self._temperature_c = 25.0
        
        # Fault injection flags
        self._fault_active = False
        self._fault_type = None
        self._fault_end_time = 0
        
        logger.info("[EnhancedSimulator] Initialized")
    
    def _calculate_solar_output(self) -> float:
        """Calculate realistic solar output based on time of day"""
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        
        # Solar production curve (peak at 1 PM)
        # Formula: sin(π * (hour - sunrise) / day_length) scaled
        sunrise = 6.0  # 6 AM
        sunset = 18.0  # 6 PM
        max_power = 200.0  # kW peak
        
        if hour < sunrise or hour > sunset:
            return 0.0
        
        # Normalized position in day (0 to 1)
        day_position = (hour - sunrise) / (sunset - sunrise)
        
        # Solar curve: sin(π * position)
        solar_factor = math.sin(math.pi * day_position)
        
        # Add some realistic variation (±10%)
        variation = 0.9 + (random.random() * 0.2)
        
        return max_power * solar_factor * variation
    
    def _calculate_load_demand(self) -> float:
        """Calculate realistic load demand based on time of day"""
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        
        # Base load (minimum demand)
        base_load = 300.0
        
        # Morning peak (7-9 AM)
        if 7 <= hour <= 9:
            peak_factor = 1.5 + (random.random() * 0.2)
        # Evening peak (5-8 PM)
        elif 17 <= hour <= 20:
            peak_factor = 1.6 + (random.random() * 0.2)
        # Night low (11 PM - 5 AM)
        elif hour <= 5 or hour >= 23:
            peak_factor = 0.6 + (random.random() * 0.1)
        else:
            peak_factor = 1.0 + (random.random() * 0.15)
        
        return base_load * peak_factor
    
    def _calculate_grid_frequency(self, load: float, solar: float, generation: float = 500.0) -> float:
        """Calculate grid frequency based on load-supply balance"""
        total_supply = generation + solar
        imbalance = (total_supply - load) / 1000.0  # Normalized imbalance
        
        # Frequency deviation: 1% imbalance ≈ 0.5Hz deviation
        freq_deviation = imbalance * 0.5
        freq = 50.0 + freq_deviation
        
        # Clamp to realistic range
        return max(49.0, min(51.0, freq))
    
    def inject_fault(self, fault_type: str, duration_seconds: float):
        """Inject a fault for testing AECE response"""
        self._fault_active = True
        self._fault_type = fault_type
        self._fault_end_time = time.time() + duration_seconds
        
        if fault_type == "frequency_drop":
            self._grid_frequency_hz = 49.2
            logger.warning(f"[FAULT] Frequency drop to 49.2Hz for {duration_seconds}s")
        elif fault_type == "load_spike":
            self._demand_load_kw = 900.0
            logger.warning(f"[FAULT] Load spike to 900kW for {duration_seconds}s")
        elif fault_type == "solar_dip":
            self._solar_output_kw = 20.0
            logger.warning(f"[FAULT] Solar dip to 20kW for {duration_seconds}s")
        elif fault_type == "over_voltage":
            self._voltage_v = 250.0
            logger.warning(f"[FAULT] Over-voltage to 250V for {duration_seconds}s")
    
    def _update(self):
        """Update simulator values"""
        # Check if fault has expired
        if self._fault_active and time.time() > self._fault_end_time:
            self._fault_active = False
            self._fault_type = None
            logger.info("[FAULT] Fault cleared - returning to normal operation")
        
        if not self._fault_active:
            # Normal simulation
            self._solar_output_kw = self._calculate_solar_output()
            self._demand_load_kw = self._calculate_load_demand()
            self._grid_frequency_hz = self._calculate_grid_frequency(
                self._demand_load_kw, self._solar_output_kw
            )
            
            # Battery SOC simulation (charge/discharge)
            if self._solar_output_kw > self._demand_load_kw * 0.3:
                # Excess solar -> charging
                charge_rate = min(10.0, (self._solar_output_kw - self._demand_load_kw * 0.3) / 10)
                self._battery_soc_percent = min(100.0, self._battery_soc_percent + charge_rate / 60)
            elif self._demand_load_kw > self._solar_output_kw + 400:
                # High demand -> discharging
                discharge_rate = min(10.0, (self._demand_load_kw - self._solar_output_kw - 400) / 20)
                self._battery_soc_percent = max(10.0, self._battery_soc_percent - discharge_rate / 60)
    
    def start(self):
        """Start the simulator thread"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[EnhancedSimulator] Started with realistic solar/load simulation")
    
    def _run(self):
        """Simulator main loop"""
        while self._running:
            self._update()
            time.sleep(1.0)  # Update every second
    
    def stop(self):
        """Stop the simulator"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[EnhancedSimulator] Stopped")
    
    def get_telemetry(self) -> Dict[str, Any]:
        """Get current telemetry snapshot"""
        return {
            "active_power_kw": round(self._active_power_kw, 1),
            "grid_frequency_hz": round(self._grid_frequency_hz, 2),
            "demand_load_kw": round(self._demand_load_kw, 1),
            "solar_output_kw": round(self._solar_output_kw, 1),
            "battery_soc_percent": round(self._battery_soc_percent, 1),
            "voltage_v": round(self._voltage_v, 1),
            "temperature_c": round(self._temperature_c, 1),
            "fault_active": self._fault_active,
            "fault_type": self._fault_type
        }


# Global instance
_simulator: Optional[EnhancedModbusSimulator] = None


def get_simulator() -> EnhancedModbusSimulator:
    """Get global simulator instance"""
    global _simulator
    if _simulator is None:
        _simulator = EnhancedModbusSimulator()
    return _simulator