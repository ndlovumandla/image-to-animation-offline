#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Automated Backup Script
# Location: infrastructure/scripts/backup.sh
# Purpose:  Backs up persistent Docker volumes (sketch_u2net_models,
#           sketch_portainer_data), Caddy configuration, and /etc/sketch-studio
#           into timestamped .tar.gz archives with SHA-256 verification and
#           automated retention pruning.
# Usage:    bash infrastructure/scripts/backup.sh
# =============================================================================
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/sketch-studio}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
WORK_DIR="$(mktemp -d "/tmp/sketch-backup-${TIMESTAMP}-XXXXXX")"
ARCHIVE_NAME="sketch-studio-backup-${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="${BACKUP_ROOT}/${ARCHIVE_NAME}"

cleanup() {
    rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

mkdir -p "${BACKUP_ROOT}" "${WORK_DIR}/volumes" "${WORK_DIR}/config"

echo "[1/4] Exporting Docker persistent volumes..."
for vol in sketch_u2net_models sketch_portainer_data sketch_caddy_data; do
    if docker volume inspect "${vol}" >/dev/null 2>&1; then
        docker run --rm \
            -v "${vol}:/volume_data:ro" \
            -v "${WORK_DIR}/volumes:/backup" \
            alpine:3.21 \
            tar -czf "/backup/${vol}.tar.gz" -C /volume_data .
        echo "  -> Archived volume: ${vol}"
    fi
done

echo "[2/4] Archiving infrastructure configuration & metadata..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cp -r "${REPO_ROOT}/docker" "${WORK_DIR}/config/docker"
cp -r "${REPO_ROOT}/infrastructure/caddy" "${WORK_DIR}/config/caddy"

if [[ -d /etc/sketch-studio && -r /etc/sketch-studio ]]; then
    cp -r /etc/sketch-studio "${WORK_DIR}/config/etc-sketch-studio" 2>/dev/null || true
fi

cat <<EOF > "${WORK_DIR}/backup-metadata.json"
{
  "timestamp_utc": "${TIMESTAMP}",
  "hostname": "$(hostname)",
  "docker_version": "$(docker --version)",
  "git_commit": "$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
}
EOF

echo "[3/4] Creating compressed bundle and SHA-256 checksum..."
tar -czf "${ARCHIVE_PATH}" -C "${WORK_DIR}" .
(cd "${BACKUP_ROOT}" && sha256sum "${ARCHIVE_NAME}" > "${ARCHIVE_NAME}.sha256")
chmod 0640 "${ARCHIVE_PATH}" "${ARCHIVE_PATH}.sha256"

echo "  -> Created archive: ${ARCHIVE_PATH} ($(du -h "${ARCHIVE_PATH}" | awk '{print $1}'))"
echo "  -> Checksum: $(cat "${ARCHIVE_PATH}.sha256")"

echo "[4/4] Pruning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_ROOT}" -maxdepth 1 -type f -name "sketch-studio-backup-*.tar.gz*" -mtime "+${RETENTION_DAYS}" -print -delete || true

echo "Backup completed successfully."
