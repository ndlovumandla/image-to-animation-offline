# System & Network Architecture (`docs/architecture.md`)

## 1. High-Level Request & Data Flow

```text
[Internet Visitor / Learner / Creator]
        |
        v  (HTTPS TLS 1.3)
[Cloudflare Global Edge]
  |-- DNS (Proxied CNAME)
  |-- WAF / DDoS Mitigation
  |-- Cloudflare Zero Trust Access (Mandatory MFA on portainer.<domain>)
        |
        v  (Outbound-only encrypted QUIC/HTTP2 tunnel)
[Ubuntu Server 26.04.1 LTS]
  |
  +-- Docker Network: edge_proxy (172.x.0.0/16)
        |
        +-- sketch-cloudflared (cloudflare/cloudflared:2025.2.1)
        |       |
        |       v
        +-- sketch-caddy (caddy:2.9.1-alpine, port 80 internal / 127.0.0.1:8880 host)
                |
                |-- /*           ---> sketch-web:8080 (React 18 + Vite 8 + Fabric.js 7 SPA)
                |-- /api/*       ---> sketch-bg-api:7000 (FastAPI + rembg U²-Net + OpenCV Inpaint)
                |-- /commons/*   ---> https://commons.wikimedia.org (CORS/User-Agent Proxy)
                |-- /openverse/* ---> https://api.openverse.org (Open Media Search Proxy)
                |-- portainer.*  ---> sketch-portainer:9000 (Portainer CE 2.27.1 LTS)
```

---

## 2. Container & Network Topology

| Service | Image | Networks | Host Port Binding | Persistent Volumes |
|---|---|---|---|---|
| `sketch-web` | `sketch-video-studio-web:0.1.0` | `sketch_internal`, `edge_proxy` | None in prod (`127.0.0.1:8881:8080` in dev) | None (stateless static SPA) |
| `sketch-bg-api` | `sketch-video-studio-bg-api:0.1.0` | `sketch_internal`, `edge_proxy` | None in prod (`127.0.0.1:7000:7000` in dev) | `sketch_u2net_models` (`/home/appuser/.u2net`) |
| `sketch-caddy` | `caddy:2.9.1-alpine` | `edge_proxy` | `127.0.0.1:8880:80` | `sketch_caddy_data`, `sketch_caddy_config`, `/var/log/sketch-studio` |
| `sketch-portainer` | `portainer/portainer-ce:2.27.1-alpine` | `edge_proxy` | `127.0.0.1:9443:9443` | `sketch_portainer_data`, `/var/run/docker.sock:ro` |
| `sketch-cloudflared` | `cloudflare/cloudflared:2025.2.1` | `edge_proxy` | None (outbound tunnel only) | None |

---

## 3. Adding Additional Applications on the Same Server

Because `sketch-caddy` and `sketch-cloudflared` share the external `edge_proxy` Docker network:
1. Attach any new application's frontend/API container to the external `edge_proxy` network in its own `compose.yaml`.
2. Add a 5-line site block in [`infrastructure/caddy/Caddyfile`](../infrastructure/caddy/Caddyfile):
   ```caddyfile
   http://app2.yourdomain.com {
       import security_headers
       import access_log
       reverse_proxy app2-container:3000
   }
   ```
3. Reload Caddy with zero downtime:
   ```bash
   docker exec sketch-caddy caddy reload --config /etc/caddy/Caddyfile
   ```
4. Add `app2.yourdomain.com -> http://sketch-caddy:80` in the Cloudflare Tunnel dashboard.
