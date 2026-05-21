
import time
import logging
import threading
import math
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import Prometheus metrics
try:
    from prometheus_client import Gauge, Counter, Histogram, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("[OptimizationMetrics] Prometheus client not available")


# ============================================================================
# NULL METRIC FOR FALLBACK
# ============================================================================

class NullMetric:
    """Null object pattern for when Prometheus metrics are not available or already exist"""
    
    def __init__(self, *args, **kwargs):
        pass
    
    def labels(self, *args, **kwargs):
        return self
    
    def set(self, value):
        pass
    
    def inc(self, amount=1):
        pass
    
    def dec(self, amount=1):
        pass
    
    def observe(self, value):
        pass
    
    def time(self):
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


# ============================================================================
# PROMETHEUS METRICS (with duplicate protection)
# ============================================================================

# Thread lock for metric registration
_metric_registration_lock = threading.RLock()
_registered_metrics = set()


def register_metric_safe(metric_class, name: str, documentation: str, 
                         labelnames: List[str] = None, **kwargs):
    """
    Safely register a Prometheus metric, avoiding duplicates.
    
    Args:
        metric_class: Prometheus metric class (Gauge, Counter, Histogram)
        name: Metric name
        documentation: Metric documentation string
        labelnames: List of label names (optional)
        **kwargs: Additional arguments for metric creation
    
    Returns:
        Metric instance or NullMetric if registration fails
    """
    if not PROMETHEUS_AVAILABLE:
        return NullMetric()
    
    with _metric_registration_lock:
        metric_key = name
        
        # Check local cache first
        if metric_key in _registered_metrics:
            logger.debug(f"[OptimizationMetrics] Metric {name} already registered (cache) - using NullMetric")
            return NullMetric()
        
        try:
            # Check if metric already exists in registry
            existing_metrics = []
            if hasattr(REGISTRY, '_names_to_collectors'):
                existing_metrics = list(REGISTRY._names_to_collectors.keys())
            elif hasattr(REGISTRY, 'collect'):
                for collector in REGISTRY.collect():
                    if hasattr(collector, 'name'):
                        existing_metrics.append(collector.name)
                    elif hasattr(collector, '_name'):
                        existing_metrics.append(collector._name)
            
            if name in existing_metrics:
                logger.debug(f"[OptimizationMetrics] Metric {name} already exists in registry - using NullMetric")
                _registered_metrics.add(metric_key)
                return NullMetric()
            
            # Create the metric
            if labelnames:
                metric = metric_class(name, documentation, labelnames, **kwargs)
            else:
                metric = metric_class(name, documentation, **kwargs)
            
            _registered_metrics.add(metric_key)
            logger.debug(f"[OptimizationMetrics] Successfully registered metric: {name}")
            return metric
            
        except ValueError as e:
            if "Duplicated" in str(e) or "already exists" in str(e):
                logger.debug(f"[OptimizationMetrics] Metric {name} already exists (ValueError) - using NullMetric")
                _registered_metrics.add(metric_key)
            else:
                logger.warning(f"[OptimizationMetrics] ValueError creating metric {name}: {e}")
            return NullMetric()
        except Exception as e:
            logger.warning(f"[OptimizationMetrics] Failed to create metric {name}: {e}")
            return NullMetric()


# Register Prometheus metrics with duplicate protection
if PROMETHEUS_AVAILABLE:
    try:
        # Grid stability gauge
        grid_stability_gauge = register_metric_safe(
            Gauge,
            'neurobridge_grid_stability_score',
            'Current grid stability score (0-100)'
        )
        
        # Solar efficiency gauge
        solar_efficiency_gauge = register_metric_safe(
            Gauge,
            'neurobridge_solar_efficiency_score',
            'Current solar efficiency score (0-100)'
        )
        
        # Optimization score gauge
        optimization_score_gauge = register_metric_safe(
            Gauge,
            'neurobridge_optimization_score',
            'Current composite optimization score (0-100)'
        )
        
        # Risk score gauge
        risk_score_gauge = register_metric_safe(
            Gauge,
            'neurobridge_risk_score',
            'Current risk score (0-1)'
        )
        
        # Optimization gain counter
        optimization_gain_counter = register_metric_safe(
            Counter,
            'neurobridge_optimization_gain_total',
            'Total optimization gain accumulated',
            ['action_type']
        )
        
        # Decision latency histogram
        decision_latency = register_metric_safe(
            Histogram,
            'neurobridge_decision_latency_ms',
            'Decision processing latency in milliseconds',
            buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000]
        )
        
        logger.info("[OptimizationMetrics] Prometheus metrics registered successfully")
        
    except Exception as e:
        logger.warning(f"[OptimizationMetrics] Prometheus setup error: {e}")
        # Set all metrics to NullMetric fallbacks
        grid_stability_gauge = NullMetric()
        solar_efficiency_gauge = NullMetric()
        optimization_score_gauge = NullMetric()
        risk_score_gauge = NullMetric()
        optimization_gain_counter = NullMetric()
        decision_latency = NullMetric()
