# check_routes.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.main import app

print("\n" + "="*80)
print("REGISTERED API ENDPOINTS")
print("="*80)

for route in app.routes:
    if hasattr(route, 'path') and '/api/v1/security' in route.path:
        print(f"  {route.methods if hasattr(route, 'methods') else 'ANY'} {route.path}")