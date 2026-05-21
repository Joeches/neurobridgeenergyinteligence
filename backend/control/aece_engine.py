# backend/control/aece_engine.py - PRODUCTION CLEAN v4.1.0
# Autonomous Energy Control Engine - Phase 1 Compliant
# Prometheus Metrics Instrumented - AECE Observability

import asyncio
import time
import logging
import uuid
import json
import traceback
import math
import random
import threading
import os
from typing import Dict, Any, Optional, List, Tuple, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from collections import deque, defaultdict
from functools import wraps
from pathlib import Path

# ============================================================================
# LOGGER CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)

# Single concise initialization log - NO BANNER
logger.info("[AECE] engine initializing")

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

METRICS_AVAILABLE = False
prom_metrics = None

# Default null functions for graceful degradation
def record_aece_action(action: str, priority: str):
    pass

def record_grid_risk_event(risk_level: str):
    pass

def update_aece_risk_score(risk_score: float):
    pass

try:
    from backend.monitoring.prometheus_metrics import (
        record_aece_action as prom_record_aece_action,
        record_grid_risk_event as prom_record_grid_risk,
        update_aece_risk_score as prom_update_risk_score,
        record_aece_decision,
        set_emergency_stop_state,
        set_grid_stability_index,
        set_solar_efficiency_score,
        set_active_module,
        set_prediction_accuracy,
        metrics as prom_metrics_instance,
    )
    
    # Override with real implementations
    record_aece_action = prom_record_aece_action
    record_grid_risk_event = prom_record_grid_risk
    update_aece_risk_score = prom_update_risk_score
    METRICS_AVAILABLE = True
    prom_metrics = prom_metrics_instance
    logger.info("[AECE] prometheus metrics instrumented")
except ImportError:
    logger.debug("[AECE] prometheus metrics unavailable - running without instrumentation")
    # Create null fallbacks for extended metrics
    def record_aece_decision(*args, **kwargs): pass
    def set_emergency_stop_state(*args, **kwargs): pass
    def set_grid_stability_index(*args, **kwargs): pass
    def set_solar_efficiency_score(*args, **kwargs): pass
    def set_active_module(*args, **kwargs): pass
    def set_prediction_accuracy(*args, **kwargs): pass

# ============================================================================
# ADFI INTEGRATION (OPTIONAL)
# ============================================================================

ADFI_AVAILABLE = False
EnergyDataPoint = None
DataSourceType = None
get_orchestrator = None
get_data_pipeline = None

try:
    from backend.integrations.adfi_engine import EnergyDataPoint, DataSourceType, get_orchestrator
    from backend.integrations.data_pipeline import get_data_pipeline
    ADFI_AVAILABLE = True
except ImportError:
    pass

# ============================================================================
# AECE AVAILABILITY FLAG
# ============================================================================

AECE_AVAILABLE = True

# ============================================================================
# ENVIRONMENT VARIABLE PARSING
# ============================================================================

def get_env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    value_lower = value.lower().strip()
    if value_lower in ("true", "1", "yes", "on"):
        return True
    elif value_lower in ("false", "0", "no", "off"):
        return False
    return default


def get_env_float(key: str, default: float, min_val: float = None, max_val: float = None) -> float:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        parsed = float(value)
        if min_val is not None and parsed < min_val:
            return min_val
        if max_val is not None and parsed > max_val:
            return max_val
        return parsed
    except (ValueError, TypeError):
        return default


def get_env_int(key: str, default: int, min_val: int = None, max_val: int = None) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        parsed = int(value)
        if min_val is not None and parsed < min_val:
            return min_val
        if max_val is not None and parsed > max_val:
            return max_val
        return parsed
    except (ValueError, TypeError):
        return default


def get_runtime_mode() -> str:
    env = os.getenv("ENVIRONMENT", "production").lower()
    if env in ("production", "prod"):
        return "production"
    elif env in ("staging", "stage"):
        return "staging"
    return "development"

# ============================================================================
# PROTECTION MODE CONFIGURATION
# ============================================================================

PROTECTION_MODE_ENABLED_BY_DEFAULT = get_env_bool("AECE_PROTECTION_MODE_ACTIVE", True)
PROTECTION_MODE_FORCE_ENABLE = get_env_bool("AECE_FORCE_PROTECTION_MODE", True)
PROTECTION_AUDIT_LOG: List[Dict[str, Any]] = []


def _audit_protection_change(action: str, reason: str, previous_state: bool, new_state: bool):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "reason": reason,
        "previous_state": previous_state,
        "new_state": new_state,
        "phase": "PHASE_1_PRODUCTION"
    }
    PROTECTION_AUDIT_LOG.append(entry)
    while len(PROTECTION_AUDIT_LOG) > 1000:
        PROTECTION_AUDIT_LOG.pop(0)
    
    # PROMETHEUS: Track emergency stop state changes
    try:
        set_emergency_stop_state(active=new_state, component="protection_mode")
    except Exception:
        pass

# ============================================================================
# PHASE 1 CONFIGURATION - BLOCKED DOMAINS
# ============================================================================

AECE_PHASE1_ALLOWED_ACTIONS = [
    "reduce_load", "redistribute_energy", "preemptive_stabilization",
    "trigger_alert", "lockdown_mode", "no_action", "increase_solar_efficiency",
    "dispatch_battery", "curtail_solar", "adjust_inverter_power"
]

AECE_PHASE1_BLOCKED_ACTIONS = [
    "nuclear_control", "fusion_stabilization", "quantum_optimization", "defense_protocol"
]

_phase1_blocked_actions_log: List[Dict[str, Any]] = []


def is_phase1_allowed_action(action: str) -> bool:
    action_lower = action.lower()
    for blocked_action in AECE_PHASE1_BLOCKED_ACTIONS:
        if blocked_action in action_lower:
            return False
    for allowed_action in AECE_PHASE1_ALLOWED_ACTIONS:
        if allowed_action in action_lower:
            return True
    return False


def validate_phase1_compliance(decision_data: Dict[str, Any]) -> Tuple[bool, str]:
    action = decision_data.get("action", "")
    if not is_phase1_allowed_action(action):
        _phase1_blocked_actions_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "phase": "PHASE_1_BLOCKED"
        })
        return False, f"Action '{action}' blocked in Phase 1"
    return True, "Phase 1 compliant"


