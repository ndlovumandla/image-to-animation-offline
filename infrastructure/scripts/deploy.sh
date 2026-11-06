#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Production Deployment Script with Auto-Rollback
# Location: infrastructure/scripts/deploy.sh
# Usage:    bash infrastructure/scripts/deploy.sh <new-app-version>
# =============================================================================
set -euo pipefail

NEW_VERSION="${1:-}"
if [[ -z "${NEW_VERSION}" ]]; then
    echo "Usage: $0 <new-app-version>" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/sketch-studio/app.env}"
STATE_DIR="${STATE_DIR:-/var/backups/sketch-studio}"
LAST_GOOD_FILE="${STATE_DIR}/last-known-good-version"

mkdir -p "${STATE_DIR}"

# 1. Record current running version for instant rollback
CURRENT_VERSION="0.1.0"
if [[ -f "${ENV_FILE}" ]]; then
    CURRENT_VERSION="$(grep -E '^APP_VERSION=' "${ENV_FILE}" | cut -d= -f2- || echo '0.1.0')"
fi
echo "${CURRENT_VERSION}" > "${LAST_GOOD_FILE}"
echo "[1/5] Recorded current version (${CURRENT_VERSION}) to ${LAST_GOOD_FILE}"

# 2. Run pre-deployment backup
echo "[2/5] Creating pre-deployment backup..."
bash "${SCRIPT_DIR}/backup.sh"

# 3. Update APP_VERSION in environment file
echo "[3/5] Setting APP_VERSION=${NEW_VERSION}..."
if [[ -f "${ENV_FILE}" && -w "${ENV_FILE}" ]]; then
    sed -i "s/^APP_VERSION=.*/APP_VERSION=${NEW_VERSION}/" "${ENV_FILE}"
fi
export APP_VERSION="${NEW_VERSION}"

# 4. Deploy updated application containers and ensure infrastructure is up
echo "[4/5] Deploying containers with APP_VERSION=${NEW_VERSION}..."
cd "${REPO_ROOT}"
docker compose -f docker/compose.infra.yaml up -d
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d --remove-orphans

# 5. Wait briefly and run post-deployment verification
echo "[5/5] Running post-deployment health verification..."
sleep 8
if bash "${SCRIPT_DIR}/health-check.sh"; then
    echo "=== DEPLOYMENT SUCCESSFUL: Version ${NEW_VERSION} is live and healthy ==="
    exit 0
else
    echo "[ERROR] Post-deployment health check failed for version ${NEW_VERSION}! Initiating automatic rollback..." >&2
    bash "${SCRIPT_DIR}/rollback.sh" "${CURRENT_VERSION}"
    exit 1
fi
