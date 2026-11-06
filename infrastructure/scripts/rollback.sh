#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Production Rollback Script
# Location: infrastructure/scripts/rollback.sh
# Usage:    bash infrastructure/scripts/rollback.sh [target-version]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/sketch-studio/app.env}"
STATE_DIR="${STATE_DIR:-/var/backups/sketch-studio}"
LAST_GOOD_FILE="${STATE_DIR}/last-known-good-version"

TARGET_VERSION="${1:-}"
if [[ -z "${TARGET_VERSION}" && -f "${LAST_GOOD_FILE}" ]]; then
    TARGET_VERSION="$(cat "${LAST_GOOD_FILE}")"
fi

if [[ -z "${TARGET_VERSION}" ]]; then
    echo "[ERROR] No target rollback version specified and ${LAST_GOOD_FILE} not found." >&2
    exit 1
fi

echo "=== Rolling Back Sketch Video Studio to Version: ${TARGET_VERSION} ==="

if [[ -f "${ENV_FILE}" && -w "${ENV_FILE}" ]]; then
    sed -i "s/^APP_VERSION=.*/APP_VERSION=${TARGET_VERSION}/" "${ENV_FILE}"
fi
export APP_VERSION="${TARGET_VERSION}"

cd "${REPO_ROOT}"
docker compose -f docker/compose.yaml -f docker/compose.prod.yaml up -d

sleep 6
echo "Verifying health after rollback..."
bash "${SCRIPT_DIR}/health-check.sh"
echo "=== ROLLBACK COMPLETE: Version ${TARGET_VERSION} restored and healthy ==="