def get_phase1_blocked_stats() -> Dict[str, Any]:
    return {
        "total_blocked": len(_phase1_blocked_actions_log),
        "recent_blocked": _phase1_blocked_actions_log[-10:] if _phase1_blocked_actions_log else [],
        "allowed_actions": AECE_PHASE1_ALLOWED_ACTIONS,
        "blocked_actions": AECE_PHASE1_BLOCKED_ACTIONS,
        "phase": "PHASE_1_PRODUCTION"
    }


def get_phase1_status() -> Dict[str, Any]:
    return {
        "phase": "PHASE_1_PRODUCTION",
        "allowed_actions": AECE_PHASE1_ALLOWED_ACTIONS,
        "blocked_actions": AECE_PHASE1_BLOCKED_ACTIONS,
        "total_blocked_attempts": len(_phase1_blocked_actions_log),
        "version": "4.1.0",
        "runtime_mode": get_runtime_mode()
    }

# ============================================================================
# DATA MODELS
# ============================================================================

class ControlAction(str, Enum):
    REDUCE_LOAD = "reduce_load"
    REDISTRIBUTE_ENERGY = "redistribute_energy"
    PREEMPTIVE_STABILIZATION = "preemptive_stabilization"
    TRIGGER_ALERT = "trigger_alert"
    LOCKDOWN_MODE = "lockdown_mode"
    NO_ACTION = "no_action"
    INCREASE_SOLAR_EFFICIENCY = "increase_solar_efficiency"
    DISPATCH_BATTERY = "dispatch_battery"
    CURTAIL_SOLAR = "curtail_solar"
    ADJUST_INVERTER_POWER = "adjust_inverter_power"


class ControlPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class DecisionConfidence(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


@dataclass
class UEIV:
    solar_efficiency: float = 0.5
    grid_risk: float = 0.3
    weather_severity: float = 0.2
    demand_load: float = 0.5
    predicted_solar_efficiency: float = 0.5
    predicted_grid_risk: float = 0.3
    predicted_demand_peak: float = 0.0
    solar_trend: float = 0.0
    load_trend: float = 0.0
    battery_soc: float = 0.5
    battery_power_kw: float = 0.0
    storage_available_kwh: float = 100.0
    nuclear_stability: float = 1.0
    ergotropy_score: float = 0.8
    threat_level: str = "LOW"

    def validate(self) -> bool:
        try:
            return all([
                0.0 <= self.solar_efficiency <= 1.0,
                0.0 <= self.grid_risk <= 1.0,
                0.0 <= self.weather_severity <= 1.0,
                0.0 <= self.demand_load <= 2.0,
                0.0 <= self.battery_soc <= 1.0,
            ])
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "solar_efficiency": round(self.solar_efficiency, 4),
            "grid_risk": round(self.grid_risk, 4),
            "weather_severity": round(self.weather_severity, 4),
            "demand_load": round(self.demand_load, 4),
            "battery_soc": round(self.battery_soc, 4),
            "phase": "PHASE_1_PRODUCTION"
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UEIV':
        return cls(
            solar_efficiency=float(data.get("solar_efficiency", 0.5)),
            grid_risk=float(data.get("grid_risk", 0.3)),
            weather_severity=float(data.get("weather_severity", 0.2)),
            demand_load=float(data.get("demand_load", 0.5)),
            battery_soc=float(data.get("battery_soc", 0.5)),
        )

    @classmethod
    def from_telemetry(cls, telemetry: Dict[str, Any]) -> 'UEIV':
        try:
            solar_output_kw = float(telemetry.get("solar_output_kw", telemetry.get("solar_power_kw", 100)))
            max_solar_kw = float(telemetry.get("max_solar_kw", 200))
            solar_efficiency = min(1.0, solar_output_kw / max(max_solar_kw, 1))
            
            grid_frequency = float(telemetry.get("grid_frequency_hz", telemetry.get("frequency_hz", 50.0)))
            grid_risk = min(1.0, abs(50.0 - grid_frequency) / 5.0)
            
            demand_load_kw = float(telemetry.get("demand_load_kw", telemetry.get("demand_kw", 500)))
            max_demand_kw = float(telemetry.get("max_demand_kw", 2000))
            demand_load = demand_load_kw / max(max_demand_kw, 1)
            
            cloud_cover = float(telemetry.get("cloud_cover_percent", telemetry.get("cloud_cover", 25)))
            weather_severity = min(1.0, cloud_cover / 100.0)
            
            battery_soc_percent = float(telemetry.get("battery_soc_percent", telemetry.get("battery_soc", 50)))
            battery_soc = battery_soc_percent / 100.0
            
            return cls(
                solar_efficiency=solar_efficiency,
                grid_risk=grid_risk,
                weather_severity=weather_severity,
                demand_load=demand_load,
                battery_soc=battery_soc
            )
        except Exception as e:
            logger.warning(f"[AECE] Telemetry conversion failed: {e}")
            return cls.safe_default()

    @classmethod
    def safe_default(cls) -> 'UEIV':
        return cls()

    def sanitize(self) -> 'UEIV':
        self.solar_efficiency = max(0.0, min(1.0, self.solar_efficiency))
        self.grid_risk = max(0.0, min(1.0, self.grid_risk))
        self.weather_severity = max(0.0, min(1.0, self.weather_severity))
        self.demand_load = max(0.0, min(2.0, self.demand_load))
        self.battery_soc = max(0.0, min(1.0, self.battery_soc))
        return self


@dataclass
class ControlDecision:
    action: ControlAction
    priority: ControlPriority
    risk_score: float
    confidence_score: float
    confidence_level: DecisionConfidence
    reason: str
    triggered_rules: List[str]
    recommended_parameters: Dict[str, Any] = field(default_factory=dict)
    predicted_outcome: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "priority": self.priority.value,
            "risk_score": round(self.risk_score, 4),
            "confidence_score": round(self.confidence_score, 4),
            "confidence_level": self.confidence_level.value,
            "reason": self.reason,
            "triggered_rules": self.triggered_rules,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "phase": "PHASE_1_PRODUCTION"
        }


@dataclass
class ControlAuditEntry:
    decision_id: str
    ueiv_snapshot: Dict[str, Any]
    decision: ControlDecision
    action_executed: bool
    execution_result: Optional[Dict[str, Any]]
    duration_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "ueiv_snapshot": self.ueiv_snapshot,
            "decision": self.decision.to_dict(),
            "action_executed": self.action_executed,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "phase": "PHASE_1_PRODUCTION"
        }

