# Save as test_phase1.py
import sys
sys.path.insert(0, 'C:/Users/hp/Desktop/energy-kernel')

from backend.control.aece_engine import get_phase1_status

status = get_phase1_status()
print("Phase 1 Status:")
print(f"  Phase: {status.get('phase')}")
print(f"  Version: {status.get('version')}")
print(f"  Runtime Mode: {status.get('runtime_mode')}")
print(f"  Allowed Actions: {status.get('allowed_actions')[:5]}...")  # First 5
print(f"  Blocked Actions: {status.get('blocked_actions')}")
print(f"  Total Blocked Attempts: {status.get('total_blocked_attempts')}")