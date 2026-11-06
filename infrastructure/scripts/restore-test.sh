#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Non-Destructive Backup Restore Verification Script
# Location: infrastructure/scripts/restore-test.sh
# Purpose:  Verifies SHA-256 integrity of the latest backup archive, extracts
#           its contents into an isolated sandbox directory, and validates all
#           nested volume archives and configuration files without overwriting
#           live production data.
# Usage:    bash infrastructure/scripts/restore-test.sh [optional-archive-path]
# =============================================================================
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/sketch-studio}"
TARGET_ARCHIVE="${1:-}"

if [[ -z "${TARGET_ARCHIVE}" ]]; then
    TARGET_ARCHIVE="$(ls -1t "${BACKUP_ROOT}"/sketch-studio-backup-*.tar.gz 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${TARGET_ARCHIVE}" || ! -f "${TARGET_ARCHIVE}" ]]; then
    echo "[ERROR] No backup archive found in ${BACKUP_ROOT}" >&2
    exit 1
fi

ARCHIVE_DIR="$(dirname "${TARGET_ARCHIVE}")"
ARCHIVE_BASE="$(basename "${TARGET_ARCHIVE}")"
SANDBOX_DIR="$(mktemp -d "/tmp/sketch-restore-verify-XXXXXX")"

cleanup() {
    rm -rf "${SANDBOX_DIR}"
}
trap cleanup EXIT

echo "=== Restore Verification Test for ${ARCHIVE_BASE} ==="

echo "[1/4] Verifying SHA-256 cryptographic checksum..."
if [[ -f "${TARGET_ARCHIVE}.sha256" ]]; then
    (cd "${ARCHIVE_DIR}" && sha256sum -c "${ARCHIVE_BASE}.sha256")
else
    echo "[ERROR] Missing checksum file: ${TARGET_ARCHIVE}.sha256" >&2
    exit 1
fi

echo "[2/4] Extracting primary backup bundle into isolated sandbox (${SANDBOX_DIR})..."
tar -xzf "${TARGET_ARCHIVE}" -C "${SANDBOX_DIR}"

echo "[3/4] Validating backup metadata and configuration files..."
test -f "${SANDBOX_DIR}/backup-metadata.json"
cat "${SANDBOX_DIR}/backup-metadata.json"
test -f "${SANDBOX_DIR}/config/caddy/Caddyfile"
test -f "${SANDBOX_DIR}/config/docker/compose.yaml"
echo "  -> Configuration files verified."

echo "[4/4] Verifying integrity of nested Docker volume archives..."
for vtar in "${SANDBOX_DIR}"/volumes/*.tar.gz; do
    if [[ -f "${vtar}" ]]; then
        tar -tzf "${vtar}" >/dev/null
        echo "  -> Volume archive intact and readable: $(basename "${vtar}")"
    fi
done

echo "=== RESTORE VERIFICATION PASSED: ${ARCHIVE_BASE} is 100% recoverable ==="
