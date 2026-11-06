# Portainer Community Edition (CE) Operations Guide

## 1. Security Posture

- **Image**: `portainer/portainer-ce:2.27.1-alpine` (Apache-2.0 / Zlib Open-Source Community Edition).
- **Network Binding**: Bound strictly to `127.0.0.1:9443` on the Ubuntu Server (`127.0.0.1:9443:9443`) and attached to the internal `edge_proxy` Docker network.
- **Zero Direct Internet Exposure**: Port `9443` and Port `9000` are never published on `0.0.0.0`.
- **Docker Socket Mount**: `/var/run/docker.sock` is mounted read-only (`:ro`) with `no-new-privileges:true`.
- **Telemetry Disabled**: Started with `--no-analytics`.

---

## 2. How to Access Portainer Safely

### Option A: Local / SSH Tunnel Access (Recommended for Emergency & Initial Setup)
From your workstation, forward local port `9443` over SSH:
```bash
ssh -L 9443:127.0.0.1:9443 mandla@<ubuntu-server-ip>
```
Then open `https://localhost:9443` in your browser and complete the initial administrator password setup within 5 minutes of container start.

### Option B: Via Cloudflare Access (`portainer.yourdomain.com`)
When routed via Caddy (`http://{$PORTAINER_DOMAIN}` -> `sketch-portainer:9000`), ensure the **Cloudflare Access Self-Hosted Policy** (documented in `infrastructure/cloudflare/README.md`) is active before adding the public hostname in your Cloudflare Tunnel.

---

## 3. Backup & Recovery

Portainer's persistent state is stored in the `sketch_portainer_data` Docker volume and is automatically archived every night by `infrastructure/scripts/backup.sh` into `/var/backups/sketch-studio/`.
