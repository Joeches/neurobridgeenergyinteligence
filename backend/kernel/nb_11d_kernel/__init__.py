import os 
import sys 
import importlib.util 
 
__all__ = ['EnergyPredictor', 'QuantumTensor', 'ManifoldAnalyzer', 'OptimizationEngine'] 
 
# Use the original module name as compiled 
_kernel_path = os.path.join(os.path.dirname(__file__), 'nb_11d_kernel.cp311-win_amd64.pyd') 
 
if os.path.exists(_kernel_path): 
    # Load the module with its original name 
    spec = importlib.util.spec_from_file_location('nb_11d_kernel', _kernel_path) 
    _kernel = importlib.util.module_from_spec(spec) 
    spec.loader.exec_module(_kernel) 
    # Export the classes 
    EnergyPredictor = _kernel.EnergyPredictor 
    QuantumTensor = _kernel.QuantumTensor 
    ManifoldAnalyzer = _kernel.ManifoldAnalyzer 
    OptimizationEngine = _kernel.OptimizationEngine 
    __version__ = getattr(_kernel, '__version__', '1.0.0') 
else: 
    raise ImportError(f'Kernel module not found at {_kernel_path}') 
