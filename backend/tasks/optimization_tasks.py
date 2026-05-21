"""
================================================================================
NeuroBridge 11D - Optimization Tasks (Phase 1 Production)
================================================================================
Purpose: Celery tasks for the core optimization loop
Priority: HIGH - Telemetry, Prediction
          MEDIUM - AECE Decisions
          LOW - Reporting
================================================================================
"""

import logging
import asyncio
from celery import Task
from backend.core.celery_app import celery_app, NeuroBridgeTask
from backend.core.optimization_metrics import get_metrics_engine
from backend.aece.decision_engine_v2 import get_decision_engine, TelemetrySnapshot, PredictionData
from backend.aece.action_executor_v2 import get_action_executor, ActionType

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="backend.tasks.optimization_tasks.process_telemetry",
    queue="energy_queue",
    priority=9,
    max_retries=3,
    time_limit=30,
    soft_time_limit=25
)
def process_telemetry(self, telemetry_data: dict) -> dict:
    """
    HIGH PRIORITY: Process incoming telemetry and update metrics.
    """
    try:
        metrics_engine = get_metrics_engine()
        decision_engine = get_decision_engine()
        
        # Create telemetry snapshot
        telemetry = TelemetrySnapshot(
            active_power_kw=telemetry_data.get("active_power_kw", 500.0),
            grid_frequency_hz=telemetry_data.get("grid_frequency_hz", 50.0),
            demand_load_kw=telemetry_data.get("demand_load_kw", 500.0),
            solar_output_kw=telemetry_data.get("solar_output_kw", 100.0),
            battery_soc_percent=telemetry_data.get("battery_soc_percent", 50.0),
            voltage_v=telemetry_data.get("voltage_v", 230.0),
            temperature_c=telemetry_data.get("temperature_c", 25.0)
        )
        
        # Create predictions (simplified for now)
        predictions = PredictionData(
            grid_stress_forecast=telemetry_data.get("grid_stress_forecast", 0.3),
            solar_forecast_kw=telemetry_data.get("solar_forecast_kw", 100.0),
            demand_forecast_kw=telemetry_data.get("demand_forecast_kw", 500.0),
            weather_severity=telemetry_data.get("weather_severity", 0.2)
        )
        
        # Evaluate decision
        decision = decision_engine.evaluate(telemetry, predictions)
        
        return {
            "success": True,
            "decision": decision.to_dict(),
            "task_id": self.request.id
        }
        
    except Exception as e:
        logger.error(f"process_telemetry failed: {e}")
        self.retry(exc=e, countdown=5)
        return {"success": False, "error": str(e)}


@celery_app.task(
    bind=True,
    name="backend.tasks.optimization_tasks.execute_decision",
    queue="control_queue",
    priority=8,
    max_retries=3,
    time_limit=60,
    soft_time_limit=50
)
def execute_decision(self, decision_data: dict) -> dict:
    """
    MEDIUM PRIORITY: Execute AECE decision and measure impact.
    """
    try:
        action_executor = get_action_executor()
        metrics_engine = get_metrics_engine()
        
        action_type = ActionType(decision_data.get("action", "no_action"))
        
        # Capture before snapshot
        before_snapshot = metrics_engine._current_snapshot
        
        # Execute action
        result = asyncio.run(
            action_executor.execute(
                action=action_type,
                telemetry=decision_data.get("telemetry", {}),
                params=decision_data.get("params", {})
            )
        )
        
        if result.success and before_snapshot:
            # Simulate after state (in production, this would be actual telemetry)
            # For now, apply impact to simulate improvement
            after_snapshot = metrics_engine.capture_snapshot(
                active_power_kw=before_snapshot.active_power_kw * (1 - result.impact.get("load_reduction_kw", 0) / 1000),
                grid_frequency_hz=before_snapshot.grid_frequency_hz + (result.impact.get("grid_stability", 0) / 50),
                demand_load_kw=before_snapshot.demand_load_kw - result.impact.get("load_reduction_kw", 0),
                solar_output_kw=before_snapshot.solar_output_kw * (1 + result.impact.get("solar_efficiency", 0) / 100),
                expected_solar_kw=before_snapshot.solar_output_kw,
                voltage_v=before_snapshot.voltage_v,
                irradiance_wm2=850,
                temperature_c=before_snapshot.temperature_c
            )
            
            # Record impact
            metrics_engine.record_action_impact(
                action_id=self.request.id,
                action_type=action_type.value,
                before=before_snapshot,
                after=after_snapshot
            )
        
        return {
            "success": result.success,
            "action": result.action,
            "message": result.message,
            "duration_ms": result.duration_ms,
            "impact": result.impact,
            "task_id": self.request.id
        }
        
    except Exception as e:
        logger.error(f"execute_decision failed: {e}")
        self.retry(exc=e, countdown=10)
        return {"success": False, "error": str(e)}


@celery_app.task(
    bind=True,
    name="backend.tasks.optimization_tasks.update_optimization_report",
    queue="reporting_queue",
    priority=3,
    max_retries=2,
    time_limit=120,
    soft_time_limit=100
)
def update_optimization_report(self) -> dict:
    """
    LOW PRIORITY: Generate optimization report.
    """
    try:
        metrics_engine = get_metrics_engine()
        decision_engine = get_decision_engine()
        action_executor = get_action_executor()
        
        stats = {
            "metrics": metrics_engine.get_stats(),
            "decisions": decision_engine.get_stats(),
            "actions": action_executor.get_stats(),
            "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        }
        
        logger.info(f"[REPORT] Optimization summary: Score {stats['metrics']['current']['optimization_score']:.1f}, "
                   f"Actions: {stats['metrics']['total_actions']}, "
                   f"Gain: {stats['metrics']['total_optimization_gain']:.1f}")
        
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.error(f"update_optimization_report failed: {e}")
        return {"success": False, "error": str(e)}