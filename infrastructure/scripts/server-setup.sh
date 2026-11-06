#!/usr/bin/env bash
# =============================================================================
# Sketch Video Studio — Full Ubuntu Server LTS Bootstrap & Hardening Script
# Location: infrastructure/scripts/server-setup.sh
# Purpose:  Takes a brand-new Ubuntu Server LTS (24.04 / 26.04) from a fresh OS
#           install to a hardened, Docker-ready production host:
#             1. Installs system packages, unattended-upgrades, fail2ban, UFW
#             2. Installs official Docker Engine + Docker Compose v2 plugin
#             3. Creates /opt/sketch-studio, /etc/sketch-studio, /var/backups, /var/log
#             4. Applies SSH hardening drop-in & optional UFW firewall rules
#             5. Installs automated cron schedules for health checks & backups
# Usage:    sudo bash infrastructure/scripts/server-setup.sh [--apply-firewall]
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

echo "[1/6] Installing essential Ubuntu Server packages & security updates..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    git \
    jq \
    tar \
    unattended-upgrades \
    fail2ban

echo "[2/6] Checking / Installing Docker Engine & Docker Compose v2..."
if ! command -v docker >/dev/null 2>&1; then
    echo "  -> Docker not found. Installing official Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    UBUNTU_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-noble}")"
    # Fallback to noble if Ubuntu 26.04 (resolute) repo alias is not yet published by Docker
    if ! curl -fsSL "https://download.docker.com/linux/ubuntu/dists/${UBUNTU_CODENAME}/Release" >/dev/null 2>&1; then
        UBUNTU_CODENAME="noble"
    fi

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      ${UBUNTU_CODENAME} stable" > /etc/apt/sources.list.d/docker.list

    apt-get update -y
    apt-get install -y --no-install-recommends \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    systemctl enable --now docker
    echo "  -> Docker Engine installed and started."
else
    echo "  -> Docker is already installed: $(docker --version)"
fi

if [[ "${DEPLOY_USER}" != "root" ]] && id "${DEPLOY_USER}" >/dev/null 2>&1; then
    usermod -aG docker "${DEPLOY_USER}" || true
    echo "  -> Added user '${DEPLOY_USER}' to the 'docker' group."
fi

# Configure Docker daemon log rotation if /etc/docker/daemon.json does not exist
if [[ ! -f /etc/docker/daemon.json ]]; then
    mkdir -p /etc/docker
    cat <<'EOF' > /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
    systemctl reload docker 2>/dev/null || true
    echo "  -> Configured /etc/docker/daemon.json log rotation."
fi

echo "[3/6] Creating host directories with least-privilege permissions..."
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
TUNNEL_TOKEN=
EOF
    chown root:"${DEPLOY_USER}" "${CONFIG_ROOT}/app.env"
    chmod 0640 "${CONFIG_ROOT}/app.env"
    echo "  -> Created template ${CONFIG_ROOT}/app.env (mode 0640)"
fi

echo "[4/6] Creating shared Docker network (edge_proxy) if not present..."
if ! docker network inspect edge_proxy >/dev/null 2>&1; then
    docker network create --driver bridge edge_proxy
    echo "  -> Created Docker network: edge_proxy"
else
    echo "  -> Docker network edge_proxy already exists"
fi

echo "[5/6] Installing SSH hardening drop-in & optional UFW firewall..."
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
    fi
fi

if [[ "${APPLY_FIREWALL}" == "true" ]]; then
    if ! command -v ufw >/dev/null 2>&1; then
        apt-get install -y --no-install-recommends ufw
    fi
    ufw default deny incoming
    ufw default allow outgoing
    ufw limit 22/tcp comment 'SSH rate-limited administration'
    ufw --force enable
    ufw status verbose
else
    echo "  -> Skipping live UFW enablement (pass --apply-firewall on bare-metal/VM host to enable)."
fi

echo "[6/6] Installing automated cron schedules for backups and health checks..."
if [[ -d /etc/cron.d ]]; then
    cat <<EOF > /etc/cron.d/sketch-studio-ops
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
# Run health check every 5 minutes
*/5 * * * * ${DEPLOY_USER} /bin/bash ${APP_ROOT}/infrastructure/scripts/health-check.sh >> ${LOG_ROOT}/health.log 2>&1
# Run automated backup daily at 02:15 UTC
15 2 * * * ${DEPLOY_USER} /bin/bash ${APP_ROOT}/infrastructure/scripts/backup.sh >> ${LOG_ROOT}/backup.log 2>&1
# Run non-destructive restore verification every Sunday at 02:30 UTC
30 2 * * 0 ${DEPLOY_USER} /bin/bash ${APP_ROOT}/infrastructure/scripts/restore-test.sh >> ${LOG_ROOT}/backup.log 2>&1
EOF
    chmod 0644 /etc/cron.d/sketch-studio-ops
    echo "  -> Installed /etc/cron.d/sketch-studio-ops"
fi

ls -ld "${APP_ROOT}" "${CONFIG_ROOT}" "${BACKUP_ROOT}" "${LOG_ROOT}"
echo "Ubuntu Server preparation complete."