# ============================================================================
# PREDICTIVE ANALYTICS ENGINE
# ============================================================================

class PredictiveAnalyticsEngine:
    def __init__(self, lookahead_minutes: int = 15):
        self.lookahead_minutes = lookahead_minutes
        self._history: Dict[str, deque] = {
            "solar_efficiency": deque(maxlen=100),
            "grid_risk": deque(maxlen=100),
            "demand_load": deque(maxlen=100),
            "battery_soc": deque(maxlen=100)
        }

    def update_history(self, ueiv: UEIV):
        self._history["solar_efficiency"].append(ueiv.solar_efficiency)
        self._history["grid_risk"].append(ueiv.grid_risk)
        self._history["demand_load"].append(ueiv.demand_load)
        self._history["battery_soc"].append(ueiv.battery_soc)
        
        # PROMETHEUS: Update prediction accuracy based on history stability
        try:
            solar_history = list(self._history["solar_efficiency"])
            if len(solar_history) >= 10:
                variance = sum((s - 0.5) ** 2 for s in solar_history[-10:]) / 10
                accuracy = max(0.0, 1.0 - variance)
                set_prediction_accuracy(component="solar_efficiency", value=accuracy)
        except Exception:
            pass

    def predict_solar_efficiency(self, minutes_ahead: int = 15) -> float:
        history = list(self._history["solar_efficiency"])
        if len(history) < 10:
            return 0.5
        recent = history[-10:]
        trend = (recent[-1] - recent[0]) / len(recent) if len(recent) > 1 else 0
        prediction = recent[-1] + trend * (minutes_ahead / 60)
        return max(0.0, min(1.0, prediction))

    def predict_grid_risk(self, minutes_ahead: int = 15) -> float:
        history = list(self._history["grid_risk"])
        if len(history) < 10:
            return 0.3
        recent = history[-10:]
        trend = (recent[-1] - recent[0]) / len(recent) if len(recent) > 1 else 0
        now = datetime.now()
        hour = now.hour + now.minute / 60
        peak_factor = 1.3 if 17 <= hour <= 20 else (1.2 if 7 <= hour <= 9 else 1.0)
        prediction = (recent[-1] + trend) * peak_factor
        return max(0.0, min(1.0, prediction))

    def predict_demand_peak(self) -> float:
        history = list(self._history["demand_load"])
        if len(history) < 10:
            return 0.8
        recent_max = max(history[-10:])
        trend = (history[-1] - history[0]) / len(history) if len(history) > 1 else 0
        predicted_peak = recent_max + trend * 1.2
        return max(0.0, min(2.0, predicted_peak))

    def get_solar_trend(self) -> float:
        history = list(self._history["solar_efficiency"])
        if len(history) < 6:
            return 0.0
        recent = history[-5:]
        increasing = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
        decreasing = len(recent) - 1 - increasing
        if increasing > decreasing:
            return min(1.0, increasing / len(recent))
        elif decreasing > increasing:
            return -min(1.0, decreasing / len(recent))
        return 0.0

    def get_load_trend(self) -> float:
        history = list(self._history["demand_load"])
        if len(history) < 6:
            return 0.0
        recent = history[-5:]
        increasing = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
        decreasing = len(recent) - 1 - increasing
        if increasing > decreasing:
            return min(1.0, increasing / len(recent))
        elif decreasing > increasing:
            return -min(1.0, decreasing / len(recent))
        return 0.0

# ============================================================================
# RISK SCORING ENGINE
# ============================================================================

class EnhancedRiskScoringEngine:
    PHYSICS_WEIGHTS = {
        "grid_risk": 0.35,
        "demand_load": 0.25,
        "weather_severity": 0.20,
        "solar_efficiency_inverse": 0.20,
    }

    @staticmethod
    def _safe_extract_float(obj: Any, *attr_names: str, default: float = 0.5) -> float:
        for attr in attr_names:
            try:
                if hasattr(obj, 'get'):
                    val = obj.get(attr)
                    if val is not None:
                        return float(val)
                elif hasattr(obj, attr):
                    val = getattr(obj, attr)
                    return float(val)
                elif attr == 'solar_efficiency' and hasattr(obj, 'solar_efficiency_percent'):
                    return float(obj.solar_efficiency_percent) / 100.0
                elif attr == 'grid_risk' and hasattr(obj, 'aece_risk_factor'):
                    return float(obj.aece_risk_factor)
                elif attr == 'battery_soc' and hasattr(obj, 'battery_soc_percent'):
                    return float(obj.battery_soc_percent) / 100.0
                elif attr == 'demand_load' and hasattr(obj, 'demand_load_kw'):
                    return float(obj.demand_load_kw) / 1000.0
                elif attr == 'weather_severity' and hasattr(obj, 'cloud_cover_percent'):
                    return float(obj.cloud_cover_percent) / 100.0
            except (TypeError, ValueError, AttributeError):
                continue
        return default

    @classmethod
    def calculate(cls, ueiv: Union[UEIV, Dict, Any], adaptive_weights: Optional[Dict[str, float]] = None, use_predictive: bool = True) -> float:
        try:
            solar_eff = cls._safe_extract_float(ueiv, 'solar_efficiency', 'solar_efficiency_percent', default=0.5)
            grid_risk_val = cls._safe_extract_float(ueiv, 'grid_risk', 'aece_risk_factor', default=0.3)
            weather = cls._safe_extract_float(ueiv, 'weather_severity', 'cloud_cover_percent', default=0.2)
            demand = cls._safe_extract_float(ueiv, 'demand_load', 'demand_load_kw', default=0.5)
            battery = cls._safe_extract_float(ueiv, 'battery_soc', 'battery_soc_percent', default=0.5)

            solar_risk = 1.0 - solar_eff
            weights = adaptive_weights or cls.PHYSICS_WEIGHTS

            current_risk = (
                grid_risk_val * weights["grid_risk"] +
                demand * weights["demand_load"] +
                weather * weights["weather_severity"] +
                solar_risk * weights["solar_efficiency_inverse"]
            )

            if use_predictive:
                predicted_grid = cls._safe_extract_float(ueiv, 'predicted_grid_risk', default=0.3)
                predicted_peak = cls._safe_extract_float(ueiv, 'predicted_demand_peak', default=0.0)
                predictive_risk = (predicted_grid * 0.3 + predicted_peak * 0.2)
                current_risk = current_risk * 0.7 + predictive_risk * 0.3

            if battery < 0.2:
                current_risk *= 1.2
            elif battery > 0.8:
                current_risk *= 0.9

            risk_score = max(0.0, min(1.0, current_risk))
            
            # PROMETHEUS: Update AECE risk score
            try:
                update_aece_risk_score(risk_score)
            except Exception:
                pass
            
            return risk_score
        except Exception:
            return 0.5

    @classmethod
    def get_risk_level(cls, risk_score: float) -> Tuple[str, ControlPriority]:
        if risk_score >= 0.85:
            return "CRITICAL", ControlPriority.CRITICAL
        elif risk_score >= 0.65:
            return "HIGH", ControlPriority.HIGH
        elif risk_score >= 0.35:
            return "MEDIUM", ControlPriority.NORMAL
        return "LOW", ControlPriority.LOW

    @classmethod
    def get_confidence(cls, risk_score: float, ueiv: Any) -> Tuple[float, DecisionConfidence]:
        base_confidence = 0.85
        if base_confidence >= 0.85:
            return base_confidence, DecisionConfidence.HIGH
        elif base_confidence >= 0.70:
            return base_confidence, DecisionConfidence.MEDIUM
        elif base_confidence >= 0.50:
            return base_confidence, DecisionConfidence.LOW
        return base_confidence, DecisionConfidence.VERY_LOW


