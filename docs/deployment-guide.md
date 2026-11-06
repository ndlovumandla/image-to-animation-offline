# Production Deployment Guide (`docs/deployment-guide.md`)

## 1. Prerequisites

- **OS**: Ubuntu Server LTS (`24.04 LTS` or `26.04 LTS`) with `x86_64` architecture, minimum 4 GiB RAM (8 GiB recommended for U²-Net ONNX inference), and 20 GiB free disk space.
- **Installed Packages**: Docker Engine (`26+`), Docker Compose plugin (`v2+`), `git`, `curl`, `tar`, `sha256sum`.

---

## 2. Initial Server Bootstrap (Phase 4)

Clone the repository and execute the idempotent server setup script:

```bash
sudo bash infrastructure/scripts/server-setup.sh
```

This creates:
- `/opt/sketch-studio` (`0750`, application root)
- `/etc/sketch-studio/app.env` (`0640`, environment & secrets file)
- `/var/backups/sketch-studio` (`0750`, automated backups)
- `/var/log/sketch-studio` (`0750`, rotated JSON access logs)
- Docker network `edge_proxy`
- SSH hardening drop-in `/etc/ssh/sshd_config.d/99-sketch-hardening.conf`

On a standalone bare-metal or VM Ubuntu Server, also enable the UFW firewall rules:
```bash
sudo bash infrastructure/scripts/server-setup.sh --apply-firewall
```

---

## 3. Starting the Infrastructure & Application Stacks

### 3.1 Local / LAN Production Stack (Without Cloudflare Tunnel Token)
```bash
# 1. Start Central Caddy Reverse Proxy + Portainer CE
docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.infra.yaml up -d

# 2. Build and start Sketch Video Studio (Frontend + FastAPI AI Backend)
docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.yaml -f docker/compose.prod.yaml up --build -d

# 3. Verify end-to-end health
bash infrastructure/scripts/health-check.sh
```

### 3.2 Enabling Cloudflare Tunnel for Public Zero-Trust Access
1. Populate `TUNNEL_TOKEN`, `APP_DOMAIN`, and `PORTAINER_DOMAIN` in `/etc/sketch-studio/app.env`.
2. Start the infrastructure stack with the `tunnel` profile enabled:
   ```bash
   docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.infra.yaml --profile tunnel up -d
   ```

---

## 4. Automated Releases & Rollbacks

### Deploying a New Release Version
```bash
bash infrastructure/scripts/deploy.sh 0.1.1
```
`deploy.sh` automatically records the current version, takes a full pre-deployment backup via `backup.sh`, updates `APP_VERSION`, deploys the updated containers, runs `health-check.sh`, and automatically executes `rollback.sh` if any health check fails.

### Manual Rollback to Previous Known-Good Version
```bash
bash infrastructure/scripts/rollback.sh
```
