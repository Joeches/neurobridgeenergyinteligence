# ============================================================================
# NeuroBridge 11D - Production Dockerfile
# Phase 1: Solar | Grid Stability | AECE | ADFI | External API | PWA
# Version: 14.8.1 | Production Ready
# ============================================================================

FROM python:3.11-slim-bookworm

WORKDIR /app

# ============================================================================
# SYSTEM DEPENDENCIES - HARDENED PRODUCTION INSTALL
# ============================================================================
# netcat-openbsd replaced with netcat-traditional due to Debian mirror
# synchronization issues (400 Bad Request on some mirrors).
# All apt operations use --no-install-recommends for minimal image size.
# ============================================================================

RUN apt-get update -o Acquire::Retries=10 -o Acquire::http::Timeout=30 && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        procps \
        build-essential \
        gcc \
        g++ \
        make \
        libstdc++6 \
        libffi-dev \
        libssl-dev \
        pkg-config \
        netcat-traditional \
        redis-tools \
        dumb-init \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ============================================================================
# PYTHON DEPENDENCIES
# ============================================================================

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /app/requirements.txt && \
    pip check

# ============================================================================
# APPLICATION CODE
# ============================================================================

COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY benchmarks/ /app/benchmarks/
COPY postman/ /app/postman/
COPY scripts/ /app/scripts/
COPY deploy/prometheus.yml /app/deploy/prometheus.yml
COPY deploy/nginx.conf /app/deploy/nginx.conf
COPY deploy/.env.production.example /app/deploy/.env.production.example
COPY deploy/docker-entrypoint.sh /app/docker-entrypoint.sh

# ============================================================================
# RUNTIME SETUP
# ============================================================================

RUN chmod +x /app/docker-entrypoint.sh && \
    mkdir -p \
        /app/data \
        /app/logs \
        /app/exports \
        /app/postman \
        /app/benchmarks/reports \
        /app/backups \
        /app/cache \
        /tmp/prometheus_multiproc \
        /var/run/neurobridge \
    && chmod 755 /app/logs \
    && chmod 755 /app/data

# ============================================================================
# NON-ROOT USER
# ============================================================================

RUN useradd -m -u 1000 -s /bin/bash neurobridge && \
    chown -R neurobridge:neurobridge /app && \
    chown -R neurobridge:neurobridge /tmp/prometheus_multiproc && \
    chown -R neurobridge:neurobridge /var/run/neurobridge

USER neurobridge

# ============================================================================
# HEALTH CHECK
# ============================================================================

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# ============================================================================
# ENTRYPOINT
# ============================================================================

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/app/docker-entrypoint.sh"]