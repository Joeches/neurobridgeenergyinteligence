# Project: NeuroBridge 11D Energy Intelligence Kernel
# Component: Core Build System (MSYS2 / UCRT64 / Linux Universal)
# Author: Lead AI Design Architect & Systems Designer
# Optimized for: AVX2/NEON Hardware Acceleration

cmake_minimum_required(VERSION 3.15)
project(NeuroBridge_11D_Kernel LANGUAGES CXX)

# --- SOVEREIGN COMPILATION STANDARDS ---
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# --- HARDWARE-AWARE OPTIMIZATION LOGIC ---
if(MSVC)
    # Windows Native Optimization
    add_compile_options(/O2 /Oi /Ot /GL /arch:AVX2)
    add_link_options(/LTCG)
else()
    # MSYS2 / GCC / Clang Optimization
    # -O3 for Maximum Speed, -ffast-math for Physics throughput
    add_compile_options(-O3 -march=native -ffast-math -Wall -Wextra)
    
    # Enhanced Security: Position Independent Executable
    if(NOT APPLE)
        add_link_options("-Wl,-O1" "-Wl,--as-needed")
    endif()
endif()

# --- EXTERNAL INTELLIGENCE DEPENDENCIES ---
# Find Python & Pybind11 (Essential for 11D-to-FastAPI Bridge)
find_package(Python COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)

# --- TARGET DEFINITION: THE 11D KERNEL ---
# This produces the .pyd (Windows) or .so (Linux) binary
pybind11_add_module(nb_11d_kernel
    src/physics_11d.cpp
    src/main.cpp
)

# --- DIRECTORY ARCHITECTURE ---
target_include_directories(nb_11d_kernel PRIVATE 
    include
    ${pybind11_INCLUDE_DIRS}
    ${Python_INCLUDE_DIRS}
)

# --- METADATA & BUILD TELEMETRY ---
target_compile_definitions(nb_11d_kernel PRIVATE 
    VERSION_MAJOR=1 
    VERSION_MINOR=0 
    PILOT_SITE_ABUJA=1
    SOVEREIGN_MODE=ACTIVE
)

# --- INSTALLATION LOGIC (For Automated Deployment) ---
# Automatically places the compiled kernel into the backend directory
install(TARGETS nb_11d_kernel DESTINATION ../backend)

message(STATUS "--------------------------------------------------------")
message(STATUS " NEUROBRIDGE 11D KERNEL: BUILD SYSTEM INITIALIZED ")
message(STATUS " TARGET ARCHITECTURE: ${CMAKE_SYSTEM_PROCESSOR} ")
message(STATUS " OPTIMIZATION LEVEL: PRODUCTION / HIGH-YIELD ")
message(STATUS "--------------------------------------------------------")