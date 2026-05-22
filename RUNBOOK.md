# Operations Runbook
## NeuroBridge 11D

> Infrastructure Operations • Runtime Diagnostics • Production Recovery Procedures

---

# Overview

This runbook provides operational procedures for:

- infrastructure startup
- runtime validation
- observability diagnostics
- distributed systems recovery
- Docker orchestration troubleshooting
- reverse proxy stabilization
- metrics validation

---

# Infrastructure Components

## Core Runtime Services

| Service | Purpose |
|---|---|
| FastAPI | Backend orchestration |
| Redis | Distributed broker |
| Celery Worker | Distributed execution |
| Celery Beat | Task scheduling |
| Prometheus | Metrics aggregation |
| Grafana | Infrastructure visualization |
| NGINX | Reverse proxy |

---

# Standard Startup Procedure

## Navigate To Deployment Directory

```bash
cd deploy
```

---

# Start Infrastructure

```bash
docker compose up -d
```

---

# Verify Runtime

```bash
docker compose ps
```

---

# Expected Runtime State

```text
neurobridge-api             healthy
neurobridge-redis           healthy
neurobridge-prometheus      healthy
neurobridge-grafana         healthy
neurobridge-nginx           healthy
neurobridge-celery-worker   healthy
neurobridge-celery-beat     healthy
```

---

# API Validation

## Verify Backend Runtime

```bash
curl.exe http://127.0.0.1:8000/api/v1/health
```

---

# Expected Response

```json
{
  "status":"healthy",
  "phase":"PHASE_1_PRODUCTION"
}
```

---

# Reverse Proxy Validation

## Verify NGINX Runtime

```bash
curl.exe -I http://localhost/
```

---

# Expected Response

```text
HTTP/1.1 200 OK
Server: nginx
```

---

# Grafana Validation

## Verify Grafana Health

```bash
curl.exe http://localhost/grafana/api/health
```

---

# Expected Response

```json
{
  "database":"ok",
  "version":"13.0.1+security-01"
}
```

---

# Prometheus Validation

## Verify Metrics Runtime

```bash
curl.exe http://127.0.0.1:8000/metrics
```

---

# Expected Metrics

```text
neurobridge_api_requests_total
neurobridge_aece_decision_latency_ms
neurobridge_auto_control_latency_ms
```

---

# Runtime Diagnostics

## View Infrastructure Logs

```bash
docker compose logs --tail=100
```

---

# View Specific Service Logs

## API Logs

```bash
docker compose logs api --tail=100
```

---

## NGINX Logs

```bash
docker compose logs nginx --tail=100
```

---

## Redis Logs

```bash
docker compose logs redis --tail=100
```

---

## Grafana Logs

```bash
docker compose logs grafana --tail=100
```

---

# Distributed Runtime Validation

## Verify Celery Scheduling

Expected operational logs:

```text
Scheduler: Sending due task hardware-telemetry-poll
Scheduler: Sending due task adfi-orchestration
Scheduler: Sending due task aece-risk-monitor
Scheduler: Sending due task energy-metrics-update
```

---

# Native Runtime Validation

## Verify Native Kernel Runtime

Expected runtime:

```text
[KERNEL] native loaded version=13.0.0
```

---

# ADFI Runtime Validation

## Verify ADFI Runtime

Expected logs:

```text
[ADFI] deterministic mode active
```

---

# Startup Validation

## Expected Startup Completion

```text
[STARTUP] complete kernel=compiled adfi=True auth=True redis=True pwa=True connectors=True metrics=True
```

---

# Recovery Procedures

# Redis Recovery

## Restart Redis

```bash
docker compose restart redis
```

---

# Verify Redis Runtime

```bash
docker compose ps
```

---

# Expected State

```text
neurobridge-redis healthy
```

---

# NGINX Recovery

## Restart NGINX

```bash
docker compose restart nginx
```

---

# Verify Reverse Proxy

```bash
curl.exe -I http://localhost/
```

---

# Grafana Recovery

## Restart Grafana

```bash
docker compose restart grafana
```

---

# Verify Grafana Runtime

```bash
curl.exe http://localhost/grafana/api/health
```

---

# Full Infrastructure Recovery

## Stop Infrastructure

```bash
docker compose down
```

---

# Restart Infrastructure

```bash
docker compose up -d
```

---

# Verify Runtime

```bash
docker compose ps
```

---

# Common Runtime Issues

# NGINX Restart Loop

## Symptoms

```text
Restarting (1)
```

---

# Common Causes

- invalid proxy buffer configuration
- Grafana proxy routing issues
- runtime permission issues
- invalid nginx.conf syntax

---

# Validation Command

```bash
docker logs neurobridge-nginx --tail 20
```

---

# Redis Unhealthy Runtime

## Symptoms

```text
dependency failed to start: container neurobridge-redis is unhealthy
```

---

# Common Causes

- Redis persistence permissions
- appendonlydir permission issues
- corrupted runtime volumes

---

# Recovery Procedure

```bash
docker compose down -v
docker compose up -d
```

---

# Grafana Redirect Loop

## Symptoms

```text
ERR_TOO_MANY_REDIRECTS
```

---

# Common Causes

- incorrect proxy routing
- invalid iframe paths
- incorrect Grafana root URL
- reverse proxy misconfiguration

---

# Validation

```bash
curl.exe http://localhost/grafana/api/health
```

---

# GitHub Push Protection

## Common Issues

- credential exposure
- oversized artifacts
- runtime build outputs

---

# Recommended Fixes

Remove:

```text
credentials/
build/
*.pyd
*.obj
*.lib
```

---

# Repository Hygiene

## Protected Runtime Files

```text
.env
secrets/
credentials/
logs/
exports/
data/
venv/
build/
```

---

# Security Enforcement

## Phase-1 Restricted Domains

Restricted domains:

```text
nuclear
fusion
quantum
defense
```

---

# Verified Enforcement

```text
blocked_domains=nuclear,fusion,quantum,defense
```

---

# Operational Best Practices

Recommended operational practices:

- verify metrics regularly
- validate Docker health states
- monitor Redis availability
- validate Celery scheduling
- monitor Grafana dashboards
- verify Prometheus aggregation

---

# Recommended Monitoring Targets

Monitor:

- API latency
- queue depth
- infrastructure health
- metrics exposure
- reverse proxy routing
- distributed task execution

---

# Engineering Classification

This runbook demonstrates capability in:

- Infrastructure Operations
- Platform Engineering
- Site Reliability Engineering
- Observability Engineering
- Distributed Systems Engineering
- DevOps Engineering
- Backend Infrastructure Engineering

---

# Current Operational State

## OPERATIONS RUNBOOK ESTABLISHED
## DISTRIBUTED RUNTIME VERIFIED
## OBSERVABILITY INFRASTRUCTURE VERIFIED
## RECOVERY PROCEDURES VALIDATED
## PRODUCTION ENGINEERING MATURE