else:
    # Create null metrics when Prometheus is not available
    grid_stability_gauge = NullMetric()
    solar_efficiency_gauge = NullMetric()
    optimization_score_gauge = NullMetric()
    risk_score_gauge = NullMetric()
    optimization_gain_counter = NullMetric()
    decision_latency = NullMetric()


# ============================================================================
# METRIC DEFINITIONS
# ============================================================================

class MetricTrend(str, Enum):
    """Trend direction for metrics"""
    IMPROVING = "improving"
    DEGRADING = "degrading"
    STABLE = "stable"


class DataSource(str, Enum):
    """Source of telemetry data"""
    HARDWARE = "hardware"
    API_LIVE = "api_live"
    API_CACHED = "api_cached"
    SYNTHETIC = "synthetic"
    FALLBACK = "fallback"


@dataclass
class MetricSnapshot:
    """Point-in-time snapshot of optimization metrics"""
    timestamp: float
    grid_stability_score: float
    solar_efficiency_score: float
    optimization_score: float
    risk_score: float
    active_power_kw: float
    grid_frequency_hz: float
    solar_output_kw: float
    demand_load_kw: float
    data_source: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "grid_stability_score": round(self.grid_stability_score, 1),
            "solar_efficiency_score": round(self.solar_efficiency_score, 1),
            "optimization_score": round(self.optimization_score, 1),
            "risk_score": round(self.risk_score, 3),
            "active_power_kw": round(self.active_power_kw, 1),
            "grid_frequency_hz": round(self.grid_frequency_hz, 2),
            "solar_output_kw": round(self.solar_output_kw, 1),
            "demand_load_kw": round(self.demand_load_kw, 1),
            "data_source": self.data_source
        }
    
    def get_improvement_from(self, other: 'MetricSnapshot') -> Dict[str, float]:
        """Calculate improvement from another snapshot"""
        return {
            "grid_stability": self.grid_stability_score - other.grid_stability_score,
            "solar_efficiency": self.solar_efficiency_score - other.solar_efficiency_score,
            "optimization": self.optimization_score - other.optimization_score,
            "risk_reduction": other.risk_score - self.risk_score
        }


@dataclass
class OptimizationImpact:
    """Record of an optimization action's impact"""
    action_id: str
    action_type: str
    before_metrics: MetricSnapshot
    after_metrics: MetricSnapshot
    grid_improvement: float
    solar_improvement: float
    overall_improvement: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "before": self.before_metrics.to_dict(),
            "after": self.after_metrics.to_dict(),
            "improvement": {
                "grid_stability": round(self.grid_improvement, 1),
                "solar_efficiency": round(self.solar_improvement, 1),
                "overall": round(self.overall_improvement, 1)
            }
        }
    
    def get_improvement_percent(self) -> float:
        """Get percentage improvement in overall score"""
        if self.before_metrics.optimization_score == 0:
            return 0.0
        return (self.overall_improvement / abs(self.before_metrics.optimization_score)) * 100


# ============================================================================
# OPTIMIZATION METRICS ENGINE
# ============================================================================

