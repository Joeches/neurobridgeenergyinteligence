"""
NeuroBridge 11D - Monitoring Package
Phase 1 Production Observability

This package provides:
- Prometheus metrics collection and export
- System health monitoring
- Performance tracking
- ADFI observability instrumentation
- AECE control metrics
- External API telemetry
- Production compliance verification
- Hardware bridge monitoring

Usage:
    from backend.monitoring import metrics
    from backend.monitoring import (
        record_adfi_ingestion,
        record_aece_decision,
        record_external_request,
        set_redis_health,
        set_phase1_compliance_status,
    )
"""

# ============================================================================
# PACKAGE METADATA
# ============================================================================

__version__ = "14.8.1"
__phase__ = "PHASE_1_PRODUCTION"

# ============================================================================
# PROMETHEUS METRICS - Primary Export
# ============================================================================

from backend.monitoring.prometheus_metrics import (
    # Singleton metrics instance
    metrics,
    
    # Existing helper functions (preserved)
    update_energy_metrics,
    update_weather_metrics,
    update_celery_queue_metrics,
    update_partner_metrics,
    update_system_metrics,
    update_hardware_metrics,
    record_user_login,
    record_aece_action,
    track_aece_decision,
    update_aece_risk_score,
    record_grid_risk_event,
    track_auto_control_latency,
    
    # ADFI Observability helpers
    record_adfi_ingestion,
    record_adfi_cycle,
    set_adfi_source_health,
    record_adfi_pipeline_latency,
    
    # AECE Autonomous Control helpers (extended)
    record_aece_decision,
    set_emergency_stop_state,
    set_grid_stability_index,
    set_solar_efficiency_score,
    
    # External API helpers
    record_external_request,
    record_auth_failure,
    record_onboarding_event,
    set_investor_clients_active,
    
    # NeuroBridge 11D Overview helpers
    set_active_module,
    set_celery_queue_depth,
    set_redis_health,
    set_hardware_bridge_status,
    set_prediction_accuracy,
    set_phase1_compliance_status,
    
    # Context managers
    track_request,
    track_celery_task,
    track_duration,
    
    # Export endpoint
    get_metrics_response,
    is_prometheus_healthy,
    get_metrics_summary,
    
    # Middleware
    PrometheusMiddleware,
    
    # Utilities
    PROMETHEUS_AVAILABLE,
    REGISTRY,
    get_phase1_metric_stats,
    is_phase1_allowed_metric,
    register_metric_safe,
    metric_exists_in_registry,
    clear_metric_registration_cache,
    NullMetric,
)

# ============================================================================
# PACKAGE EXPORTS
# ============================================================================

__all__ = [
    # Singleton
    "metrics",
    
    # Existing helpers (preserved)
    "update_energy_metrics",
    "update_weather_metrics",
    "update_celery_queue_metrics",
    "update_partner_metrics",
    "update_system_metrics",
    "update_hardware_metrics",
    "record_user_login",
    "record_aece_action",
    "track_aece_decision",
    "update_aece_risk_score",
    "record_grid_risk_event",
    "track_auto_control_latency",
    
    # ADFI Observability
    "record_adfi_ingestion",
    "record_adfi_cycle",
    "set_adfi_source_health",
    "record_adfi_pipeline_latency",
    
    # AECE Autonomous Control
    "record_aece_decision",
    "set_emergency_stop_state",
    "set_grid_stability_index",
    "set_solar_efficiency_score",
    
    # External API
    "record_external_request",
    "record_auth_failure",
    "record_onboarding_event",
    "set_investor_clients_active",
    
    # NeuroBridge 11D Overview
    "set_active_module",
    "set_celery_queue_depth",
    "set_redis_health",
    "set_hardware_bridge_status",
    "set_prediction_accuracy",
    "set_phase1_compliance_status",
    
    # Context managers
    "track_request",
    "track_celery_task",
    "track_duration",
    
    # Export endpoint
    "get_metrics_response",
    "is_prometheus_healthy",
    "get_metrics_summary",
    
    # Middleware
    "PrometheusMiddleware",
    
    # Utilities
    "PROMETHEUS_AVAILABLE",
    "REGISTRY",
    "get_phase1_metric_stats",
    "is_phase1_allowed_metric",
    "register_metric_safe",
    "metric_exists_in_registry",
    "clear_metric_registration_cache",
    "NullMetric",
]