# Security & Host Hardening Guide (`docs/security-hardening.md`)

## 1. Defense-in-Depth Controls Implemented

| Layer | Security Control | Implementation Reference |
|---|---|---|
| **Edge & Network** | Zero inbound public ports (`80`/`443` closed on router/WAN); all external traffic enters via outbound Cloudflare Tunnel (`cloudflared`) | [`docker/compose.infra.yaml`](../docker/compose.infra.yaml) |
| **Authentication** | Mandatory Cloudflare Zero Trust Access MFA policy protecting `portainer.<domain>` | [`infrastructure/cloudflare/README.md`](../infrastructure/cloudflare/README.md) |
| **Reverse Proxy** | HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`, `-Server` header stripping, 20 MB upload body limit on `/api/*` | [`infrastructure/caddy/Caddyfile`](../infrastructure/caddy/Caddyfile) |
| **Container Runtime** | Non-root execution (`USER 10001:10001`), `cap_drop: [ALL]`, `no-new-privileges:true`, stripped file capabilities on `/usr/bin/caddy`, CPU & memory limits | [`docker/web.Dockerfile`](../docker/web.Dockerfile), [`docker/bg-api.Dockerfile`](../docker/bg-api.Dockerfile), [`docker/compose.yaml`](../docker/compose.yaml) |
| **Network Segmentation** | Application containers in production (`compose.prod.yaml`) publish **zero** host ports; internal communication uses isolated Docker bridge networks (`sketch_internal`, `edge_proxy`) | [`docker/compose.prod.yaml`](../docker/compose.prod.yaml) |
| **Admin Interfaces** | Portainer CE bound strictly to `127.0.0.1:9443` and mounts `/var/run/docker.sock:ro` read-only | [`docker/compose.infra.yaml`](../docker/compose.infra.yaml) |
| **Host OS & SSH** | `PermitRootLogin no`, `PasswordAuthentication no`, `MaxAuthTries 3`, `X11Forwarding no`, secrets in `/etc/sketch-studio/app.env` (`0640`) | [`infrastructure/scripts/server-setup.sh`](../infrastructure/scripts/server-setup.sh) |
| **Supply Chain & CI** | Pinned Docker base images (`node:22.14.0-bookworm-slim`, `caddy:2.9.1-alpine`, `python:3.12.9-slim-bookworm`), `npm audit --audit-level=high`, Aqua Trivy container vulnerability scanning | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) |
