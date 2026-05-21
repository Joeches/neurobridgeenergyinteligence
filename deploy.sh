#!/bin/bash
# ============================================================================
# NEUROBRIDGE 11D - UNIVERSAL DEPLOYMENT SCRIPT
# Version: 8.0.0-ENTERPRISE-INFINITE
# ============================================================================
# Supports:
#   - Docker Compose (full/lite/monitoring)
#   - Docker Swarm
#   - Kubernetes (via kompose)
#   - Cloud Platforms: AWS, GCP, Azure, Oracle, NVIDIA
# ============================================================================

set -e

# ============================================================================
# COLOR CODES
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# BANNER
# ============================================================================
echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                               ║"
echo "║   ███╗   ██╗███████╗██╗   ██╗██████╗  ██████╗ ██████╗ ██████╗ ██╗██████╗     ║"
echo "║   ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██║██╔══██╗    ║"
echo "║   ██╔██╗ ██║█████╗  ██║   ██║██████╔╝██║   ██║██████╔╝██████╔╝██║██║  ██║    ║"
echo "║   ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══██╗██╔══██╗██║██║  ██║    ║"
echo "║   ██║ ╚████║███████╗╚██████╔╝██║  ██║╚██████╔╝██████╔╝██████╔╝██║██████╔╝    ║"
echo "║   ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═╝╚═════╝     ║"
echo "║                                                                               ║"
echo "║                    SOVEREIGN QUANTUM ENERGY INTELLIGENCE                      ║"
echo "║                    ENTERPRISE EDITION - INFINITE CAPABILITIES                 ║"
echo "║                                                                               ║"
echo "║   Version: 8.0.0-ENTERPRISE-INFINITE                                          ║"
echo "║   CTO: Joseph Ochelebe | NeuroBridge Technologies Ltd                         ║"
echo "║   Deployment: Abuja Quantum Grid - Nigeria Pilot Zone                         ║"
echo "║                                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ============================================================================
# DETECT PLATFORM
# ============================================================================
detect_platform() {
    echo -e "${BLUE}🔍 Detecting platform...${NC}"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        PLATFORM="macos"
        echo -e "${GREEN}✅ Platform: macOS${NC}"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if grep -q Microsoft /proc/version 2>/dev/null; then
            PLATFORM="wsl"
            echo -e "${GREEN}✅ Platform: WSL (Windows Subsystem for Linux)${NC}"
        else
            PLATFORM="linux"
            echo -e "${GREEN}✅ Platform: Linux${NC}"
        fi
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
        PLATFORM="windows"
        echo -e "${GREEN}✅ Platform: Windows${NC}"
    else
        PLATFORM="unknown"
        echo -e "${YELLOW}⚠️ Unknown platform: $OSTYPE${NC}"
    fi
    
    # Detect architecture
    ARCH=$(uname -m)
    if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]]; then
        echo -e "${GREEN}✅ Architecture: ARM64 (Oracle Always Free compatible)${NC}"
    elif [[ "$ARCH" == "x86_64" ]]; then
        echo -e "${GREEN}✅ Architecture: AMD64${NC}"
    else
        echo -e "${YELLOW}⚠️ Architecture: $ARCH${NC}"
    fi
}

# ============================================================================
# CHECK DEPENDENCIES
# ============================================================================
check_dependencies() {
    echo -e "${BLUE}🔧 Checking dependencies...${NC}"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker found${NC}"
    
    # Check Docker Compose
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
        echo -e "${GREEN}✅ Docker Compose (standalone) found${NC}"
    elif docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
        echo -e "${GREEN}✅ Docker Compose (plugin) found${NC}"
    else
        echo -e "${RED}❌ Docker Compose not found. Please install Docker Compose.${NC}"
        exit 1
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        echo -e "${YELLOW}⚠️ curl not found. Some features may not work.${NC}"
    fi
}

# ============================================================================
# CREATE REQUIRED DIRECTORIES
# ============================================================================
create_directories() {
    echo -e "${BLUE}📁 Creating required directories...${NC}"
    
    mkdir -p logs exports data nginx/ssl prometheus grafana migrations
    echo -e "${GREEN}✅ Directories created${NC}"
}

