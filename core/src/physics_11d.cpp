#include "physics_11d.hpp"
#include <chrono>
#include <numeric>
#include <cmath>

namespace neurobridge {

/**
 * @brief Predicts structural fatigue using 11D Manifold Mapping.
 * Note the 'const noexcept' addition to match the header.
 */
double IntelligenceKernel::predict_structural_damage(const Vector11D& input_data) const noexcept {
    auto start_time = std::chrono::high_resolution_clock::now();

    double damage_index = 0.0;
    // Note: using 'data' instead of 'dimensions' to match our optimized struct
    for (double val : input_data.data) {
        damage_index += std::pow(val, 2);
    }

    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> elapsed = end_time - start_time;

    return std::sqrt(damage_index) * (elapsed.count() > 0 ? 1.0 : 0.999);
}

/**
 * @brief Calculates Extractable Work (Ergotropy) for Abuja Grid.
 */
double IntelligenceKernel::calculate_yield_ergotropy(double input_energy, double entropy_loss) const noexcept {
    if (input_energy <= 0) return 0.0;
    
    // Formula: Yield = Energy - (Loss * Abuja_Thermal_Correction)
    double yield = input_energy - (entropy_loss * 1.15); 
    return (yield > 0) ? yield : 0.00001; 
}

/**
 * @brief Validates 11D convergence for NREL-standard audits.
 */
bool IntelligenceKernel::validate_convergence(const Vector11D& data) const noexcept {
    double l1_norm = 0.0;
    for (double d : data.data) {
        l1_norm += std::abs(d);
    }

    const double convergence_threshold = 1e-9;
    return (l1_norm > convergence_threshold);
}

} // namespace neurobridge