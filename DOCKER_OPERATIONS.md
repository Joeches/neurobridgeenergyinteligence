# Docker Operations
## NeuroBridge 11D

> Production Container Infrastructure • Distributed Orchestration • Runtime Operations

---

# Overview

NeuroBridge 11D uses Docker Compose for production-grade infrastructure orchestration.

The deployment stack includes:

- FastAPI backend
- Redis infrastructure
- Celery distributed workers
- Prometheus monitoring
- Grafana visualization
- NGINX reverse proxy
- Native C++ kernel integration

---

# Infrastructure Topology

```text
┌──────────────────────────────────────┐
│              Docker Host             │
├──────────────────────────────────────┤
│                                      │
│  ┌──────────────┐                    │
│  │    NGINX     │                    │
│  └──────┬───────┘                    │
│         │                            │
│         ▼                            │
│  ┌──────────────┐                    │
│  │   FastAPI    │                    │
│  └──────┬───────┘                    │
│         │                            │
│  ┌──────┴───────────────┐            │
│  ▼                      ▼            │
│ Redis               Celery Workers   │
│                                      │
│  ┌──────────────┐                    │
│  │ Prometheus   │                    │
│  └──────┬───────┘                    │
│         ▼                            │
│     Grafana                          │
│                                      │
└──────────────────────────────────────┘

Docker Compose Services:

Core Services
Service	Purpose
neurobridge-api	FastAPI backend
neurobridge-redis	Redis broker
neurobridge-celery-worker	Distributed task worker
neurobridge-celery-beat	Scheduler
neurobridge-prometheus	Metrics engine
neurobridge-grafana	Visualization
neurobridge-nginx	Reverse proxy
Start Infrastructure
docker compose up -d
Stop Infrastructure
docker compose down
Remove Infrastructure + Volumes
docker compose down -v
Rebuild Infrastructure
docker compose build --no-cache
Restart Infrastructure
docker compose restart
Restart Specific Service
docker compose restart nginx

Example:

docker compose restart grafana nginx api
Verify Infrastructure Health
docker compose ps

Expected healthy services:

neurobridge-api             healthy
neurobridge-redis           healthy
neurobridge-prometheus      healthy
neurobridge-grafana         healthy
neurobridge-nginx           healthy
neurobridge-celery-worker   healthy
neurobridge-celery-beat     healthy
Container Logs
API Logs
docker compose logs api --tail=100
NGINX Logs
docker compose logs nginx --tail=100
Grafana Logs
docker compose logs grafana --tail=100
Redis Logs
docker compose logs redis --tail=100
Celery Worker Logs
docker compose logs celery_worker --tail=100
Infrastructure Validation
API Health Validation
curl.exe http://127.0.0.1:8000/api/v1/health

Expected response:

{
  "status":"healthy",
  "version":"14.8.0",
  "phase":"PHASE_1_PRODUCTION"
}
Metrics Validation
curl.exe http://127.0.0.1:8000/metrics

Expected metrics:

neurobridge_api_requests_total
neurobridge_aece_decision_latency_ms
neurobridge_auto_control_latency_ms
Grafana Validation
curl.exe http://localhost/grafana/api/health

Expected response:

{
  "database":"ok",
  "version":"13.0.1+security-01"
}
Celery Validation

Expected scheduler activity:

Scheduler: Sending due task hardware-telemetry-poll
Scheduler: Sending due task adfi-orchestration
Scheduler: Sending due task aece-risk-monitor
Scheduler: Sending due task energy-metrics-update
Redis Validation
docker exec -it neurobridge-redis redis-cli ping

Expected response:

PONG
NGINX Validation
curl.exe -I http://localhost/

Expected response:

HTTP/1.1 200 OK
Common Operational Commands
View Running Containers
docker ps
View Container Resource Usage
docker stats
Enter API Container
docker exec -it neurobridge-api sh
Enter Redis Container
docker exec -it neurobridge-redis sh
Volume Management
Remove Dangling Volumes
docker volume prune
Remove Unused Images
docker image prune -a
Operational Metrics

Current observability stack monitors:

API latency
Redis health
Celery queue depth
ADFI telemetry ingestion
AECE control latency
Grafana health
Prometheus metrics
NGINX routing
Startup Validation Sequence

Expected production startup logs:

[PROMETHEUS] client library loaded
[METRICS] initialized
[ADFI] deterministic mode active
[REDIS] available
[KERNEL] native loaded version=13.0.0
[STARTUP] complete kernel=compiled adfi=True auth=True redis=True pwa=True connectors=True metrics=True
Production Hardening Recommendations
Recommended Improvements
TLS certificates
automated backups
OCI block storage snapshots
Docker image scanning
container vulnerability analysis
Prometheus retention tuning
Grafana dashboard backup automation
fail2ban integration
firewall restrictions
Security Considerations

Phase-1 restricted domains enforced:

nuclear
fusion
quantum
defense

Security layers include:

route protection
token validation
metrics sanitization
reverse proxy headers
Docker isolation
observability controls
Current Infrastructure Status

PHASE 1 PRODUCTION VERIFIED

Distributed orchestration operational.
Observability operational.
Metrics instrumentation operational.
Docker infrastructure healthy.