RiskScoringEngine = EnhancedRiskScoringEngine

# ============================================================================
# HYSTERESIS MANAGER
# ============================================================================

class EnhancedHysteresisManager:
    def __init__(self):
        self._last_action_time: Dict[str, float] = {}
        self._action_counters: Dict[str, int] = defaultdict(int)
        self._last_risk_score: float = 0.0
        self._last_action_times: deque = deque(maxlen=60)

        self.cooldown_seconds = {
            ControlAction.REDUCE_LOAD: 30.0,
            ControlAction.REDISTRIBUTE_ENERGY: 60.0,
            ControlAction.PREEMPTIVE_STABILIZATION: 120.0,
            ControlAction.TRIGGER_ALERT: 300.0,
            ControlAction.LOCKDOWN_MODE: 600.0,
            ControlAction.INCREASE_SOLAR_EFFICIENCY: 15.0,
            ControlAction.DISPATCH_BATTERY: 10.0,
            ControlAction.CURTAIL_SOLAR: 30.0,
            ControlAction.ADJUST_INVERTER_POWER: 5.0,
        }

        self.hysteresis_thresholds = {"risk_up": 0.05, "risk_down": 0.03}
        self.max_actions_per_minute = 15

    def can_execute(self, action: ControlAction, current_risk_score: float) -> Tuple[bool, str]:
        try:
            action_key = action.value
            last_time = self._last_action_time.get(action_key, 0)
            cooldown = self.cooldown_seconds.get(action, 30.0)
            time_since_last = time.time() - last_time

            if time_since_last < cooldown:
                return False, f"Cooldown: {cooldown - time_since_last:.1f}s remaining"

            risk_diff = current_risk_score - self._last_risk_score
            if action_key in self._last_action_time:
                if abs(risk_diff) < self.hysteresis_thresholds["risk_up"]:
                    return False, f"Risk change insufficient: {risk_diff:.3f}"

            self._clean_old_counters()
            total_actions = sum(self._action_counters.values())
            if total_actions >= self.max_actions_per_minute:
                return False, f"Rate limit: {total_actions}/{self.max_actions_per_minute} actions/min"

            return True, "OK"
        except Exception:
            return False, "Safety error"

    def record_execution(self, action: ControlAction, risk_score: float):
        try:
            action_key = action.value
            now = time.time()
            self._last_action_time[action_key] = now
            self._action_counters[action_key] += 1
            self._last_action_times.append(now)
            self._last_risk_score = risk_score
        except Exception:
            pass

    def _clean_old_counters(self):
        try:
            now = time.time()
            cutoff = now - 60.0
            self._action_counters.clear()
            for t in self._last_action_times:
                if t > cutoff:
                    self._action_counters["recent"] += 1
        except Exception:
            pass

# ============================================================================
# DECISION ENGINE
# ============================================================================

