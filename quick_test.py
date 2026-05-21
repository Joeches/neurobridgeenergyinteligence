"""
NeuroBridge 11D - Simple Celery Client
Save as: celery_simple.py
Run: python celery_simple.py
"""

import time
from datetime import datetime

# Import Celery tasks
from tasks import (
    calculate_energy_prediction,
    echo_task,
    add_numbers,
    get_task_status
)


def submit_task_example():
    """Simple example of submitting tasks"""
    
    print("=" * 60)
    print("NEUROBRIDGE 11D - Celery Task Client")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Example 1: Echo task
    print("1. Submitting echo task...")
    try:
        result = echo_task.delay("Hello from NeuroBridge!")
        task_id = result.id
        print(f"   Task ID: {task_id}")
        
        # Check status
        time.sleep(1)
        status = get_task_status(task_id)
        print(f"   Status: {status.get('status')}")
        print("   ✅ Echo task submitted successfully\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")
    
    # Example 2: Add numbers
    print("2. Submitting addition task...")
    try:
        result = add_numbers.delay(15, 27)
        task_id = result.id
        print(f"   Task ID: {task_id}")
        
        # Wait for result
        print("   Waiting for result...")
        task_result = result.get(timeout=10)
        print(f"   Result: 15 + 27 = {task_result.get('sum')}")
        print("   ✅ Addition task completed successfully\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")
    
    # Example 3: Energy prediction
    print("3. Submitting energy prediction...")
    try:
        result = calculate_energy_prediction.delay("renewables", 12)
        task_id = result.id
        print(f"   Task ID: {task_id}")
        
        # Check status periodically
        print("   Checking status...")
        for i in range(5):
            time.sleep(1)
            status = get_task_status(task_id)
            print(f"   Status: {status.get('status')}")
            if status.get('ready'):
                break
        
        # Get result if ready
        if result.ready():
            if result.successful():
                pred_result = result.result
                predictions = pred_result.get('predictions', [])
                print(f"   ✅ Success! Predicted {len(predictions)} hours")
                if predictions:
                    first_pred = predictions[0]
                    print(f"   First hour: {first_pred.get('predicted_yield_mwh')} MWh")
            else:
                print(f"   ❌ Task failed: {result.result}")
        else:
            print("   ⚠️ Task still processing...")
        
        print("\n✅ All tasks submitted successfully!")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    submit_task_example()