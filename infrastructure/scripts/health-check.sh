#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Comprehensive Infrastructure & Application Health Check
# Location: infrastructure/scripts/health-check.sh
# Usage:    bash infrastructure/scripts/health-check.sh
# Returns:  0 if all checks pass, non-zero if any critical check fails.
# =============================================================================
set -euo pipefail

CADDY_URL="${CADDY_URL:-http://127.0.0.1:8880}"
MAX_DISK_PCT="${MAX_DISK_PCT:-85}"
MAX_MEM_PCT="${MAX_MEM_PCT:-90}"
FAILURES=0

log_ok()   { printf "  [PASS] %s\n" "$1"; }
log_fail() { printf "  [FAIL] %s\n" "$1" >&2; FAILURES=$((FAILURES + 1)); }

echo "=== Sketch Video Studio Health Check ($(date -u +"%Y-%m-%dT%H:%M:%SZ")) ==="

# 1. Docker Daemon Check
echo "[1/4] Checking Docker Engine..."
if docker info >/dev/null 2>&1; then
    log_ok "Docker daemon is responsive"
else
    log_fail "Docker daemon is unreachable"
fi

# 2. Container Health & Status Checks
echo "[2/4] Checking Required Containers..."
for cname in sketch-web sketch-bg-api sketch-caddy sketch-portainer; do
    if ! docker inspect "${cname}" >/dev/null 2>&1; then
        log_fail "Container '${cname}' does not exist"
        continue
    fi
    state=$(docker inspect --format '{{.State.Status}}' "${cname}")
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${cname}")
    if [[ "${state}" == "running" && ( "${health}" == "healthy" || "${health}" == "none" ) ]]; then
        log_ok "Container '${cname}' is ${state} (health: ${health})"
    else
        log_fail "Container '${cname}' is ${state} (health: ${health})"
    fi
done

# 3. End-to-End HTTP Routing via Central Caddy Reverse Proxy
echo "[3/4] Checking End-to-End HTTP Endpoints via Caddy (${CADDY_URL})..."

if curl -fsS --max-time 5 "${CADDY_URL}/healthz" | grep -q "OK"; then
    log_ok "Caddy /healthz endpoint returned 200 OK"
else
    log_fail "Caddy /healthz endpoint check failed"
fi

if curl -fsS --max-time 5 "${CADDY_URL}/" | grep -q "Sketch Video Studio"; then
    log_ok "React SPA root (/) served via Caddy"
else
    log_fail "React SPA root (/) check failed"
fi

if curl -fsS --max-time 5 "${CADDY_URL}/api-health" | grep -q '"ready":true'; then
    log_ok "FastAPI AI Backend (/api-health -> sketch-bg-api:7000/health) returned ready:true"
else
    log_fail "FastAPI AI Backend (/api-health) check failed"
fi

# Verify security headers from Caddy
headers=$(curl -sI --max-time 5 "${CADDY_URL}/")
if echo "${headers}" | grep -qi "X-Content-Type-Options: nosniff"; then
    log_ok "Security headers (X-Content-Type-Options: nosniff) present on Caddy response"
else
    log_fail "Security headers missing from Caddy response"
fi

# 4. Host Resource Utilization Checks
echo "[4/4] Checking Host Disk and Memory Thresholds..."
disk_pct=$(df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if (( disk_pct < MAX_DISK_PCT )); then
    log_ok "Root filesystem usage is ${disk_pct}% (threshold: ${MAX_DISK_PCT}%)"
else
    log_fail "Root filesystem usage is ${disk_pct}% (exceeds ${MAX_DISK_PCT}%)"
fi

mem_pct=$(free | awk '/Mem:/ {printf("%.0f", $3/$2 * 100)}')
if (( mem_pct < MAX_MEM_PCT )); then
    log_ok "System memory usage is ${mem_pct}% (threshold: ${MAX_MEM_PCT}%)"
else
    log_fail "System memory usage is ${mem_pct}% (exceeds ${MAX_MEM_PCT}%)"
fi

echo "=================================================================="
if (( FAILURES == 0 )); then
    echo "OVERALL STATUS: HEALTHY (0 failures)"
    exit 0
else
    echo "OVERALL STATUS: UNHEALTHY (${FAILURES} failure(s))" >&2
    exit 1
fi
