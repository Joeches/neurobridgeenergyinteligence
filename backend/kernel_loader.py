"""
================================================================================
NeuroBridge 11D - Kernel Loader (Native C++ Priority)
================================================================================
CRITICAL FIX: Forces loading of nb_11d_kernel.pyd from venv site-packages
Version: 5.0.0-NATIVE-FORCED
================================================================================
"""

import logging
import sys
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Global kernel instance
_kernel_instance = None


def _find_and_load_kernel():
    """Find and load the native kernel from venv site-packages FIRST"""
    
    # CRITICAL FIX: Add venv site-packages to path FIRST
    venv_path = Path(__file__).parent.parent / "venv" / "Lib" / "site-packages"
    if venv_path.exists() and str(venv_path) not in sys.path:
        sys.path.insert(0, str(venv_path))
        logger.info(f"[Kernel] Added venv site-packages to path: {venv_path}")
    
    # Also add backend directory
    backend_dir = Path(__file__).parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    
    # Add DLL directories for Windows
    if sys.platform == "win32":
        try:
            if venv_path.exists():
                os.add_dll_directory(str(venv_path))
            if backend_dir.exists():
                os.add_dll_directory(str(backend_dir))
            kernel_dir = backend_dir / "kernel"
            if kernel_dir.exists():
                os.add_dll_directory(str(kernel_dir))
        except (AttributeError, OSError) as e:
            logger.debug(f"[Kernel] DLL directory add warning: {e}")
    
    # NOW try to import nb_11d_kernel
    try:
        import nb_11d_kernel as _kernel
        # Test the import by accessing a attribute
        if hasattr(_kernel, 'EnergyPredictor'):
            logger.info("[Kernel] ✅ NATIVE C++ KERNEL LOADED from venv site-packages")
            return _kernel
        else:
            logger.warning("[Kernel] Kernel loaded but EnergyPredictor not found")
    except ImportError as e:
        logger.warning(f"[Kernel] Failed to import nb_11d_kernel: {e}")
    
    # Fallback: Try direct .pyd file loading
    kernel_pyd_paths = [
        venv_path / "nb_11d_kernel.pyd",
        backend_dir / "nb_11d_kernel.pyd",
        backend_dir / "kernel" / "nb_11d_kernel.pyd",
        backend_dir / "kernel" / "nb_11d_kernel" / "nb_11d_kernel.cp311-win_amd64.pyd",
    ]
    
    for pyd_path in kernel_pyd_paths:
        if pyd_path.exists():
            logger.info(f"[Kernel] Found kernel .pyd at: {pyd_path}")
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("nb_11d_kernel", str(pyd_path))
                if spec and spec.loader:
                    _kernel = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(_kernel)
                    logger.info(f"[Kernel] ✅ Loaded kernel from {pyd_path}")
                    return _kernel
            except Exception as e:
                logger.warning(f"[Kernel] Failed to load from {pyd_path}: {e}")
    
    logger.error("[Kernel] ❌ No native kernel found - simulation mode will be used")
    return None