# ============================================================================
# SETUP ENVIRONMENT FILE
# ============================================================================
setup_env() {
    echo -e "${BLUE}🔐 Setting up environment variables...${NC}"
    
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            echo -e "${YELLOW}⚠️ .env file created from .env.example${NC}"
        else
            # Create minimal .env file
            cat > .env << EOF
# NeuroBridge 11D Environment Configuration
CTO_ACCESS_CODE=$(openssl rand -hex 16 | cut -c1-32 | tr 'a-z' 'A-Z' | sed 's/\(.\{6\}\)/-\1/g' | sed 's/^-//')
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379/0
ENABLE_REDIS_CACHE=true
ENABLE_ANALYTICS=true
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+' | cut -c1-24)
JWT_SECRET=$(openssl rand -base64 32)
COMPANY_NAME="NeuroBridge Technologies Ltd"
COMPANY_CTO="Joseph Ochelebe"
COMPANY_LOCATION="Abuja, Nigeria"
COMPANY_EMAIL="neurobridgetechnologiesltd@gmail.com"
COMPANY_WHATSAPP="+2348163399026"
EOF
            echo -e "${YELLOW}⚠️ Minimal .env file created${NC}"
        fi
        echo -e "${YELLOW}⚠️ Please review and edit .env file before deployment${NC}"
    else
        echo -e "${GREEN}✅ .env file found${NC}"
    fi
}

# ============================================================================
# DEPLOY FULL MODE
# ============================================================================
deploy_full() {
    echo -e "${BLUE}🏭 Deploying FULL production mode...${NC}"
    $COMPOSE_CMD up -d --build
    echo -e "${GREEN}✅ Full deployment complete${NC}"
}

# ============================================================================
# DEPLOY LITE MODE (Oracle Always Free)
# ============================================================================
deploy_lite() {
    echo -e "${BLUE}📦 Deploying LITE mode (Oracle Always Free compatible)...${NC}"
    
    if [ -f "docker-compose.lite.yml" ]; then
        $COMPOSE_CMD -f docker-compose.lite.yml up -d --build
    else
        echo -e "${YELLOW}⚠️ docker-compose.lite.yml not found, using full compose with limited resources${NC}"
        $COMPOSE_CMD up -d --build
    fi
    echo -e "${GREEN}✅ Lite deployment complete${NC}"
}

# ============================================================================
# DEPLOY WITH MONITORING
# ============================================================================
deploy_monitoring() {
    echo -e "${BLUE}📊 Deploying with monitoring (Prometheus + Grafana)...${NC}"
    $COMPOSE_CMD --profile monitoring up -d --build
    echo -e "${GREEN}✅ Monitoring deployment complete${NC}"
}

# ============================================================================
# STOP SERVICES
# ============================================================================
stop_services() {
    echo -e "${BLUE}🛑 Stopping all services...${NC}"
    $COMPOSE_CMD down
    echo -e "${GREEN}✅ All services stopped${NC}"
}

# ============================================================================
# RESTART SERVICES
# ============================================================================
restart_services() {
    echo -e "${BLUE}🔄 Restarting all services...${NC}"
    $COMPOSE_CMD restart
    echo -e "${GREEN}✅ All services restarted${NC}"
}

# ============================================================================
# VIEW LOGS
# ============================================================================
view_logs() {
    echo -e "${BLUE}📋 Showing logs (Ctrl+C to exit)...${NC}"
    $COMPOSE_CMD logs -f
}

# ============================================================================
# CHECK STATUS
# ============================================================================
check_status() {
    echo -e "${BLUE}📊 Service status:${NC}"
    $COMPOSE_CMD ps
}

# ============================================================================
# CLEAN EVERYTHING
# ============================================================================
clean_all() {
    echo -e "${RED}🧹 Cleaning up containers and volumes...${NC}"
    read -p "Are you sure? This will delete all data! (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        $COMPOSE_CMD down -v
        echo -e "${GREEN}✅ Cleanup complete${NC}"
    else
        echo -e "${YELLOW}⚠️ Cleanup cancelled${NC}"
    fi
}

