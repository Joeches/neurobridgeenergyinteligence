#!/bin/bash

# Project: NeuroBridge 11D Energy Intelligence Kernel
# Component: Sovereign Node Initialization & Deployment Script
# Author: Lead AI Design Architect & Systems Designer
# Description: Unified Development & Production setup for Abuja Pilot.

# --- ANSI WEALTH COLOR SCHEME ---
GOLD='\033[0;33m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GOLD}"
echo "--------------------------------------------------------"
echo "   NEUROBRIDGE 11D: SOVEREIGN SYSTEM INITIALIZATION      "
echo "   TARGET: ABUJA PILOT NODE-01 | REGION: NIGERIA        "
echo "--------------------------------------------------------"
echo -e "${NC}"

# 1. ENVIRONMENT & ARCHITECTURE DISCOVERY
echo -e "[*] ${CYAN}IDENTIFYING SYSTEM ARCHITECTURE...${NC}"
OS_TYPE=$(uname -s)
ARCH=$(uname -m)
CPU_CORES=$(nproc 2>/dev/null || echo 4)

if [[ "$OS_TYPE" == *"MSYS"* || "$OS_TYPE" == *"MINGW"* ]]; then
    ENV_MODE="DEVELOPMENT (Windows/UCRT64)"
else
    ENV_MODE="PRODUCTION (Linux/Ubuntu)"
fi

echo -e "[+] MODE: ${GREEN}$ENV_MODE${NC} | ARCH: ${GREEN}$ARCH${NC} | CORES: ${GREEN}$CPU_CORES${NC}"

# 2. TOOLCHAIN SYNCHRONIZATION (Linux Only)
if [[ "$ENV_MODE" == *"PRODUCTION"* ]]; then
    echo -e "[*] ${CYAN}UPDATING SOVEREIGN TOOLCHAIN (APT)...${NC}"
    sudo apt-get update -y && sudo apt-get upgrade -y
    sudo apt-get install -y \
        build-essential cmake python3-pip python3-dev \
        libboost-all-dev docker.io docker-compose git
fi

# 3. DIRECTORY & PERMISSION ALIGNMENT
echo -e "[*] ${CYAN}CALIBRATING DIRECTORY STRUCTURE...${NC}"
mkdir -p logs exports/reports core/build cache data temp
# Adjusting for Windows vs Linux pathing styles
if [[ "$ENV_MODE" == *"PRODUCTION"* ]]; then
    chmod +x backend/main.py
fi

# 4. KERNEL COMPILATION (11D PHYSICS BRIDGE)
echo -e "[*] ${CYAN}COMPILING 11D C++ KERNEL...${NC}"

if [[ "$ENV_MODE" == *"DEVELOPMENT"* ]]; then
    # --- WINDOWS/UCRT64 MANUAL LINKING ---
    VENV_PATH="./venv"
    
    # Extracting venv metadata for precise binary alignment
    PYTHON_INC=$($VENV_PATH/Scripts/python -c "import sysconfig; print(sysconfig.get_path('include'))")
    PYBIND_INC=$($VENV_PATH/Scripts/python -m pybind11 --includes)
    PYTHON_LIB_DIR=$($VENV_PATH/Scripts/python -c "import sys, os; print(os.path.join(sys.base_prefix, 'libs'))")
    PY_VER=$($VENV_PATH/Scripts/python -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")

    echo -e "[*] Linking against Python ${GOLD}$PY_VER${NC} in ${CYAN}$PYTHON_LIB_DIR${NC}"

    g++ -O3 -shared -std=c++17 -fPIC \
        $PYBIND_INC \
        -I "$PYTHON_INC" \
        -I core/include \
        core/src/main.cpp core/src/physics_11d.cpp \
        -o backend/nb_11d_kernel.pyd \
        -L "$PYTHON_LIB_DIR" -lpython$PY_VER
else
    # --- LINUX/DOCKER CMAKE BUILD ---
    cd core/build
    cmake .. -DCMAKE_BUILD_TYPE=Release
    make -j$CPU_CORES
    cd ../..
fi

if [ $? -eq 0 ]; then
    echo -e "[+] ${GREEN}11D KERNEL ALIGNED & LINKED SUCCESSFULLY.${NC}"
else
    echo -e "[!] ${RED}CRITICAL COMPILATION FAILURE.${NC}"
    exit 1
fi

# 5. ORCHESTRATION & SECURITY INITIALIZATION
if [[ "$ENV_MODE" == *"PRODUCTION"* ]]; then
    echo -e "[*] ${CYAN}DEPLOYING SOVEREIGN CONTAINERS...${NC}"
    sudo systemctl start docker
    sudo systemctl enable docker
    docker-compose up -d --build
    
    echo -e "[*] ${CYAN}GENERATING INITIAL LATTICE-KEY...${NC}"
    python3 -c "from backend.utils.crypto_lattice import LatticeSecurityEngine; LatticeSecurityEngine().provision_access()"
else
    echo -e "[*] ${GOLD}SKIPPING DOCKER: Run 'uvicorn backend.main:app' to start local dev server.${NC}"
fi

echo -e "${GOLD}"
echo "--------------------------------------------------------"
echo "  SYSTEM DEPLOYMENT COMPLETE | NODE OPERATIONAL        "
echo "  CORE STATUS: NATIVE C++ ENGINE BOUND                 "
echo "  SECURITY STATUS: LATTICE-GUARD-READY                 "
echo "--------------------------------------------------------"
echo -e "${NC}"