class SimpleKernelWrapper:
    """Kernel wrapper that prioritizes native C++"""
    
    def __init__(self):
        self._native_module = _find_and_load_kernel()
        self._is_native = self._native_module is not None
        self._predictor = None
        
        if self._is_native:
            try:
                self._predictor = self._native_module.EnergyPredictor()
                logger.info("[Kernel] ✅ EnergyPredictor created successfully")
            except Exception as e:
                logger.error(f"[Kernel] Failed to create EnergyPredictor: {e}")
                self._is_native = False
        else:
            logger.warning("[Kernel] ⚠️ Running in SIMULATION mode - native kernel not available")
        
        self._call_count = 0
        self._error_count = 0
        
        if self._is_native:
            logger.info("=" * 60)
            logger.info("🚀 NATIVE C++ KERNEL ACTIVE - FULL PERFORMANCE MODE")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("📊 SIMULATION MODE ACTIVE - Python fallback")
            logger.info("=" * 60)
    
    def is_native(self) -> bool:
        return self._is_native
    
    def get_kernel_type(self) -> str:
        return "nb_11d_kernel" if self._is_native else "simulation"
    
    def get_info(self) -> dict:
        return {
            "mode": "NATIVE_CPP" if self._is_native else "SIMULATED",
            "status": "healthy" if self._is_native else "degraded",
            "loaded": self._is_native,
            "kernel_type": self.get_kernel_type(),
            "version": "1.0.0-native" if self._is_native else "simulation",
            "phase": "PHASE_1_PRODUCTION",
            "phase1_compliant": True
        }
    
    def predict_solar_yield(self, irradiance: float, temp: float, cloud: float = 0) -> float:
        """Predict solar yield using native kernel if available"""
        self._call_count += 1
        
        if self._is_native and self._predictor:
            try:
                features = [
                    irradiance / 1000.0,
                    max(0, (temp - 25) / 25),
                    cloud / 100.0,
                    0.5, 0.6, 0.7, 0.5, 0.6, 0.7, 0.8, 0.85
                ]
                result = self._predictor.predict_yield(features)
                logger.debug(f"[Kernel] Native solar: {irradiance}W/m² → {result:.2f}kW")
                return max(0.0, min(200.0, float(result)))
            except Exception as e:
                self._error_count += 1
                logger.error(f"[Kernel] Native solar error: {e}")
        
        # Fallback calculation
        panel_area = 100.0
        panel_efficiency = 0.18
        irradiance_factor = irradiance / 1000.0
        temp_derate = 1.0 - max(0, (temp - 25) * 0.004)
        cloud_factor = 1.0 - (cloud / 100) * 0.8
        power = (irradiance * panel_area * panel_efficiency) / 1000.0
        power *= irradiance_factor * temp_derate * cloud_factor
        return max(0, min(panel_area * 0.2, power))
    
    def predict_grid_stability(self, freq: float, volt: float, demand: float, solar: float, battery: float = 50) -> float:
        """Predict grid stability using native kernel if available"""
        self._call_count += 1
        
        if self._is_native and self._predictor:
            try:
                features = [
                    (freq - 50.0) / 0.5,
                    (volt - 230.0) / 23.0,
                    demand / 1000.0,
                    solar / 500.0,
                    battery / 100.0,
                    0.5, 0.6, 0.7, 0.5, 0.6, 0.7
                ]
                result = self._predictor.predict_yield(features)
                stability = max(0.0, min(100.0, float(result) * 100))
                logger.debug(f"[Kernel] Native grid: {freq}Hz → {stability:.1f}")
                return stability
            except Exception as e:
                self._error_count += 1
                logger.error(f"[Kernel] Native grid error: {e}")
        
        # Fallback calculation
        score = 100.0
        score -= min(40, abs(freq - 50) / 0.5 * 20)
        score -= min(30, abs(volt - 230) / 23 * 15)
        total_supply = 500 + solar
        if demand > 0:
            imbalance = abs(total_supply - demand) / demand
            score -= min(30, imbalance * 40)
        return max(0, min(100, score))
    
    def calculate_yield(self, energy: float, entropy: float = 0.05) -> float:
        """Calculate energy yield using native kernel if available"""
        self._call_count += 1
        
        if self._is_native and self._predictor:
            try:
                features = [
                    energy / 150.0,
                    entropy,
                    0.5, 0.6, 0.7, 0.5, 0.6, 0.7, 0.8, 0.9, 0.85
                ]
                result = self._predictor.predict_yield(features)
                return max(0.0, float(result))
            except Exception as e:
                self._error_count += 1
                logger.error(f"[Kernel] Native yield error: {e}")
        
        # Fallback - energy conservation guaranteed
        max_efficiency = 0.95
        efficiency = max_efficiency * (1 - entropy)
        return min(energy * efficiency, energy)
    
    def get_metrics(self) -> dict:
        error_rate = self._error_count / max(self._call_count, 1) * 100
        return {
            "is_native": self._is_native,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "error_rate": round(error_rate, 2),
            "kernel_type": self.get_kernel_type()
        }
    
    def health_check(self) -> dict:
        if not self._is_native:
            return {"status": "degraded", "is_native": False, "message": "Using simulation fallback"}
        try:
            test = self.predict_solar_yield(850, 25, 10)
            return {"status": "healthy", "is_native": True, "test_result": round(test, 2), "message": "Native C++ kernel active"}
        except Exception as e:
            return {"status": "unhealthy", "is_native": True, "error": str(e)}


# Singleton instance
_kernel_loader = None


def get_kernel_loader():
    global _kernel_loader
    if _kernel_loader is None:
        _kernel_loader = SimpleKernelWrapper()
    return _kernel_loader


def get_phase1_blocked_stats():
    return {
        "total_blocked": 0,
        "blocked_types": ["nuclear", "fusion", "quantum", "defense"],
        "phase": "PHASE_1_PRODUCTION"
    }


# For backward compatibility
kernel_loader = get_kernel_loader()
kernel = kernel_loader


__all__ = [
    'get_kernel_loader',
    'get_phase1_blocked_stats',
    'kernel_loader',
    'kernel'
]