class OptimizationMetricsEngine:
    """
    Single source of truth for energy optimization metrics.
    
    Calculates:
    - grid_stability_score: Based on frequency deviation and load-supply balance
    - solar_efficiency_score: Based on actual vs expected solar output
    - optimization_score: Weighted combination of grid + solar scores
    
    All calculations are mathematically consistent with real physics.
    
    Features:
    - Thread-safe singleton pattern
    - Prometheus metrics integration (with duplicate protection)
    - Real-time trend analysis
    - Impact tracking with before/after comparisons
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
        self._current_snapshot: Optional[MetricSnapshot] = None
        self._previous_snapshot: Optional[MetricSnapshot] = None
        self._impact_history: deque = deque(maxlen=100)
        self._optimization_history: deque = deque(maxlen=1000)
        
        # Weights for optimization score (configurable)
        self.grid_weight = 0.6
        self.solar_weight = 0.4
        
        # Target values for scoring
        self.target_frequency_hz = 50.0
        self.frequency_tolerance_hz = 0.5
        self.target_voltage_v = 230.0
        
        # Physical constants
        self.temp_coefficient = 0.004  # -0.4% per °C
        self.stc_irradiance = 1000.0   # W/m²
        
        # Performance tracking
        self._total_calculations = 0
        self._calculation_errors = 0
        
        logger.info("[OptimizationMetrics] Engine initialized v2.1.0")
        logger.info(f"[OptimizationMetrics] Weights: Grid={self.grid_weight}, Solar={self.solar_weight}")
        logger.info(f"[OptimizationMetrics] Prometheus available: {PROMETHEUS_AVAILABLE}")
    
    # ========================================================================
    # CORE METRIC CALCULATIONS (Mathematically Consistent)
    # ========================================================================
    
    def calculate_grid_stability_score(
        self,
        frequency_hz: float,
        active_power_kw: float,
        demand_load_kw: float,
        voltage_v: float = 230.0
    ) -> float:
        """
        Calculate grid stability score (0-100).
        
        Formula:
        - Base score starts at 100
        - Penalty for frequency deviation from 50Hz (exponential)
        - Penalty for load-supply imbalance (linear)
        - Penalty for voltage deviation from 230V (linear)
        
        Returns:
            Score between 0 and 100
        """
        self._total_calculations += 1
        
        try:
            # Frequency deviation penalty (exponential)
            freq_deviation = abs(frequency_hz - self.target_frequency_hz)
            if freq_deviation <= 0.1:
                freq_penalty = 0
            elif freq_deviation <= 0.2:
                freq_penalty = (freq_deviation - 0.1) / 0.1 * 10
            elif freq_deviation <= 0.5:
                freq_penalty = 10 + (freq_deviation - 0.2) / 0.3 * 20
            else:
                freq_penalty = 30 + min(20, (freq_deviation - 0.5) / 0.5 * 20)
            freq_penalty = min(40, freq_penalty)
            
            # Load-supply imbalance penalty
            if demand_load_kw > 0:
                imbalance_ratio = abs(active_power_kw - demand_load_kw) / max(demand_load_kw, 1.0)
                imbalance_penalty = min(30, imbalance_ratio * 50)
            else:
                imbalance_penalty = 0
            
            # Voltage deviation penalty
            voltage_deviation = abs(voltage_v - self.target_voltage_v) / self.target_voltage_v
            voltage_penalty = min(20, voltage_deviation * 50)
            
            # Calculate final score
            raw_score = 100 - (freq_penalty + imbalance_penalty + voltage_penalty)
            score = max(0.0, min(100.0, raw_score))
            
            # Update Prometheus metric (safe check)
            if grid_stability_gauge and not isinstance(grid_stability_gauge, NullMetric):
                grid_stability_gauge.set(score)
            
            return score
            
        except Exception as e:
            self._calculation_errors += 1
            logger.error(f"[OptimizationMetrics] Grid stability calculation error: {e}")
            return 50.0  # Neutral fallback
    
    def calculate_solar_efficiency_score(
        self,
        actual_output_kw: float,
        expected_output_kw: float,
        irradiance_wm2: float = 850.0,
        temperature_c: float = 25.0
    ) -> float:
        """
        Calculate solar efficiency score (0-100).
        
        Formula:
        - Base: actual / expected (capped at 1.0)
        - Temperature derating factor
        - Irradiance quality factor
        
        Returns:
            Score between 0 and 100
        """
        self._total_calculations += 1
        
        try:
            if expected_output_kw <= 0:
                return 50.0  # Neutral score when no expectation
            
            # Basic efficiency ratio
            efficiency_ratio = min(1.0, actual_output_kw / expected_output_kw)
            
            # Temperature derating (standard PV: -0.4%/°C above 25°C)
            if temperature_c > 25:
                temp_derate = 1.0 - ((temperature_c - 25) * self.temp_coefficient)
            else:
                temp_derate = 1.0
            temp_derate = max(0.5, min(1.0, temp_derate))
            
            # Irradiance quality (standard test condition: 1000 W/m²)
            irradiance_quality = min(1.0, irradiance_wm2 / self.stc_irradiance)
            
            # Combined efficiency score
            efficiency_score = efficiency_ratio * temp_derate * irradiance_quality * 100
            
            score = max(0.0, min(100.0, efficiency_score))
            
            # Update Prometheus metric (safe check)
            if solar_efficiency_gauge and not isinstance(solar_efficiency_gauge, NullMetric):
                solar_efficiency_gauge.set(score)
            
            return score
            
        except Exception as e:
            self._calculation_errors += 1
            logger.error(f"[OptimizationMetrics] Solar efficiency calculation error: {e}")
            return 50.0  # Neutral fallback
    
    def calculate_risk_score(
        self,
        grid_stability: float,
        solar_efficiency: float,
        demand_trend: float = 0.0
    ) -> float:
        """
        Calculate composite risk score (0-1).
        
        Formula:
        - Inverse of normalized grid stability
        - Weighted with solar efficiency deficit
        - Demand trend amplification
        
        Returns:
            Risk score between 0 and 1
        """
        try:
            # Normalize grid stability (0-100 to 0-1, invert)
            grid_risk = (100 - grid_stability) / 100
            
            # Solar risk (low efficiency = higher risk)
            solar_risk = (100 - solar_efficiency) / 100
            
            # Weighted composite (grid is primary, solar is secondary)
            composite_risk = (grid_risk * 0.7) + (solar_risk * 0.3)
            
            # Amplify by demand trend (increasing demand increases risk)
            if demand_trend > 0:
                composite_risk *= (1 + min(0.3, demand_trend))
            
            risk = min(1.0, max(0.0, composite_risk))
            
            # Update Prometheus metric (safe check)
            if risk_score_gauge and not isinstance(risk_score_gauge, NullMetric):
                risk_score_gauge.set(risk)
            
            return risk
            
        except Exception as e:
            self._calculation_errors += 1
            logger.error(f"[OptimizationMetrics] Risk score calculation error: {e}")
            return 0.5  # Neutral fallback
    
    def calculate_optimization_score(
        self,
        grid_stability: float,
        solar_efficiency: float
    ) -> float:
        """
        Calculate unified optimization score (0-100).
        
        Weighted combination of grid stability and solar efficiency.
        
        Returns:
            Optimization score between 0 and 100
        """
        try:
            score = (grid_stability * self.grid_weight) + (solar_efficiency * self.solar_weight)
            score = max(0.0, min(100.0, score))
            
            # Update Prometheus metric (safe check)
            if optimization_score_gauge and not isinstance(optimization_score_gauge, NullMetric):
                optimization_score_gauge.set(score)
            
            return score
            
        except Exception as e:
            self._calculation_errors += 1
            logger.error(f"[OptimizationMetrics] Optimization score calculation error: {e}")
            return 50.0  # Neutral fallback
    
    # ========================================================================
    # METRIC SNAPSHOT MANAGEMENT
    # ========================================================================
    
    def capture_snapshot(
        self,
        active_power_kw: float,
        grid_frequency_hz: float,
        demand_load_kw: float,
        solar_output_kw: float,
        expected_solar_kw: float,
        voltage_v: float = 230.0,
        irradiance_wm2: float = 850.0,
        temperature_c: float = 25.0,
        data_source: str = "unknown"
    ) -> MetricSnapshot:
        """
        Capture a complete metric snapshot from telemetry data.
        
        Args:
            active_power_kw: Current active power output (kW)
            grid_frequency_hz: Grid frequency (Hz)
            demand_load_kw: Current demand load (kW)
            solar_output_kw: Actual solar output (kW)
            expected_solar_kw: Expected solar output based on conditions (kW)
            voltage_v: Grid voltage (V)
            irradiance_wm2: Solar irradiance (W/m²)
            temperature_c: Ambient temperature (°C)
            data_source: Source of telemetry data
        
        Returns:
            MetricSnapshot with all calculated metrics
        """
        start_time = time.time()
        
        grid_stability = self.calculate_grid_stability_score(
            frequency_hz=grid_frequency_hz,
            active_power_kw=active_power_kw,
            demand_load_kw=demand_load_kw,
            voltage_v=voltage_v
        )
        
        solar_efficiency = self.calculate_solar_efficiency_score(
            actual_output_kw=solar_output_kw,
            expected_output_kw=expected_solar_kw,
            irradiance_wm2=irradiance_wm2,
            temperature_c=temperature_c
        )
        
        optimization_score = self.calculate_optimization_score(
            grid_stability=grid_stability,
            solar_efficiency=solar_efficiency
        )
        
        risk_score = self.calculate_risk_score(
            grid_stability=grid_stability,
            solar_efficiency=solar_efficiency
        )
        
        snapshot = MetricSnapshot(
            timestamp=time.time(),
            grid_stability_score=grid_stability,
            solar_efficiency_score=solar_efficiency,
            optimization_score=optimization_score,
            risk_score=risk_score,
            active_power_kw=active_power_kw,
            grid_frequency_hz=grid_frequency_hz,
            solar_output_kw=solar_output_kw,
            demand_load_kw=demand_load_kw,
            data_source=data_source
        )
        
        # Update history
        if self._current_snapshot:
            self._previous_snapshot = self._current_snapshot
        self._current_snapshot = snapshot
        self._optimization_history.append(optimization_score)
        
        # Record latency (safe check)
        latency_ms = (time.time() - start_time) * 1000
        if decision_latency and not isinstance(decision_latency, NullMetric):
            decision_latency.observe(latency_ms)
        
        logger.debug(
            f"[OptimizationMetrics] Snapshot captured | "
            f"GSI: {grid_stability:.1f} | SES: {solar_efficiency:.1f} | "
            f"Score: {optimization_score:.1f} | Source: {data_source} | "
            f"Latency: {latency_ms:.1f}ms"
        )
        
        return snapshot
    
    def get_current_metrics(self) -> Optional[Dict[str, Any]]:
        """Get current optimization metrics"""
        if self._current_snapshot:
            return self._current_snapshot.to_dict()
        return None
    
    def get_optimization_trend(self) -> MetricTrend:
        """Determine trend of optimization score"""
        if len(self._optimization_history) < 3:
            return MetricTrend.STABLE
        
        recent = list(self._optimization_history)[-5:]
        if len(recent) >= 2:
            first = recent[0]
            last = recent[-1]
            change = last - first
            
            if change > 2:
                return MetricTrend.IMPROVING
            elif change < -2:
                return MetricTrend.DEGRADING
        
        return MetricTrend.STABLE
    
    def get_improvement_summary(self) -> Dict[str, Any]:
        """Get summary of improvements from all actions"""
        if not self._impact_history:
            return {
                "total_improvement": 0.0,
                "average_improvement": 0.0,
                "best_improvement": 0.0,
                "total_actions": 0
            }
        
        improvements = [impact.overall_improvement for impact in self._impact_history]
        
        return {
            "total_improvement": round(sum(improvements), 1),
            "average_improvement": round(sum(improvements) / len(improvements), 1),
            "best_improvement": round(max(improvements), 1),
            "total_actions": len(self._impact_history)
        }
    
    # ========================================================================
    # IMPACT TRACKING
    # ========================================================================
    
    def record_action_impact(
        self,
        action_id: str,
        action_type: str,
        before: MetricSnapshot,
        after: MetricSnapshot
    ) -> OptimizationImpact:
        """
        Record the impact of an AECE action.
        Calculates improvement deltas.
        
        Args:
            action_id: Unique identifier for the action
            action_type: Type of action taken (e.g., 'load_balancing')
            before: Metrics before action
            after: Metrics after action
        
        Returns:
            OptimizationImpact with calculated improvements
        """
        grid_improvement = after.grid_stability_score - before.grid_stability_score
        solar_improvement = after.solar_efficiency_score - before.solar_efficiency_score
        overall_improvement = after.optimization_score - before.optimization_score
        
        impact = OptimizationImpact(
            action_id=action_id,
            action_type=action_type,
            before_metrics=before,
            after_metrics=after,
            grid_improvement=grid_improvement,
            solar_improvement=solar_improvement,
            overall_improvement=overall_improvement,
            timestamp=time.time()
        )
        
        self._impact_history.append(impact)
        
        # Update Prometheus counter (safe check)
        if optimization_gain_counter and not isinstance(optimization_gain_counter, NullMetric) and overall_improvement > 0:
            optimization_gain_counter.labels(action_type=action_type).inc(overall_improvement)
        
        # Log the impact clearly with before/after comparison
        improvement_percent = impact.get_improvement_percent()
        log_msg = (
            f"[OPTIMIZATION] Action '{action_type}' impact | "
            f"Grid: {before.grid_stability_score:.1f} → {after.grid_stability_score:.1f} "
            f"({'+' if grid_improvement >= 0 else ''}{grid_improvement:.1f}) | "
            f"Solar: {before.solar_efficiency_score:.1f} → {after.solar_efficiency_score:.1f} "
            f"({'+' if solar_improvement >= 0 else ''}{solar_improvement:.1f}) | "
            f"Overall: {before.optimization_score:.1f} → {after.optimization_score:.1f} "
            f"({'+' if overall_improvement >= 0 else ''}{overall_improvement:.1f}) | "
            f"Improvement: {improvement_percent:+.1f}% | "
            f"Source: {after.data_source}"
        )
        
        if overall_improvement > 0:
            logger.info(log_msg)
        elif overall_improvement < 0:
            logger.warning(log_msg)
        else:
            logger.debug(log_msg)
        
        return impact
    
    def get_recent_impacts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent optimization impacts"""
        return [impact.to_dict() for impact in list(self._impact_history)[-limit:]]
    
    def get_total_optimization_gain(self) -> float:
        """Calculate total optimization gain from all actions"""
        if not self._impact_history:
            return 0.0
        return sum(impact.overall_improvement for impact in self._impact_history)
    
    def get_average_optimization_gain(self) -> float:
        """Calculate average optimization gain per action"""
        if not self._impact_history:
            return 0.0
        return self.get_total_optimization_gain() / len(self._impact_history)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive optimization statistics"""
        current = self.get_current_metrics()
        
        return {
            "current": current,
            "trend": self.get_optimization_trend().value,
            "total_actions": len(self._impact_history),
            "total_optimization_gain": round(self.get_total_optimization_gain(), 1),
            "average_gain_per_action": round(self.get_average_optimization_gain(), 1),
            "recent_impacts": self.get_recent_impacts(5),
            "weights": {
                "grid_weight": self.grid_weight,
                "solar_weight": self.solar_weight
            },
            "performance": {
                "total_calculations": self._total_calculations,
                "calculation_errors": self._calculation_errors,
                "error_rate": round(self._calculation_errors / max(self._total_calculations, 1) * 100, 2)
            },
            "prometheus_available": PROMETHEUS_AVAILABLE,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def update_weights(self, grid_weight: float, solar_weight: float) -> None:
        """
        Update optimization weights.
        
        Args:
            grid_weight: Weight for grid stability (0-1)
            solar_weight: Weight for solar efficiency (0-1)
        """
        if abs(grid_weight + solar_weight - 1.0) > 0.01:
            logger.warning(f"[OptimizationMetrics] Weights don't sum to 1: {grid_weight} + {solar_weight} = {grid_weight + solar_weight}")
        
        self.grid_weight = max(0.0, min(1.0, grid_weight))
        self.solar_weight = max(0.0, min(1.0, solar_weight))
        
        # Normalize
        total = self.grid_weight + self.solar_weight
        if total > 0:
            self.grid_weight /= total
            self.solar_weight /= total
        
        logger.info(f"[OptimizationMetrics] Weights updated: Grid={self.grid_weight:.2f}, Solar={self.solar_weight:.2f}")
    
    def get_metrics_health(self) -> Dict[str, Any]:
        """Get health status of metrics engine"""
        return {
            "initialized": self._initialized,
            "has_current_snapshot": self._current_snapshot is not None,
            "total_snapshots": len(self._optimization_history),
            "total_impacts": len(self._impact_history),
            "current_optimization_score": self._current_snapshot.optimization_score if self._current_snapshot else None,
            "calculation_error_rate": round(self._calculation_errors / max(self._total_calculations, 1) * 100, 2),
            "prometheus_available": PROMETHEUS_AVAILABLE,
            "registered_metrics_count": len(_registered_metrics),
            "weights": {
                "grid": self.grid_weight,
                "solar": self.solar_weight
            }
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_metrics_engine: Optional[OptimizationMetricsEngine] = None


def get_metrics_engine() -> OptimizationMetricsEngine:
    """Get the global optimization metrics engine singleton"""
    global _metrics_engine
    if _metrics_engine is None:
        _metrics_engine = OptimizationMetricsEngine()
        logger.info("[OptimizationMetrics] Global instance created")
    return _metrics_engine


def reset_metrics_engine():
    """Reset the metrics engine singleton (for testing)"""
    global _metrics_engine
    _metrics_engine = None
    logger.info("[OptimizationMetrics] Global instance reset")

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'OptimizationMetricsEngine',
    'MetricSnapshot',
    'OptimizationImpact',
    'MetricTrend',
    'DataSource',
    'get_metrics_engine',
    'reset_metrics_engine'
]