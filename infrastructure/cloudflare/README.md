# Cloudflare Tunnel & Zero Trust Access Setup Guide

## 1. Architecture Overview

All external traffic enters through Cloudflare's edge network and reaches the Ubuntu Server exclusively over an outbound-only encrypted **Cloudflare Tunnel (`cloudflared`)** to **Caddy (`sketch-caddy:80`)**.

- **Zero Inbound Router Port Forwarding**: Ports `80` and `443` do **not** need to be opened on your home/office router or UFW firewall.
- **Origin IP Concealment**: Your residential or server public IP address is never exposed in public DNS records.

---

## 2. Step-by-Step Cloudflare Tunnel Creation

1. Log in to the **Cloudflare Zero Trust Dashboard** (`https://one.dash.cloudflare.com`).
2. Navigate to **Networks -> Tunnels** and click **Create a tunnel**.
3. Select **Cloudflared** as the connector type and name the tunnel `ubuntu-home-server`.
4. Copy the generated **Tunnel Token** (`eyJhIjoi...`) and store it on the Ubuntu Server inside `/etc/sketch-studio/app.env` (permissions `0640`):
   ```bash
   TUNNEL_TOKEN=eyJhIjoi...
   APP_DOMAIN=sketch.yourdomain.com
   PORTAINER_DOMAIN=portainer.yourdomain.com
   ```
5. In the tunnel's **Public Hostname** tab, add two routes:
   - **Route 1 (Application)**:
     - Subdomain: `sketch`
     - Domain: `yourdomain.com`
     - Service Type: `HTTP`
     - URL: `sketch-caddy:80`
   - **Route 2 (Portainer Admin — Protected by Cloudflare Access)**:
     - Subdomain: `portainer`
     - Domain: `yourdomain.com`
     - Service Type: `HTTP`
     - URL: `sketch-caddy:80`
6. Start the tunnel container on the Ubuntu Server:
   ```bash
   docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.infra.yaml --profile tunnel up -d
   ```

---

## 3. Securing Applications & Portainer with Cloudflare Access (Zero Trust)

### 3.1 Mandatory Access Policy for `portainer.yourdomain.com`
Portainer must **never** be publicly accessible without pre-authentication at the Cloudflare edge:
1. In Cloudflare Zero Trust, navigate to **Access -> Applications -> Add an application -> Self-hosted**.
2. Set **Application domain** to `portainer.yourdomain.com`.
3. Create an **Allow** policy named `Server Administrators`:
   - **Include**: `Emails` -> your administrator email address(es).
   - **Require**: `Authentication Method` -> MFA / One-time PIN / GitHub OAuth / Google Workspace.
4. Enable **HttpOnly** and **SameSite=Lax** cookies with a session duration of `8 hours`.

### 3.2 Access Policy for `sketch.yourdomain.com`
- **Private / Internal Team Mode**: Add a Self-hosted Access Application for `sketch.yourdomain.com` restricting access to authorised email addresses or email domains.
- **Bypass Rule for Health Probes (Optional)**: If an external uptime monitor probes `/healthz`, create a **Bypass** policy scoped specifically to path `/healthz` restricted to your monitoring IP ranges.