# ============================================================================
# RUN TESTS
# ============================================================================
run_tests() {
    echo -e "${BLUE}🧪 Running tests...${NC}"
    docker exec neurobridge_api python -m pytest tests/test_energy_kernel.py -v -s --tb=short
    echo -e "${GREEN}✅ Tests complete${NC}"
}

# ============================================================================
# SHOW HELP
# ============================================================================
show_help() {
    echo -e "${CYAN}NeuroBridge 11D Deployment Script${NC}"
    echo ""
    echo "Usage: ./deploy.sh [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  full       - Full production deployment"
    echo "  lite       - Lite deployment (Oracle Always Free / 1GB RAM)"
    echo "  monitoring - Full deployment with Prometheus + Grafana"
    echo "  stop       - Stop all services"
    echo "  restart    - Restart all services"
    echo "  logs       - View live logs"
    echo "  status     - Check service status"
    echo "  test       - Run pytest inside container"
    echo "  clean      - Remove all containers and volumes"
    echo "  help       - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh lite        # Deploy on Oracle Always Free"
    echo "  ./deploy.sh full        # Deploy on production server"
    echo "  ./deploy.sh status      # Check if services are running"
    echo "  ./deploy.sh logs        # View logs"
    echo ""
    echo "Cloud Platform Recommendations:"
    echo "  Oracle Always Free    -> ./deploy.sh lite"
    echo "  AWS t2.micro/t4g.micro -> ./deploy.sh lite"
    echo "  GCP e2-micro          -> ./deploy.sh lite"
    echo "  Azure B1S             -> ./deploy.sh lite"
    echo "  Production Servers    -> ./deploy.sh full"
    echo "  With Monitoring       -> ./deploy.sh monitoring"
}

# ============================================================================
# MAIN FUNCTION
# ============================================================================
main() {
    detect_platform
    check_dependencies
    create_directories
    setup_env
    
    MODE=${1:-help}
    
    case $MODE in
        full)
            deploy_full
            ;;
        lite)
            deploy_lite
            ;;
        monitoring)
            deploy_monitoring
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        logs)
            view_logs
            ;;
        status)
            check_status
            ;;
        test)
            run_tests
            ;;
        clean)
            clean_all
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}❌ Unknown command: $MODE${NC}"
            show_help
            exit 1
            ;;
    esac
    
    # Show access URLs if deployment was successful
    if [[ $MODE == "full" ]] || [[ $MODE == "lite" ]] || [[ $MODE == "monitoring" ]]; then
        echo ""
        echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}✅ NeuroBridge 11D Deployment Successful!${NC}"
        echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "${CYAN}📍 Access Points:${NC}"
        echo -e "   API:           ${GREEN}http://localhost:8000${NC}"
        echo -e "   API Docs:      ${GREEN}http://localhost:8000/api/docs${NC}"
        echo -e "   Dashboard:     ${GREEN}http://localhost:8000/dashboard${NC}"
        
        if [[ $MODE == "monitoring" ]]; then
            echo -e "   Grafana:       ${GREEN}http://localhost:3000${NC} (admin/admin)"
            echo -e "   Prometheus:    ${GREEN}http://localhost:9090${NC}"
        fi
        
        echo ""
        echo -e "${CYAN}📋 Useful Commands:${NC}"
        echo -e "   View logs:     ${YELLOW}./deploy.sh logs${NC}"
        echo -e "   Check status:  ${YELLOW}./deploy.sh status${NC}"
        echo -e "   Stop services: ${YELLOW}./deploy.sh stop${NC}"
        echo -e "   Run tests:     ${YELLOW}./deploy.sh test${NC}"
        echo ""
        echo -e "${CYAN}🏢 NeuroBridge Technologies Ltd${NC}"
        echo -e "   CTO: Joseph Ochelebe"
        echo -e "   Email: neurobridgetechnologiesltd@gmail.com"
        echo -e "   WhatsApp: +2348163399026"
        echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
    fi
}

# ============================================================================
# RUN MAIN FUNCTION
# ============================================================================
main "$@"