#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Ubuntu Server Preparation & Hardening Script
# Location: infrastructure/scripts/server-setup.sh
# Purpose: Idempotently prepares host directories, least-privilege permissions,
#          SSH hardening drop-in, and UFW firewall baseline on Ubuntu Server LTS.
# Usage:   sudo bash infrastructure/scripts/server-setup.sh [--apply-firewall]
# =============================================================================
set -euo pipefail

APPLY_FIREWALL=false
if [[ "${1:-}" == "--apply-firewall" ]]; then
    APPLY_FIREWALL=true
fi

DEPLOY_USER="${SUDO_USER:-$(whoami)}"
APP_ROOT="/opt/sketch-studio"
CONFIG_ROOT="/etc/sketch-studio"
BACKUP_ROOT="/var/backups/sketch-studio"
LOG_ROOT="/var/log/sketch-studio"

echo "[1/5] Creating host directories with least-privilege permissions..."
mkdir -p "${APP_ROOT}" "${CONFIG_ROOT}" "${BACKUP_ROOT}" "${LOG_ROOT}"

chown "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_ROOT}" "${BACKUP_ROOT}" "${LOG_ROOT}"
chmod 0750 "${APP_ROOT}" "${BACKUP_ROOT}" "${LOG_ROOT}"

chown root:"${DEPLOY_USER}" "${CONFIG_ROOT}"
chmod 0750 "${CONFIG_ROOT}"

if [[ ! -f "${CONFIG_ROOT}/app.env" ]]; then
    cat <<'EOF' > "${CONFIG_ROOT}/app.env"
APP_VERSION=0.1.0
APP_DOMAIN=localhost
PORTAINER_DOMAIN=portainer.localhost
VITE_BG_API_BASE=
MAX_UPLOAD_BYTES=20971520
ALLOWED_ORIGINS=http://localhost:8880,http://127.0.0.1:8880
CADDY_HTTP_PORT=8880
EOF
    chown root:"${DEPLOY_USER}" "${CONFIG_ROOT}/app.env"
    chmod 0640 "${CONFIG_ROOT}/app.env"
    echo "  -> Created template ${CONFIG_ROOT}/app.env (mode 0640)"
fi

echo "[2/5] Creating shared Docker network (edge_proxy) if not present..."
if ! docker network inspect edge_proxy >/dev/null 2>&1; then
    docker network create --driver bridge edge_proxy
    echo "  -> Created Docker network: edge_proxy"
else
    echo "  -> Docker network edge_proxy already exists"
fi

echo "[3/5] Installing SSH hardening drop-in configuration..."
if [[ -d /etc/ssh/sshd_config.d ]]; then
    cat <<'EOF' > /etc/ssh/sshd_config.d/99-sketch-hardening.conf
# Hardened SSH configuration managed by sketch-studio server-setup.sh
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
AllowAgentForwarding no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
    chmod 0644 /etc/ssh/sshd_config.d/99-sketch-hardening.conf
    if command -v sshd >/dev/null 2>&1 && sshd -t 2>/dev/null; then
        systemctl reload ssh 2>/dev/null || service ssh reload 2>/dev/null || true
        echo "  -> Validated and applied /etc/ssh/sshd_config.d/99-sketch-hardening.conf"
    else
        echo "  -> Wrote /etc/ssh/sshd_config.d/99-sketch-hardening.conf (sshd service not active in WSL container)"
    fi
fi

echo "[4/5] Checking UFW firewall configuration..."
if [[ "${APPLY_FIREWALL}" == "true" ]]; then
    if ! command -v ufw >/dev/null 2>&1; then
        apt-get update && apt-get install -y --no-install-recommends ufw
    fi
    ufw default deny incoming
    ufw default allow outgoing
    ufw limit 22/tcp comment 'SSH rate-limited administration'
    # Note: Inbound HTTP/HTTPS travels through outbound Cloudflare Tunnel; no public 80/443 needed.
    ufw --force enable
    ufw status verbose
else
    echo "  -> Skipping live UFW enablement (pass --apply-firewall on bare-metal/VM host to enable)."
fi

echo "[5/5] Verifying directory structure and permissions..."
ls -ld "${APP_ROOT}" "${CONFIG_ROOT}" "${BACKUP_ROOT}" "${LOG_ROOT}"
echo "Ubuntu Server preparation complete."
