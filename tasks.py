"""
NeuroBridge 11D - Celery Task Queue
Working version for Windows
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Celery imports
from celery import Celery
from celery.result import AsyncResult

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

REDIS_URL = "redis://localhost:6379/0"

app = Celery(
    'neurobridge_tasks',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# BASIC TASKS
# ============================================================================

@app.task(name='tasks.echo')
def echo_task(message: str) -> Dict[str, Any]:
    """Simple echo task"""
    logger.info(f"Echo task: {message}")
    time.sleep(0.5)
    return {
        "task_id": echo_task.request.id,
        "message": message,
        "echo": f"Echo: {message}",
        "timestamp": datetime.now().isoformat()
    }


@app.task(name='tasks.add')
def add_numbers(a: float, b: float) -> Dict[str, Any]:
    """Add two numbers"""
    logger.info(f"Adding {a} + {b}")
    time.sleep(0.3)
    result = a + b
    return {
        "task_id": add_numbers.request.id,
        "a": a,
        "b": b,
        "sum": result,
        "timestamp": datetime.now().isoformat()
    }


@app.task(name='tasks.multiply')
def multiply_numbers(a: float, b: float) -> Dict[str, Any]:
    """Multiply two numbers"""
    logger.info(f"Multiplying {a} * {b}")
    time.sleep(0.3)
    result = a * b
    return {
        "task_id": multiply_numbers.request.id,
        "a": a,
        "b": b,
        "product": result,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# ENERGY TASKS
# ============================================================================

@app.task(name='tasks.energy.predict')
def predict_energy(sector: str, hours_ahead: int = 24) -> Dict[str, Any]:
    """Predict energy yield for a sector"""
    logger.info(f"Predicting {sector} for {hours_ahead} hours")
    
    # Base yields by sector
    base_yields = {
        "renewables": 100.0,
        "oil_gas": 85.0,
        "grid_storage": 95.0,
        "quantum": 120.0,
        "defense": 90.0,
        "nuclear": 110.0
    }
    
    base = base_yields.get(sector, 100.0)
    predictions = []
    
    for hour in range(min(hours_ahead, 48)):
        predicted = base * (1 + (hour * 0.02))
        predictions.append({
            "hour": hour + 1,
            "timestamp": (datetime.now() + timedelta(hours=hour+1)).isoformat(),
            "yield_mwh": round(predicted, 2),
            "confidence": round(0.95 - (hour * 0.01), 3)
        })
    
    return {
        "task_id": predict_energy.request.id,
        "sector": sector,
        "hours": hours_ahead,
        "predictions": predictions,
        "timestamp": datetime.now().isoformat()
    }


@app.task(name='tasks.energy.batch_predict')
def batch_predict_energy(sectors: List[str], hours: int = 24) -> Dict[str, Any]:
    """Batch prediction for multiple sectors"""
    logger.info(f"Batch predicting {len(sectors)} sectors")
    
    results = {}
    for sector in sectors:
        task = predict_energy.delay(sector, hours)
        results[sector] = task.id
    
    return {
        "task_id": batch_predict_energy.request.id,
        "sectors": len(sectors),
        "task_ids": results,
        "timestamp": datetime.now().isoformat()
    }


@app.task(name='tasks.energy.metrics')
def get_energy_metrics() -> Dict[str, Any]:
    """Get aggregated energy metrics"""
    logger.info("Getting energy metrics")
    time.sleep(0.5)
    
    return {
        "task_id": get_energy_metrics.request.id,
        "total_yield_mwh": 1250.5,
        "avg_efficiency": 0.89,
        "active_sectors": 6,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# MONITORING TASKS
# ============================================================================

@app.task(name='tasks.monitoring.health')
def check_health() -> Dict[str, Any]:
    """Check system health"""
    logger.info("Checking system health")
    
    # Check Redis
    redis_ok = False
    try:
        import redis
        r = redis.from_url(REDIS_URL)
        redis_ok = r.ping()
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
    
    return {
        "task_id": check_health.request.id,
        "status": "healthy" if redis_ok else "degraded",
        "redis": {"connected": redis_ok},
        "timestamp": datetime.now().isoformat()
    }


@app.task(name='tasks.monitoring.rate_limits')
def check_rate_limits() -> Dict[str, Any]:
    """Check rate limits"""
    logger.info("Checking rate limits")
    
    return {
        "task_id": check_rate_limits.request.id,
        "total_requests": 1234,
        "active_users": 42,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# NOTIFICATION TASKS
# ============================================================================

@app.task(name='tasks.notifications.email')
def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send email notification"""
    logger.info(f"Sending email to {to}: {subject}")
    time.sleep(0.5)
    
    return {
        "task_id": send_email.request.id,
        "to": to,
        "subject": subject,
        "status": "sent",
        "timestamp": datetime.now().isoformat()
    }


@app.task(name='tasks.notifications.alert')
def send_alert(alert_type: str, severity: str, message: str) -> Dict[str, Any]:
    """Send system alert"""
    logger.info(f"Alert [{severity}]: {message}")
    
    return {
        "task_id": send_alert.request.id,
        "type": alert_type,
        "severity": severity,
        "message": message,
        "status": "sent",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# DATA PROCESSING TASKS
# ============================================================================

@app.task(name='tasks.data.process_batch')
def process_sensor_batch(sensor_data: List[Dict]) -> Dict[str, Any]:
    """Process batch of sensor data"""
    logger.info(f"Processing {len(sensor_data)} sensor readings")
    
    processed = 0
    errors = 0
    
    for reading in sensor_data:
        if reading.get('sensor_id') and reading.get('value') is not None:
            processed += 1
        else:
            errors += 1
    
    time.sleep(0.5)
    
    return {
        "task_id": process_sensor_batch.request.id,
        "total": len(sensor_data),
        "processed": processed,
        "errors": errors,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get task status"""
    try:
        result = AsyncResult(task_id, app=app)
        return {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "result": result.result if result.ready() else None,
        }
    except Exception as e:
        return {"task_id": task_id, "status": "error", "error": str(e)}


def revoke_task(task_id: str, terminate: bool = False) -> Dict[str, Any]:
    """Revoke a task"""
    try:
        result = AsyncResult(task_id, app=app)
        result.revoke(terminate=terminate)
        return {"task_id": task_id, "revoked": True}
    except Exception as e:
        return {"task_id": task_id, "revoked": False, "error": str(e)}


if __name__ == '__main__':
    app.start()