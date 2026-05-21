import asyncio
import sys
sys.path.insert(0, 'C:/Users/hp/Desktop/energy-kernel')

async def test_adfi():
    print("\n" + "="*60)
    print("ADFI ENGINE TEST SUITE")
    print("="*60)
    
    # Test 1: Import and check ADFI availability
    print("\n[1] Checking ADFI Availability:")
    try:
        from backend.ingestion.adfi_engine import get_adfi_engine
        adfi = get_adfi_engine()
        print(f"   ✅ ADFI Engine loaded: {adfi is not None}")
        print(f"   📊 ADFI Version: 4.0.0")
    except Exception as e:
        print(f"   ❌ ADFI not available: {e}")
        return
    
    # Test 2: Get telemetry
    print("\n[2] Getting Telemetry from ADFI:")
    try:
        telemetry = await adfi.get_telemetry()
        if telemetry:
            print(f"   ✅ Telemetry retrieved successfully")
            print(f"   📊 Solar Output: {getattr(telemetry, 'solar_output_kw', 'N/A')} kW")
            print(f"   📊 Grid Frequency: {getattr(telemetry, 'grid_frequency_hz', 'N/A')} Hz")
            print(f"   📊 Demand Load: {getattr(telemetry, 'demand_load_kw', 'N/A')} kW")
            print(f"   📊 Battery SOC: {getattr(telemetry, 'battery_soc_percent', 'N/A')}%")
            print(f"   📊 Source: {getattr(telemetry, 'source', 'N/A')}")
            print(f"   📊 Quality: {getattr(telemetry, 'quality_score', getattr(telemetry, 'data_quality', 'N/A'))}")
        else:
            print(f"   ⚠️ No telemetry available")
    except Exception as e:
        print(f"   ❌ Telemetry error: {e}")
    
    # Test 3: Get status
    print("\n[3] Getting ADFI Status:")
    try:
        status = await adfi.get_status() if hasattr(adfi, 'get_status') else {"status": "unknown"}
        print(f"   ✅ Status: {status.get('status', 'unknown')}")
        if 'sources' in status:
            print(f"   📊 Registered Sources: {list(status['sources'].keys())}")
    except Exception as e:
        print(f"   ❌ Status error: {e}")
    
    # Test 4: Health check
    print("\n[4] ADFI Health Check:")
    try:
        if hasattr(adfi, 'health_check'):
            health = await adfi.health_check()
            print(f"   ✅ Health: {health.get('status', 'unknown')}")
        else:
            print(f"   ℹ️ Health check method not available")
    except Exception as e:
        print(f"   ❌ Health check error: {e}")

if __name__ == "__main__":
    asyncio.run(test_adfi())