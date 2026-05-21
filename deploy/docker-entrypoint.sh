#!/bin/bash
# ==============================================================================
# NeuroBridge 11D - Docker Entrypoint with Enhanced Error Handling
# Handles signals, zombie processes, and graceful shutdown
# Phase 1 Production | Version 14.8.1
# ==============================================================================

set -euo pipefail

# Color codes for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging function
log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Signal handlers for graceful shutdown
handle_sigterm() {
    log_info "Received SIGTERM signal, initiating graceful shutdown..."
    if [ -n "${child:-}" ]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
    fi
    log_info "Graceful shutdown completed"
    exit 0
}

handle_sigint() {
    log_info "Received SIGINT signal, initiating graceful shutdown..."
    if [ -n "${child:-}" ]; then
        kill -INT "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
    fi
    log_info "Graceful shutdown completed"
    exit 0
}

# Trap signals
trap handle_sigterm SIGTERM
trap handle_sigint SIGINT

# Validate environment
log_info "Starting NeuroBridge 11D Production Environment"
log_info "Python version: $(python --version 2>&1 || python3 --version 2>&1)"
log_info "Working directory: $(pwd)"

# Create necessary directories
mkdir -p /app/logs /app/data /app/backups /tmp/prometheus_multiproc

# Check if critical files exist
if [ ! -f "/app/backend/main.py" ]; then
    log_error "Critical file backend/main.py not found!"
    exit 1
fi

# Determine the command to run
if [ $# -gt 0 ]; then
    # Use provided command arguments
    CMD="$@"
    log_info "Using provided command: $CMD"
else
    # Default: start uvicorn with environment-configured settings
    HOST="${HOST:-0.0.0.0}"
    PORT="${PORT:-8000}"
    # Convert LOG_LEVEL to lowercase for uvicorn compatibility
    LOG_LEVEL=$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')
    CMD="python -m uvicorn backend.main:app --host ${HOST} --port ${PORT} --log-level ${LOG_LEVEL}"
    log_info "Using default uvicorn command"
fi

# Start the application in background
log_info "Starting application..."
$CMD &
child=$!

log_info "NeuroBridge 11D is running (PID: $child)"
log_info "Ready to accept connections on ${HOST:-0.0.0.0}:${PORT:-8000}"

# Wait for the child process
wait "$child"
exit_code=$?

if [ $exit_code -ne 0 ]; then
    log_error "Application exited with error code: $exit_code"
else
    log_info "Application exited normally with code: $exit_code"
fi

exit $exit_code