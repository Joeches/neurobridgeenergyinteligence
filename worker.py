"""
Redis Queue Worker for NeuroBridge - Windows Compatible
Run: python worker.py
"""

import time
import redis
from datetime import datetime

# Connect to Redis
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# Define tasks (must be at module level)
def echo_task(message):
    """Echo task"""
    print(f"📝 Processing echo: {message}")
    time.sleep(0.5)
    return f"Echo: {message}"

def add_task(a, b):
    """Add two numbers"""
    print(f"➕ Adding {a} + {b}")
    time.sleep(0.3)
    return a + b

def multiply_task(a, b):
    """Multiply two numbers"""
    print(f"✖️ Multiplying {a} * {b}")
    time.sleep(0.3)
    return a * b

def predict_energy_task(sector, hours=24):
    """Predict energy yield"""
    print(f"⚡ Predicting {sector} for {hours} hours")
    
    base_yields = {
        "renewables": 100,
        "oil_gas": 85,
        "grid_storage": 95,
        "quantum": 120,
        "defense": 90,
        "nuclear": 110
    }
    
    base = base_yields.get(sector, 100)
    predictions = []
    
    for hour in range(min(hours, 24)):
        predicted = base * (1 + (hour * 0.02))
        predictions.append({
            "hour": hour + 1,
            "yield_mwh": round(predicted, 2),
            "confidence": round(0.95 - (hour * 0.01), 3)
        })
    
    return {
        "sector": sector,
        "hours": hours,
        "predictions": predictions[:5],
        "timestamp": datetime.now().isoformat()
    }

def health_check_task():
    """Check system health"""
    try:
        redis_conn.ping()
        redis_status = "connected"
        print("✅ Redis health check passed")
    except Exception as e:
        redis_status = f"disconnected: {e}"
        print(f"❌ Redis health check failed: {e}")
    
    return {
        "status": "healthy" if redis_status == "connected" else "degraded",
        "redis": redis_status,
        "timestamp": datetime.now().isoformat()
    }

def process_sensor_task(sensor_data):
    """Process sensor data"""
    print(f"📊 Processing {len(sensor_data)} sensor readings")
    
    processed = 0
    for reading in sensor_data:
        if reading.get('sensor_id'):
            processed += 1
        time.sleep(0.01)
    
    return {
        "total": len(sensor_data),
        "processed": processed,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == '__main__':
    print("=" * 60)
    print("🔷 NEUROBRIDGE 11D - RQ WORKER")
    print("=" * 60)
    
    # Test Redis connection
    try:
        redis_conn.ping()
        print(f"✅ Redis connected successfully!")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Make sure Redis is running: redis-server")
        exit(1)
    
    print("📋 Available tasks:")
    print("   - echo_task")
    print("   - add_task") 
    print("   - multiply_task")
    print("   - predict_energy_task")
    print("   - health_check_task")
    print("   - process_sensor_task")
    print("=" * 60)
    print("⏳ Starting RQ worker...")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    # Use SimpleWorker for Windows compatibility
    from rq import SimpleWorker, Queue
    
    queue = Queue('default', connection=redis_conn)
    worker = SimpleWorker([queue], connection=redis_conn)
    
    try:
        worker.work()
    except KeyboardInterrupt:
        print("\n\n👋 Worker stopped.")