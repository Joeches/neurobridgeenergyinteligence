"""
Check kernel dependencies and export symbols
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("KERNEL DEPENDENCY CHECK")
print("=" * 60)

# Find all .pyd files
pyd_files = []
search_paths = [
    Path("venv/Lib/site-packages"),
    Path("backend"),
    Path("backend/kernel"),
    Path("."),
]

for search_path in search_paths:
    if search_path.exists():
        for pyd in search_path.glob("*.pyd"):
            pyd_files.append(pyd)

print(f"\n📦 Found .pyd files:")
for pyd in pyd_files:
    size = pyd.stat().st_size
    print(f"   - {pyd} ({size:,} bytes)")

# Check which one is actually importable
print(f"\n🔍 Testing imports:")

for pyd in pyd_files:
    module_name = pyd.stem
    parent_dir = str(pyd.parent)
    
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    try:
        module = __import__(module_name)
        print(f"   ✅ {module_name} - IMPORT SUCCESS")
        
        # List available attributes
        attrs = [a for a in dir(module) if not a.startswith('_')]
        print(f"      Available: {', '.join(attrs[:5])}...")
        
    except ImportError as e:
        print(f"   ❌ {module_name} - Import failed: {e}")