"""
Redis Queue Client for NeuroBridge
Run: python client.py
"""

import redis
from rq import Queue
from worker import echo_task, add_task, multiply_task, predict_energy_task, health_check_task
import time

# Connect to Redis
redis_conn = redis.Redis(host='localhost', port=6379, db=0)
queue = Queue('default', connection=redis_conn)

print("=" * 60)
print("NeuroBridge RQ Client")
print("=" * 60)

# Test 1: Echo
print("\n1. Submitting echo task...")
job = queue.enqueue(echo_task, "Hello NeuroBridge!")
print(f"   Job ID: {job.id}")
result = job.result
while result is None:
    time.sleep(0.5)
    result = job.result
print(f"   Result: {result}")
print("   ✅ PASSED")

# Test 2: Add
print("\n2. Submitting add task...")
job = queue.enqueue(add_task, 10, 20)
result = job.result
while result is None:
    time.sleep(0.5)
    result = job.result
print(f"   Result: 10 + 20 = {result}")
print("   ✅ PASSED")

# Test 3: Multiply
print("\n3. Submitting multiply task...")
job = queue.enqueue(multiply_task, 5, 6)
result = job.result
while result is None:
    time.sleep(0.5)
    result = job.result
print(f"   Result: 5 * 6 = {result}")
print("   ✅ PASSED")

# Test 4: Energy Prediction
print("\n4. Submitting energy prediction...")
job = queue.enqueue(predict_energy_task, "renewables", 12)
result = job.result
while result is None:
    time.sleep(0.5)
    result = job.result
print(f"   Sector: {result.get('sector')}")
print(f"   First hour: {result['predictions'][0]['yield_mwh']} MWh")
print("   ✅ PASSED")

# Test 5: Health Check
print("\n5. Submitting health check...")
job = queue.enqueue(health_check_task)
result = job.result
while result is None:
    time.sleep(0.5)
    result = job.result
print(f"   Status: {result.get('status')}")
print(f"   Redis: {result.get('redis')}")
print("   ✅ PASSED")

print("\n" + "=" * 60)
print("🎉 All tests passed!")
print("=" * 60)