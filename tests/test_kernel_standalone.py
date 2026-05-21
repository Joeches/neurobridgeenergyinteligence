"""
Standalone test for nb_11d_kernel.pyd
No dependencies on backend modules
"""

import sys
import time
from pathlib import Path

# Add the kernel directory to path
kernel_dir = Path(__file__).parent / "backend" / "kernel" / "nb_11d_kernel"
if kernel_dir.exists():
    sys.path.insert(0, str(kernel_dir))

# Also add backend directory
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

print("=" * 70)
print("STANDALONE NB_KERNEL TEST")
print("=" * 70)

# Try direct import
print("\n1. Attempting to import nb_11d_kernel...")
try:
    import nb_11d_kernel as kernel
    print(f"✅ Success! Version: {getattr(kernel, '__version__', 'unknown')}")
    print(f"   Location: {kernel.__file__ if hasattr(kernel, '__file__') else 'built-in'}")
except ImportError as e:
    print(f"❌ Failed: {e}")
    sys.exit(1)

# List available attributes
print("\n2. Available attributes:")
attrs = [a for a in dir(kernel) if not a.startswith('_')]
for attr in attrs:
    print(f"   - {attr}")

# Create EnergyPredictor
print("\n3. Creating EnergyPredictor instance...")
try:
    predictor = kernel.EnergyPredictor()
    print("✅ EnergyPredictor created successfully")
except Exception as e:
    print(f"❌ Failed: {e}")
    sys.exit(1)

# Test predict_yield method
print("\n4. Testing predict_yield method...")

# Based on your successful test, predict_yield works with 11 features
test_features = [0.85, 0.1, 0.2, 0.5, 0.6, 0.7, 0.5, 0.6, 0.7, 0.8, 0.85]
print(f"   Features: {test_features[:5]}...")

try:
    result = predictor.predict_yield(test_features)
    print(f"✅ predict_yield result: {result}")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test solar yield prediction
print("\n5. Testing solar yield prediction...")

def predict_solar_yield(irradiance, temp, cloud):
    """Convert solar parameters to kernel features"""
    features = [
        irradiance / 1000.0,           # Normalized irradiance
        max(0, (temp - 25) / 25),      # Temperature deviation
        cloud / 100.0,                  # Cloud cover
        0.5, 0.6, 0.7, 0.5, 0.6, 0.7,  # Placeholders
        0.8, 0.85                       # More placeholders
    ]
    return predictor.predict_yield(features)

test_cases = [
    ("High irradiance", 1000.0, 20.0, 0),
    ("Medium irradiance", 850.0, 30.0, 25),
    ("Low irradiance", 500.0, 38.0, 60),
]

for name, irradiance, temp, cloud in test_cases:
    start = time.perf_counter()
    result = predict_solar_yield(irradiance, temp, cloud)
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"   {name}: {irradiance}W/m², {temp}°C, {cloud}% cloud → {result:.2f} kW ({elapsed_ms:.2f}ms)")

# Test grid stability prediction
print("\n6. Testing grid stability prediction...")

def predict_grid_stability(freq, volt, demand, solar):
    """Convert grid parameters to kernel features"""
    features = [
        (freq - 50.0) / 0.5,           # Frequency deviation
        (volt - 230.0) / 23.0,          # Voltage deviation
        demand / 1000.0,                # Normalized demand
        solar / 500.0,                  # Normalized solar
        0.5, 0.6, 0.7, 0.5, 0.6, 0.7,  # Placeholders
        0.85                            # Final placeholder
    ]
    result = predictor.predict_yield(features)
    # Scale to 0-100
    return max(0, min(100, result * 100))

grid_tests = [
    ("Perfect", 50.00, 230.0, 500, 100),
    ("Low frequency", 49.30, 228.0, 600, 80),
    ("High frequency", 50.80, 235.0, 550, 120),
    ("High demand", 49.85, 225.0, 850, 50),
]

for name, freq, volt, demand, solar in grid_tests:
    start = time.perf_counter()
    result = predict_grid_stability(freq, volt, demand, solar)
    elapsed_ms = (time.perf_counter() - start) * 1000
    risk = "HIGH" if result < 70 else "MEDIUM" if result < 85 else "LOW"
    print(f"   {name}: {freq}Hz, {volt}V, {demand}kW → {result:.1f} ({risk} risk) ({elapsed_ms:.2f}ms)")

# Performance benchmark
print("\n7. Performance Benchmark (1000 predictions)...")
iterations = 1000

start = time.perf_counter()
for _ in range(iterations):
    predict_solar_yield(850.0, 25.0, 10.0)
total_ms = (time.perf_counter() - start) * 1000

avg_ms = total_ms / iterations
throughput = iterations / (total_ms / 1000)

print(f"   Total time: {total_ms:.2f} ms")
print(f"   Average per prediction: {avg_ms:.3f} ms")
print(f"   Throughput: {throughput:.0f} predictions/second")

if avg_ms < 1:
    print("   ✅ Excellent performance (<1ms)")
elif avg_ms < 5:
    print("   ✅ Good performance (<5ms)")
else:
    print("   ⚠️ Consider optimization")

# Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)

# Check available methods
print("\n📋 Available predictor methods:")
predictor_methods = [m for m in dir(predictor) if not m.startswith('_') and callable(getattr(predictor, m))]
for method in predictor_methods:
    print(f"   - {method}")

print("\n" + "=" * 70)
print("✅ STANDALONE TEST COMPLETE")
print("=" * 70)