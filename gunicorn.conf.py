# ============================================================================
# NEUROBRIDGE 11D - GUNICORN PRODUCTION CONFIGURATION
# Version: 8.0.0-ENTERPRISE-INFINITE
# Deployment: Cloud-Agnostic (AWS, GCP, Azure, Oracle, NVIDIA)
# ============================================================================
# Optimized for:
#   - High concurrency with low memory footprint
#   - Graceful worker recycling
#   - Proper logging for production environments
#   - Compatibility with all cloud platforms
# ============================================================================

import multiprocessing
import os
import sys

# ============================================================================
# SERVER SOCKET CONFIGURATION
# ============================================================================
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
backlog = int(os.environ.get("GUNICORN_BACKLOG", 2048))

# ============================================================================
# WORKER PROCESSES
# ============================================================================
# Calculate optimal worker count based on CPU cores
# Formula: (2 x CPU cores) + 1
cpu_count = multiprocessing.cpu_count()
default_workers = max(2, (cpu_count * 2) + 1)

workers = int(os.environ.get("WORKERS", default_workers))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = int(os.environ.get("WORKER_CONNECTIONS", 1000))
max_requests = int(os.environ.get("MAX_REQUESTS", 10000))
max_requests_jitter = int(os.environ.get("MAX_REQUESTS_JITTER", 1000))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = int(os.environ.get("GRACEFUL_TIMEOUT", 30))
keepalive = int(os.environ.get("KEEPALIVE", 5))

# Threads per worker (for multi-threading)
threads = int(os.environ.get("GUNICORN_THREADS", 2))

# ============================================================================
# MEMORY MANAGEMENT
# ============================================================================
# Maximum number of requests a worker will process before restarting
# Prevents memory leaks
max_requests = 10000
max_requests_jitter = 1000

# Worker temporary directory
worker_tmp_dir = "/dev/shm"

# ============================================================================
# SECURITY & LIMITS
# ============================================================================
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "/app/logs/gunicorn_access.log")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "/app/logs/gunicorn_error.log")
loglevel = os.environ.get("LOG_LEVEL", "info")

# Structured access log format (JSON-compatible)
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s %(p)s'

# Log to stdout for container environments (12-factor app)
if os.environ.get("ENVIRONMENT", "production") == "container":
    accesslog = "-"
    errorlog = "-"

# ============================================================================
# PROCESS NAMING
# ============================================================================
proc_name = "neurobridge-11d"
default_proc_name = proc_name

# ============================================================================
# DEVELOPMENT VS PRODUCTION
# ============================================================================
# Disable reload and daemon mode in production
reload = os.environ.get("GUNICORN_RELOAD", "false").lower() == "true"
daemon = False

# Preload app for better performance (only if using multiple workers)
preload_app = workers > 1

# ============================================================================
# SIGNAL HANDLING
# ============================================================================
# Graceful shutdown on SIGTERM
graceful_timeout = 30

# ============================================================================
# PROMETHEUS METRICS (Optional)
# ============================================================================
# Enable statsd metrics if configured
if os.environ.get("ENABLE_METRICS", "true").lower() == "true":
    try:
        from prometheus_client import multiprocess
        multiprocess.mark_process_dead(os.getpid())
    except ImportError:
        pass

# ============================================================================
# PERFORMANCE TUNING
# ============================================================================
# Sendfile system call optimization
sendfile = True

# Enable sticky sessions if behind load balancer
# forwarder_allow_ips = "*"

# ============================================================================
# PRINT CONFIGURATION ON STARTUP (for debugging)
# ============================================================================
if os.environ.get("LOG_LEVEL", "info") == "debug":
    print(f"Gunicorn Configuration:", file=sys.stderr)
    print(f"  bind: {bind}", file=sys.stderr)
    print(f"  workers: {workers}", file=sys.stderr)
    print(f"  worker_class: {worker_class}", file=sys.stderr)
    print(f"  threads: {threads}", file=sys.stderr)
    print(f"  timeout: {timeout}", file=sys.stderr)
    print(f"  max_requests: {max_requests}", file=sys.stderr)