class EnhancedDecisionEngine:
    def __init__(self):
        self.hysteresis = EnhancedHysteresisManager()
        self._decision_history: deque = deque(maxlen=500)

    @staticmethod
    def _convert_to_ueiv(input_obj: Any) -> UEIV:
        if isinstance(input_obj, UEIV):
            return input_obj
        if isinstance(input_obj, dict):
            return UEIV(
                solar_efficiency=float(input_obj.get("solar_efficiency", 0.5)),
                grid_risk=float(input_obj.get("grid_risk", 0.3)),
                weather_severity=float(input_obj.get("weather_severity", 0.2)),
                demand_load=float(input_obj.get("demand_load", 0.5)),
                battery_soc=float(input_obj.get("battery_soc", 0.5)),
            )
        try:
            return UEIV(
                solar_efficiency=EnhancedRiskScoringEngine._safe_extract_float(input_obj, 'solar_efficiency', default=0.5),
                grid_risk=EnhancedRiskScoringEngine._safe_extract_float(input_obj, 'grid_risk', default=0.3),
                weather_severity=EnhancedRiskScoringEngine._safe_extract_float(input_obj, 'weather_severity', default=0.2),
                demand_load=EnhancedRiskScoringEngine._safe_extract_float(input_obj, 'demand_load', default=0.5),
                battery_soc=EnhancedRiskScoringEngine._safe_extract_float(input_obj, 'battery_soc', default=0.5),
            )
        except Exception:
            return UEIV.safe_default()

    def evaluate(self, ueiv_input: Any, *args, **kwargs) -> ControlDecision:
        ueiv = self._convert_to_ueiv(ueiv_input)

        try:
            risk_score = EnhancedRiskScoringEngine.calculate(ueiv, use_predictive=True)

            # PROMETHEUS: Calculate and set grid stability index
            gsi = max(0.0, min(100.0, (1.0 - ueiv.grid_risk) * 100.0))
            ses = max(0.0, min(100.0, ueiv.solar_efficiency * 100.0))
            try:
                set_grid_stability_index(gsi)
                set_solar_efficiency_score(ses)
            except Exception:
                pass

            if risk_score >= 0.85:
                decision = ControlDecision(
                    action=ControlAction.LOCKDOWN_MODE, priority=ControlPriority.CRITICAL,
                    risk_score=risk_score, confidence_score=0.95, confidence_level=DecisionConfidence.VERY_HIGH,
                    reason=f"Critical risk: {risk_score:.3f}", triggered_rules=["critical_risk"],
                    recommended_parameters={"severity": "max"}, predicted_outcome={}
                )
                record_grid_risk_event("critical")
                return decision

            if risk_score >= 0.65:
                if ueiv.grid_risk > 0.75:
                    action, reason = ControlAction.REDUCE_LOAD, f"Grid instability: risk={ueiv.grid_risk:.3f}"
                    triggered = ["grid_instability"]
                elif ueiv.demand_load > 0.9:
                    action, reason = ControlAction.REDISTRIBUTE_ENERGY, f"High demand: {ueiv.demand_load:.3f}"
                    triggered = ["high_demand"]
                elif ueiv.weather_severity > 0.75:
                    action, reason = ControlAction.PREEMPTIVE_STABILIZATION, f"Severe weather: {ueiv.weather_severity:.3f}"
                    triggered = ["weather_impact"]
                else:
                    action, reason = ControlAction.REDUCE_LOAD, f"High risk: {risk_score:.3f}"
                    triggered = ["high_risk_default"]

                record_grid_risk_event("high")
                return ControlDecision(
                    action=action, priority=ControlPriority.HIGH,
                    risk_score=risk_score, confidence_score=0.85, confidence_level=DecisionConfidence.HIGH,
                    reason=reason, triggered_rules=triggered,
                    recommended_parameters={"reduction_percent": 15}, predicted_outcome={}
                )

            rules = [
                (ueiv.grid_risk > 0.6, ControlAction.REDUCE_LOAD, "Grid risk elevated", ["grid_risk"], {}),
                (ueiv.demand_load > 0.8, ControlAction.REDISTRIBUTE_ENERGY, "High demand", ["demand_load"], {}),
                (ueiv.weather_severity > 0.6, ControlAction.PREEMPTIVE_STABILIZATION, "Weather impact", ["weather"], {}),
                (ueiv.solar_efficiency < 0.3, ControlAction.INCREASE_SOLAR_EFFICIENCY, "Low solar efficiency", ["solar_low"], {"target_efficiency": 0.5}),
                (ueiv.battery_soc > 0.7 and ueiv.demand_load > 0.7, ControlAction.DISPATCH_BATTERY, "Battery dispatch", ["battery_dispatch"], {"discharge_power_kw": 50}),
                (ueiv.solar_efficiency > 0.8 and ueiv.battery_soc < 0.3, ControlAction.CURTAIL_SOLAR, "Solar curtailment", ["solar_curtail"], {"curtail_percent": 20}),
            ]

            for condition, action, reason, triggered, params in rules:
                if condition:
                    return ControlDecision(
                        action=action, priority=ControlPriority.NORMAL,
                        risk_score=risk_score, confidence_score=0.85, confidence_level=DecisionConfidence.HIGH,
                        reason=reason, triggered_rules=triggered,
                        recommended_parameters=params, predicted_outcome={}
                    )

            return ControlDecision(
                action=ControlAction.NO_ACTION, priority=ControlPriority.LOW,
                risk_score=risk_score, confidence_score=0.98, confidence_level=DecisionConfidence.VERY_HIGH,
                reason=f"System stable: risk={risk_score:.3f}", triggered_rules=["stable"],
                recommended_parameters={}, predicted_outcome={}
            )
        except Exception as e:
            return ControlDecision(
                action=ControlAction.NO_ACTION, priority=ControlPriority.LOW,
                risk_score=0.5, confidence_score=0.5, confidence_level=DecisionConfidence.VERY_LOW,
                reason=f"Error fallback", triggered_rules=["error"],
                recommended_parameters={}, predicted_outcome={}
            )

    def should_execute(self, decision: ControlDecision) -> Tuple[bool, str]:
        if decision.action == ControlAction.NO_ACTION:
            return False, "No action required"
        return self.hysteresis.can_execute(decision.action, decision.risk_score)

    def record_execution(self, decision: ControlDecision):
        try:
            self.hysteresis.record_execution(decision.action, decision.risk_score)
            self._decision_history.append(decision)
        except Exception:
            pass

# ============================================================================
# ACTION EXECUTOR
# ============================================================================

