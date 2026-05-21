/*
 * NeuroBridge 11D Energy Kernel - Python Bindings
 * High-performance C++ extension for energy calculations
 * 
 * Module name: _kernel_compiled (must match loader expectation)
 * Exports: EnergyPredictor class with predict_yield method
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "core.h"

namespace py = pybind11;

// EnergyPredictor class wrapper for Python
class EnergyPredictor {
private:
    EnergyKernel kernel;
    
public:
    EnergyPredictor() {
        // Initialize kernel with default parameters
        kernel.initialize();
    }
    
    ~EnergyPredictor() {
        // Cleanup if needed
    }
    
    /**
     * Predict energy yield based on input features
     * Features array: [input_energy, entropy_loss, ...additional_params]
     */
    double predict_yield(const std::vector<double>& features) {
        if (features.empty()) {
            return 100.0;  // Default fallback
        }
        
        double input_energy = features[0] * 150.0;  // Scale back to actual value
        double entropy_loss = features.size() > 1 ? features[1] : 0.05;
        
        return kernel.calculate_yield_ergotropy(input_energy, entropy_loss);
    }
    
    /**
     * Direct calculation method (simpler interface)
     */
    double calculate(double input_energy, double entropy_loss = 0.05) {
        return kernel.calculate_yield_ergotropy(input_energy, entropy_loss);
    }
    
    /**
     * Batch prediction for multiple inputs
     */
    std::vector<double> predict_batch(const std::vector<std::vector<double>>& features_batch) {
        std::vector<double> results;
        results.reserve(features_batch.size());
        
        for (const auto& features : features_batch) {
            results.push_back(predict_yield(features));
        }
        
        return results;
    }
    
    /**
     * Get kernel version and info
     */
    py::dict get_info() {
        py::dict info;
        info["version"] = "13.0.0";
        info["native"] = true;
        info["backend"] = "C++";
        info["compiler"] = "MSVC/GCC";
        info["optimization"] = "O3, AVX2, OpenMP";
        return info;
    }
};

// Module definition - MUST be named _kernel_compiled
PYBIND11_MODULE(_kernel_compiled, m) {
    m.doc() = "NeuroBridge 11D Energy Kernel - High Performance C++ Extension";
    
    // Add module version
    m.attr("__version__") = "13.0.0";
    m.attr("__native__") = true;
    
    // Export the EnergyPredictor class
    py::class_<EnergyPredictor>(m, "EnergyPredictor")
        .def(py::init<>())
        .def("predict_yield", &EnergyPredictor::predict_yield, 
             py::arg("features"),
             "Predict energy yield from feature vector")
        .def("calculate", &EnergyPredictor::calculate,
             py::arg("input_energy"), py::arg("entropy_loss") = 0.05,
             "Direct calculation of yield from energy and entropy")
        .def("predict_batch", &EnergyPredictor::predict_batch,
             py::arg("features_batch"),
             "Batch prediction for multiple feature sets")
        .def("get_info", &EnergyPredictor::get_info,
             "Get kernel information")
        .def("__call__", &EnergyPredictor::calculate,
             "Allow direct calling of the predictor");
    
    // Also export a convenience function for direct use
    m.def("calculate_yield", [](double input_energy, double entropy_loss = 0.05) {
        EnergyKernel kernel;
        return kernel.calculate_yield_ergotropy(input_energy, entropy_loss);
    }, py::arg("input_energy"), py::arg("entropy_loss") = 0.05);
    
    // Export kernel info
    m.def("get_kernel_version", []() { return std::string("13.0.0-ENTERPRISE-PILOT"); });
    m.def("is_native", []() { return true; });
    
#ifdef _OPENMP
    m.attr("_has_openmp") = true;
#else
    m.attr("_has_openmp") = false;
#endif
    
    // Print initialization message (only once)
    static bool initialized = false;
    if (!initialized) {
        py::print("[Kernel] ✅ Native C++ kernel v13.0.0 loaded");
        initialized = true;
    }
}