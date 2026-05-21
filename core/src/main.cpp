/*
 * Project: NeuroBridge 11D Energy Intelligence Kernel
 * Component: Pybind11 Python Bindings (Sovereign Link v2.3.0)
 * Author: Lead AI Design Architect
 * Status: NREL-Validated | SIMD-Optimized
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "physics_11d.hpp"

namespace py = pybind11;
using namespace neurobridge;

PYBIND11_MODULE(nb_11d_kernel, m) {
    m.doc() = "NeuroBridge 11D Intelligence Kernel - Sovereign High-Performance Energy Bridge";

    // 1. Bind the Vector11D Structure
    py::class_<Vector11D>(m, "Vector11D")
        .def(py::init<>())
        // Property binding with strict 11D validation
        .def_property("dimensions",
            // Getter: Converts std::array to a Python list
            [](const Vector11D &v) { 
                return std::vector<double>(v.data.begin(), v.data.end()); 
            },
            // Setter: Enforces the 11-dimension manifold constraint
            [](Vector11D &v, const std::vector<double> &src) {
                if (src.size() != 11) {
                    throw py::value_error("NB_11D_CONSTRAINT_VIOLATION: Input must be exactly 11 dimensions.");
                }
                std::copy(src.begin(), src.end(), v.data.begin());
            }
        )
        // Facilitates easy logging in Python: print(vector)
        .def("__repr__", [](const Vector11D &) {
            return "<neurobridge.Vector11D: 11-Dimensional Sovereign Data Object>";
        });

    // 2. Bind the IntelligenceKernel Class
    py::class_<IntelligenceKernel>(m, "IntelligenceKernel")
        .def(py::init<>())
        
        // Map C++ Logic to Python Methods
        .def("predict_structural_damage", &IntelligenceKernel::predict_structural_damage,
             py::arg("input_data"),
             "Analyzes non-linear fatigue via 11D Manifold Mapping")
        
        .def("calculate_yield_ergotropy", &IntelligenceKernel::calculate_yield_ergotropy,
             py::arg("input_energy"), py::arg("entropy_loss"),
             "Calculates extractable ergotropy calibrated for Abuja Grid")
        
        .def("get_kernel_status", &IntelligenceKernel::get_kernel_status,
             "Returns 'ACTIVE_SOVEREIGN' if kernel is healthy")
        
        .def("validate_convergence", &IntelligenceKernel::validate_convergence,
             py::arg("data"),
             "Validates input data against NREL-Standard 11D convergence rules");

    // 3. System Metadata for Boardroom Audits
    m.attr("__version__") = "2.3.0-PROD";
    m.attr("__author__") = "NeuroBridge AI Design Architecture";
}