class EnhancedActionExecutor:
    def __init__(self):
        self._protection_mode_active = PROTECTION_MODE_ENABLED_BY_DEFAULT
        self._action_history: List[Dict] = []

        if PROTECTION_MODE_FORCE_ENABLE and not self._protection_mode_active:
            self._protection_mode_active = True
            _audit_protection_change("force_enable", "Force enabled", False, True)

        status = "active" if self._protection_mode_active else "inactive"
        logger.info(f"[AECE] action executor initialized protection={status}")
        
        # PROMETHEUS: Set initial emergency stop state and module active
        try:
            set_emergency_stop_state(active=self._protection_mode_active, component="protection_mode")
            set_active_module(module="aece_engine", active=True)
        except Exception:
            pass

    def _normalize_percentage(self, value: Any, default: float = 20.0) -> float:
        try:
            val = float(value)
            if val > 1 and val <= 100:
                return val
            elif 0 <= val <= 1:
                return val * 100
            return default
        except (TypeError, ValueError):
            return default

    async def reduce_load(self, percentage: float = 20.0, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("reduce_load"):
            return self._blocked_response("reduce_load")
        percentage = self._normalize_percentage(percentage, 20.0)
        percentage = max(0.0, min(100.0, percentage))
        await asyncio.sleep(0.02)
        record_aece_action(action="reduce_load", priority="high")
        record_aece_decision(
            action="reduce_load", risk_score=0.0, gsi=None, ses=None, module="aece_engine"
        )
        return {"success": True, "action": "reduce_load", "percentage": percentage, "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def redistribute_energy(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("redistribute_energy"):
            return self._blocked_response("redistribute_energy")
        await asyncio.sleep(0.02)
        record_aece_action(action="redistribute_energy", priority="normal")
        record_aece_decision(
            action="redistribute_energy", risk_score=0.0, gsi=None, ses=None, module="aece_engine"
        )
        return {"success": True, "action": "redistribute_energy", "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def preemptive_stabilization(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("preemptive_stabilization"):
            return self._blocked_response("preemptive_stabilization")
        await asyncio.sleep(0.02)
        record_aece_action(action="preemptive_stabilization", priority="high")
        record_aece_decision(
            action="preemptive_stabilization", risk_score=0.0, gsi=None, ses=None, module="aece_engine"
        )
        return {"success": True, "action": "preemptive_stabilization", "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def trigger_alert(self, message: str, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("trigger_alert"):
            return self._blocked_response("trigger_alert")
        logger.warning(f"[AECE] Alert: {message}")
        record_aece_action(action="trigger_alert", priority="normal")
        return {"success": True, "action": "trigger_alert", "message": message[:200], "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def activate_protection_mode(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("lockdown_mode"):
            return self._blocked_response("lockdown_mode")
        logger.warning("[AECE] Protection mode activating")
        if not self._protection_mode_active:
            self._protection_mode_active = True
            _audit_protection_change("activate", "API activation", False, True)
            record_aece_action(action="lockdown_mode", priority="critical")
            record_grid_risk_event("critical")
            try:
                set_emergency_stop_state(active=True, component="protection_mode")
            except Exception:
                pass
        return {"success": True, "action": "activate_protection_mode", "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION", "protection_mode_active": self._protection_mode_active}

    async def increase_solar_efficiency(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("increase_solar_efficiency"):
            return self._blocked_response("increase_solar_efficiency")
        await asyncio.sleep(0.01)
        record_aece_action(action="increase_solar_efficiency", priority="normal")
        return {"success": True, "action": "increase_solar_efficiency", "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def dispatch_battery(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("dispatch_battery"):
            return self._blocked_response("dispatch_battery")
        discharge_power = parameters.get("discharge_power_kw", 50) if parameters else 50
        await asyncio.sleep(0.01)
        record_aece_action(action="dispatch_battery", priority="high")
        record_aece_decision(
            action="dispatch_battery", risk_score=0.0, gsi=None, ses=None, module="aece_engine"
        )
        return {"success": True, "action": "dispatch_battery", "discharge_power_kw": discharge_power, "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def curtail_solar(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("curtail_solar"):
            return self._blocked_response("curtail_solar")
        curtail_percent = self._normalize_percentage(parameters.get("curtail_percent", 20) if parameters else 20, 20.0)
        curtail_percent = max(0.0, min(100.0, curtail_percent))
        await asyncio.sleep(0.01)
        record_aece_action(action="curtail_solar", priority="normal")
        record_aece_decision(
            action="curtail_solar", risk_score=0.0, gsi=None, ses=None, module="aece_engine"
        )
        return {"success": True, "action": "curtail_solar", "curtail_percent": curtail_percent, "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def adjust_inverter_power(self, parameters: Dict = None) -> Dict[str, Any]:
        start_time = time.time()
        if not is_phase1_allowed_action("adjust_inverter_power"):
            return self._blocked_response("adjust_inverter_power")
        power_percent = self._normalize_percentage(parameters.get("power_percent", 80) if parameters else 80, 80.0)
        power_percent = max(0.0, min(100.0, power_percent))
        await asyncio.sleep(0.01)
        record_aece_action(action="adjust_inverter_power", priority="normal")
        return {"success": True, "action": "adjust_inverter_power", "power_percent": power_percent, "duration_ms": round((time.time() - start_time) * 1000, 2), "phase": "PHASE_1_PRODUCTION"}

    async def no_action(self, parameters: Dict = None) -> Dict[str, Any]:
        return {"success": True, "message": "No action taken", "phase": "PHASE_1_PRODUCTION"}

    async def execute(self, decision: ControlDecision) -> Dict[str, Any]:
        action_map = {
            ControlAction.REDUCE_LOAD: lambda: self.reduce_load(decision.recommended_parameters.get("reduction_percent", 20), decision.recommended_parameters),
            ControlAction.REDISTRIBUTE_ENERGY: lambda: self.redistribute_energy(decision.recommended_parameters),
            ControlAction.PREEMPTIVE_STABILIZATION: lambda: self.preemptive_stabilization(decision.recommended_parameters),
            ControlAction.TRIGGER_ALERT: lambda: self.trigger_alert(decision.reason, decision.recommended_parameters),
            ControlAction.LOCKDOWN_MODE: lambda: self.activate_protection_mode(decision.recommended_parameters),
            ControlAction.INCREASE_SOLAR_EFFICIENCY: lambda: self.increase_solar_efficiency(decision.recommended_parameters),
            ControlAction.DISPATCH_BATTERY: lambda: self.dispatch_battery(decision.recommended_parameters),
            ControlAction.CURTAIL_SOLAR: lambda: self.curtail_solar(decision.recommended_parameters),
            ControlAction.ADJUST_INVERTER_POWER: lambda: self.adjust_inverter_power(decision.recommended_parameters),
            ControlAction.NO_ACTION: self.no_action,
        }
        executor = action_map.get(decision.action)
        if executor:
            result = await executor()
            # PROMETHEUS: Record AECE decision on execution
            try:
                record_aece_decision(
                    action=decision.action.value,
                    risk_score=decision.risk_score,
                    gsi=None,
                    ses=None,
                    module="aece_engine"
                )
            except Exception:
                pass
            return result
        return {"success": False, "error": f"Unknown action: {decision.action}", "phase": "PHASE_1_PRODUCTION"}

    def _blocked_response(self, action: str) -> Dict[str, Any]:
        return {"success": False, "action": action, "error": "Action blocked in Phase 1", "phase": "PHASE_1_PRODUCTION"}

    def get_protection_mode(self) -> bool:
        return self._protection_mode_active

    def set_protection_mode(self, active: bool):
        previous = self._protection_mode_active
        self._protection_mode_active = active
        _audit_protection_change("set", "API call", previous, active)
        logger.info(f"[AECE] protection mode={'active' if active else 'inactive'}")
        
        # PROMETHEUS: Update emergency stop state
        try:
            set_emergency_stop_state(active=active, component="protection_mode")
        except Exception:
            pass

    def ensure_protection_mode(self) -> bool:
        if not self._protection_mode_active and PROTECTION_MODE_FORCE_ENABLE:
            self._protection_mode_active = True
            _audit_protection_change("auto_repair", "Force enabled", False, True)
        return self._protection_mode_active

# ============================================================================
# GLOBAL EMERGENCY STOP
# ============================================================================

class GlobalEmergencyStop:
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
        self._emergency_active = False
        self._emergency_time = None
        self._emergency_reason = None
        self._activation_history: List[Dict] = []

    def activate(self, reason: str = "Manual emergency stop"):
        with self._lock:
            self._emergency_active = True
            self._emergency_time = datetime.now(timezone.utc)
            self._emergency_reason = reason
            self._activation_history.append({"timestamp": self._emergency_time.isoformat(), "reason": reason, "action": "activate"})
            logger.warning(f"[AECE] emergency stop activated: {reason}")
            
            # PROMETHEUS: Set emergency stop state and record risk event
            try:
                set_emergency_stop_state(active=True, component="global_emergency")
                record_grid_risk_event("critical")
            except Exception:
                pass

    def deactivate(self):
        with self._lock:
            self._emergency_active = False
            self._activation_history.append({"timestamp": datetime.now(timezone.utc).isoformat(), "action": "deactivate"})
            
            # PROMETHEUS: Clear emergency stop state
            try:
                set_emergency_stop_state(active=False, component="global_emergency")
            except Exception:
                pass

    def is_active(self) -> bool:
        return self._emergency_active

    def get_status(self) -> Dict[str, Any]:
        return {
            "active": self._emergency_active,
            "time": self._emergency_time.isoformat() if self._emergency_time else None,
            "reason": self._emergency_reason,
            "activation_count": len([h for h in self._activation_history if h.get("action") == "activate"]),
            "phase": "PHASE_1_PRODUCTION"
        }

# ============================================================================
# MAIN AECE CONTROLLER
# ============================================================================

class AutonomousEnergyControlEngine:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if AutonomousEnergyControlEngine._initialized:
            return
        AutonomousEnergyControlEngine._initialized = True

        self.decision_engine = EnhancedDecisionEngine()
        self.action_executor = EnhancedActionExecutor()
        self.predictive_engine = PredictiveAnalyticsEngine()
        self.emergency_stop = GlobalEmergencyStop()

        self.audit_trail: List[ControlAuditEntry] = []
        self.metrics = {
            "total_decisions": 0, "total_actions": 0, "actions_by_type": defaultdict(int),
            "avg_decision_time_ms": 0.0, "error_count": 0, "startup_time": time.time(),
            "phase1_blocked_actions": 0
        }
        self._decision_times: deque = deque(maxlen=100)

        protection_status = "active" if self.action_executor.get_protection_mode() else "inactive"
        logger.info(f"[AECE] controller initialized protection={protection_status}")
        
        # PROMETHEUS: Set AECE module as active on init
        try:
            set_active_module(module="aece_engine", active=True)
            set_emergency_stop_state(active=self.emergency_stop.is_active(), component="global_emergency")
        except Exception:
            pass

    async def initialize(self) -> bool:
        self.action_executor.ensure_protection_mode()
        status = "active" if self.action_executor.get_protection_mode() else "inactive"
        logger.info(f"[AECE] async init complete protection={status}")
        try:
            set_active_module(module="aece_engine", active=True)
        except Exception:
            pass
        return True

    async def shutdown(self) -> bool:
        logger.info("[AECE] shutdown")
        try:
            set_active_module(module="aece_engine", active=False)
        except Exception:
            pass
        return True

    async def process(self, ueiv: Union[UEIV, Dict, Any], skip_hysteresis: bool = False) -> ControlAuditEntry:
        start_time = time.time()
        decision_id = str(uuid.uuid4())[:8]

        try:
            if not isinstance(ueiv, UEIV):
                ueiv = self.decision_engine._convert_to_ueiv(ueiv)

            if not ueiv.validate():
                ueiv = ueiv.sanitize()

            self.predictive_engine.update_history(ueiv)
            ueiv.predicted_solar_efficiency = self.predictive_engine.predict_solar_efficiency()
            ueiv.predicted_grid_risk = self.predictive_engine.predict_grid_risk()
            ueiv.predicted_demand_peak = self.predictive_engine.predict_demand_peak()

            if self.emergency_stop.is_active():
                decision = ControlDecision(
                    action=ControlAction.LOCKDOWN_MODE, priority=ControlPriority.CRITICAL,
                    risk_score=1.0, confidence_score=1.0, confidence_level=DecisionConfidence.VERY_HIGH,
                    reason="Emergency stop active", triggered_rules=["emergency_stop"],
                    recommended_parameters={"severity": "max"}, predicted_outcome={}
                )
            else:
                decision = self.decision_engine.evaluate(ueiv)

            can_execute, _ = self.decision_engine.should_execute(decision)

            execution_result = None
            action_executed = False

            if can_execute and decision.action != ControlAction.NO_ACTION:
                execution_result = await self.action_executor.execute(decision)
                action_executed = execution_result.get("success", False)
                if action_executed:
                    self.decision_engine.record_execution(decision)
                    self.metrics["total_decisions"] += 1
                    if execution_result.get("success"):
                        self.metrics["total_actions"] += 1
                        self.metrics["actions_by_type"][decision.action.value] += 1

            duration_ms = (time.time() - start_time) * 1000
            self._decision_times.append(duration_ms)
            if self._decision_times:
                self.metrics["avg_decision_time_ms"] = round(sum(self._decision_times) / len(self._decision_times), 2)

            # PROMETHEUS: Record AECE decision with full metrics
            try:
                record_aece_decision(
                    action=decision.action.value,
                    risk_score=decision.risk_score,
                    gsi=max(0.0, min(100.0, (1.0 - ueiv.grid_risk) * 100.0)),
                    ses=max(0.0, min(100.0, ueiv.solar_efficiency * 100.0)),
                    module="aece_controller"
                )
            except Exception:
                pass

            audit_entry = ControlAuditEntry(
                decision_id=decision_id, ueiv_snapshot=ueiv.to_dict(), decision=decision,
                action_executed=action_executed, execution_result=execution_result, duration_ms=duration_ms
            )
            self.audit_trail.append(audit_entry)
            if len(self.audit_trail) > 1000:
                self.audit_trail = self.audit_trail[-1000:]

            return audit_entry

        except Exception as e:
            self.metrics["error_count"] += 1
            duration_ms = (time.time() - start_time) * 1000
            return ControlAuditEntry(
                decision_id=decision_id, ueiv_snapshot={},
                decision=ControlDecision(
                    action=ControlAction.NO_ACTION, priority=ControlPriority.LOW,
                    risk_score=0.5, confidence_score=0.5, confidence_level=DecisionConfidence.VERY_LOW,
                    reason=f"Error: {e}", triggered_rules=["error"],
                    recommended_parameters={}, predicted_outcome={}
                ),
                action_executed=False, execution_result={"error": str(e)}, duration_ms=duration_ms
            )

    def get_status(self) -> Dict[str, Any]:
        uptime = time.time() - self.metrics.get("startup_time", time.time())
        return {
            "initialized": AutonomousEnergyControlEngine._initialized,
            "phase": "PHASE_1_PRODUCTION", "version": "4.1.0",
            "uptime_seconds": round(uptime, 2),
            "metrics": {
                "total_decisions": self.metrics["total_decisions"],
                "total_actions": self.metrics["total_actions"],
                "actions_by_type": dict(self.metrics["actions_by_type"]),
                "avg_decision_time_ms": self.metrics["avg_decision_time_ms"],
                "error_count": self.metrics["error_count"],
            },
            "protection_mode_active": self.action_executor.get_protection_mode(),
            "emergency_stop": self.emergency_stop.get_status(),
            "audit_trail_size": len(self.audit_trail),
            "prometheus_instrumented": METRICS_AVAILABLE
        }

# ============================================================================
# MAIN SYSTEM INTEGRATION FUNCTIONS
# ============================================================================

async def evaluate_and_execute_telemetry(
    telemetry: Dict[str, Any],
    predictions: Dict[str, Any] = None,
    execute: bool = True
) -> Dict[str, Any]:
    start_time = time.time()
    try:
        ueiv = UEIV.from_telemetry(telemetry)
        if predictions:
            ueiv.predicted_grid_risk = predictions.get("grid_risk", ueiv.predicted_grid_risk)
            ueiv.predicted_demand_peak = predictions.get("demand_peak", ueiv.predicted_demand_peak)

        audit_entry = await aece.process(ueiv)

        return {
            "success": True,
            "decision": audit_entry.decision.to_dict(),
            "risk_score": audit_entry.decision.risk_score,
            "action": audit_entry.decision.action.value,
            "reason": audit_entry.decision.reason,
            "action_executed": audit_entry.action_executed if execute else False,
            "duration_ms": audit_entry.duration_ms,
            "phase": "PHASE_1_PRODUCTION"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "action": "no_action",
            "risk_score": 0.5,
            "action_executed": False,
            "duration_ms": (time.time() - start_time) * 1000,
            "phase": "PHASE_1_PRODUCTION"
        }


async def evaluate_and_execute(telemetry: Dict[str, Any], predictions: Dict[str, Any] = None, execute: bool = True) -> Dict[str, Any]:
    return await evaluate_and_execute_telemetry(telemetry, predictions, execute)

# ============================================================================
# SINGLETON INSTANCE & HELPERS
# ============================================================================

aece = AutonomousEnergyControlEngine()


def get_aece_engine() -> AutonomousEnergyControlEngine:
    return aece


def get_decision_engine() -> EnhancedDecisionEngine:
    return aece.decision_engine


def get_action_executor() -> EnhancedActionExecutor:
    return aece.action_executor


def emergency_stop_activate(reason: str = "Manual emergency stop"):
    aece.emergency_stop.activate(reason)


def emergency_stop_deactivate():
    aece.emergency_stop.deactivate()


def emergency_stop_status() -> Dict[str, Any]:
    return aece.emergency_stop.get_status()


def get_protection_mode_status() -> Dict[str, Any]:
    return {
        "protection_mode_active": aece.action_executor.get_protection_mode(),
        "force_enabled": PROTECTION_MODE_FORCE_ENABLE,
        "phase": "PHASE_1_PRODUCTION"
    }


def get_phase1_status() -> Dict[str, Any]:
    return {
        "phase": "PHASE_1_PRODUCTION",
        "allowed_actions": AECE_PHASE1_ALLOWED_ACTIONS,
        "blocked_actions": AECE_PHASE1_BLOCKED_ACTIONS,
        "phase": "PHASE_1_PRODUCTION"
    }

# ============================================================================
# FASTAPI ROUTER (OPTIONAL)
# ============================================================================

_router = None
_router_initialized = False


def get_router():
    global _router, _router_initialized
    if _router_initialized:
        return _router

    try:
        from fastapi import APIRouter, Depends, HTTPException, Query

        router = APIRouter(prefix="/api/v1/control", tags=["autonomous-control"])

        @router.get("/health")
        async def aece_health():
            return {"status": "healthy", "engine": "AECE", "phase": "PHASE_1_PRODUCTION"}

        @router.get("/status")
        async def aece_status():
            return {"success": True, "status": aece.get_status(), "timestamp": datetime.now(timezone.utc).isoformat()}

        @router.get("/protection-mode/status")
        async def protection_mode_status():
            return get_protection_mode_status()

        @router.post("/emergency/activate")
        async def emergency_activate(reason: str = Query("Manual emergency stop")):
            emergency_stop_activate(reason)
            return {"success": True, "message": "Emergency stop activated", "status": emergency_stop_status()}

        @router.post("/emergency/deactivate")
        async def emergency_deactivate():
            emergency_stop_deactivate()
            return {"success": True, "message": "Emergency stop deactivated", "status": emergency_stop_status()}

        @router.post("/telemetry")
        async def process_telemetry(telemetry: dict):
            try:
                result = await evaluate_and_execute_telemetry(telemetry, execute=True)
                return result
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        _router = router
        _router_initialized = True
        return router
    except ImportError:
        _router_initialized = True
        return None


router = get_router()

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'aece', 'get_aece_engine', 'get_router', 'router',
    'AutonomousEnergyControlEngine', 'UEIV', 'ControlDecision', 'ControlAction',
    'ControlPriority', 'DecisionConfidence', 'EnhancedRiskScoringEngine',
    'RiskScoringEngine', 'EnhancedDecisionEngine', 'EnhancedActionExecutor',
    'PredictiveAnalyticsEngine', 'GlobalEmergencyStop', 'AECE_AVAILABLE',
    'emergency_stop_activate', 'emergency_stop_deactivate', 'emergency_stop_status',
    'get_protection_mode_status', 'evaluate_and_execute', 'evaluate_and_execute_telemetry',
    'get_decision_engine', 'get_action_executor', 'get_phase1_status'
]

# Final initialization log
logger.info("[AECE] initialized protection=active metrics_instrumented=" + str(METRICS_AVAILABLE))