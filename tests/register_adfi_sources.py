# test_adfi_aece_full.py
import asyncio
import sys
sys.path.insert(0, 'C:/Users/hp/Desktop/energy-kernel')

async def test_full_integration():
    print("\n" + "="*60)
    print("ADFI + AECE FULL INTEGRATION TEST")
    print("="*60)
    
    # Load engines
    from backend.ingestion.adfi_engine import get_adfi_engine, DataSource
    from backend.control.aece_engine import evaluate_and_execute_telemetry
    
    adfi = get_adfi_engine()
    
    # Register synthetic source
    async def synthetic_fetcher():
        import random
        return {
            "solar_output_kw": 100 + random.randint(-30, 80),
            "grid_frequency_hz": 50.0 + random.uniform(-0.5, 0.5),
            "demand_load_kw": 1200 + random.randint(-200, 300),
            "cloud_cover_percent": random.randint(10, 90),
            "battery_soc_percent": random.randint(20, 90),
            "temperature_c": 28 + random.uniform(-5, 10),
            "irradiance_wm2": 800 + random.randint(-200, 200)
        }
    
    adfi.register_fetcher(DataSource.SYNTHETIC, synthetic_fetcher)
    print("✅ Synthetic data source registered")
    
    # Run decision loop
    print("\n🔄 Running Decision Loop (5 cycles):")
    print("-" * 40)
    
    for i in range(5):
        print(f"\nCycle {i+1}:")
        
        # Get telemetry from ADFI
        telemetry_obj = await adfi.get_telemetry()
        
        if telemetry_obj:
            # Convert to dict for AECE
            telemetry = {
                "solar_output_kw": getattr(telemetry_obj, 'solar_output_kw', 100),
                "grid_frequency_hz": getattr(telemetry_obj, 'grid_frequency_hz', 50.0),
                "demand_load_kw": getattr(telemetry_obj, 'demand_load_kw', 1000),
                "cloud_cover_percent": getattr(telemetry_obj, 'cloud_cover_percent', 50),
                "battery_soc_percent": getattr(telemetry_obj, 'battery_soc_percent', 50),
                "temperature_c": getattr(telemetry_obj, 'temperature_c', 25),
                "irradiance_wm2": getattr(telemetry_obj, 'irradiance_wm2', 800)
            }
            
            print(f"   📊 Telemetry: Solar={telemetry['solar_output_kw']:.0f}kW, "
                  f"Freq={telemetry['grid_frequency_hz']:.2f}Hz, "
                  f"Demand={telemetry['demand_load_kw']:.0f}kW")
            
            # Get AECE decision
            decision = await evaluate_and_execute_telemetry(telemetry, execute=False)
            
            print(f"   🤖 Decision: {decision.get('action')} "
                  f"(Risk: {decision.get('risk_score'):.3f})")
            print(f"   💡 Reason: {decision.get('reason', '')[:60]}")
        else:
            print(f"   ⚠️ No telemetry available")
        
        await asyncio.sleep(2)
    
    print("\n" + "="*60)
    print("✅ Integration Test Complete!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_full_integration())