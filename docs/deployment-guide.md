# Zero-to-Production Manual: Fresh Ubuntu Server 26.04 LTS (`docs/deployment-guide.md`)

This guide assumes you have **just finished installing Ubuntu Server 26.04 LTS** on a machine, you are staring at the terminal prompt for the very first time, and you want to take **Sketch Video Studio** from zero to a fully hardened, monitored, backed-up production deployment accessible on the internet.

---

## STEP 1: First Login, System Update & Installing Git

Log into your newly installed Ubuntu Server (either directly at the keyboard or via SSH: `ssh youruser@<server-lan-ip>`).

Run the following command to update the operating system package index and install `git` and `curl`:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl ca-certificates
```

*(Optional) Find your server's local network IP address so you can SSH into it from your main computer:*
```bash
ip -br addr show
```

---

## STEP 2: Clone the Repository into `/opt/sketch-studio`

Create the `/opt/sketch-studio` directory, give your Linux user ownership of it, and clone your repository:

```bash
sudo mkdir -p /opt/sketch-studio
sudo chown "$USER:$USER" /opt/sketch-studio
git clone https://github.com/ndlovumandla/image-to-animation-offline.git /opt/sketch-studio
cd /opt/sketch-studio
```

---

## STEP 3: Run the Automated Ubuntu Server Setup & Docker Installer

We have included an automated bootstrap script (`infrastructure/scripts/server-setup.sh`) that installs **Docker Engine**, **Docker Compose v2**, **Fail2ban**, **Unattended Security Upgrades**, **UFW Firewall**, hardens **SSH**, creates `/etc/sketch-studio/app.env`, `/var/backups/sketch-studio`, `/var/log/sketch-studio`, creates the `edge_proxy` Docker network, and registers the automated backup & health-check cron jobs.

### 3.1 Important: Ensure You Have an SSH Key Before Locking Down Password SSH (If Connecting Remotely)
If you connect to this Ubuntu Server via SSH using a password, add your SSH public key to `~/.ssh/authorized_keys` first (because `server-setup.sh` hardens SSH to key-only login), or skip SSH password disablement until your key is added.

### 3.2 Run the Bootstrap Script
On a standalone Ubuntu Server (bare-metal or VM), run:
```bash
cd /opt/sketch-studio
sudo bash infrastructure/scripts/server-setup.sh --apply-firewall
```
*(Note: If running inside WSL2 on Windows, omit `--apply-firewall` and run `sudo bash infrastructure/scripts/server-setup.sh`.)*

### 3.3 Refresh Your User Group Membership
Because the script adds your user to the `docker` group so you don't need `sudo` for every Docker command, activate the new group in your current shell:
```bash
newgrp docker
docker --version
docker compose version
```

---

## STEP 4: Build & Start the Production Application Locally First

Before connecting Cloudflare, build and start the infrastructure stack (Caddy + Portainer) and the application stack (React Frontend + FastAPI U²-Net AI Backend) and verify everything works on the server:

```bash
cd /opt/sketch-studio

# 1. Start Central Caddy Reverse Proxy + Portainer CE
docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.infra.yaml up -d

# 2. Build and start Sketch Video Studio (Frontend + AI Backend)
docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.yaml -f docker/compose.prod.yaml up --build -d
```

> [!NOTE]
> The very first build downloads the Node 22, Python 3.12, Caddy, and Portainer base images and installs `rembg`, `onnxruntime`, and `opencv-python-headless`. This first build takes **5–12 minutes** depending on your internet speed. Subsequent restarts take **< 5 seconds**.

### Verify Everything Is Healthy
Run the built-in 10-point health verification script:
```bash
bash /opt/sketch-studio/infrastructure/scripts/health-check.sh
```
You should see:
```text
OVERALL STATUS: HEALTHY (0 failures)
```

---

## STEP 5: Expose Your Server to the Internet Safely (Cloudflare Tunnel + Zero Trust Access)

With Cloudflare Tunnel (`cloudflared`), **you do NOT need to open ports 80 or 443 on your router**, and your home/office IP address remains completely hidden.

### 5.1 Create the Tunnel in Cloudflare Dashboard
1. Log into [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) (Free plan supports up to 50 users at $0).
2. In the left sidebar, click **Networks -> Tunnels** -> **Create a tunnel**.
3. Choose **Cloudflared**, name the tunnel `ubuntu-sketch-server`, and click **Save tunnel**.
4. Copy the **Tunnel Token** (a long string starting with `eyJhIjoi...`).

### 5.2 Add Your Public Hostnames in the Tunnel Settings
In the Cloudflare Tunnel **Public Hostname** tab, add two routes:

1. **Main Application Route**:
   - **Subdomain**: `sketch` (or leave blank for root domain)
   - **Domain**: `yourdomain.com`
   - **Service Type**: `HTTP`
   - **URL**: `sketch-caddy:80`
2. **Portainer Management Route**:
   - **Subdomain**: `portainer`
   - **Domain**: `yourdomain.com`
   - **Service Type**: `HTTP`
   - **URL**: `sketch-caddy:80`

### 5.3 Protect Portainer with Cloudflare Zero Trust Access (Mandatory)
Before starting the tunnel, lock down `portainer.yourdomain.com` so only you can reach it:
1. In Cloudflare Zero Trust, go to **Access -> Applications -> Add an application -> Self-hosted**.
2. Set **Application name** to `Portainer Admin` and **Application domain** to `portainer.yourdomain.com`.
3. Create a policy named `Allow Admin`:
   - **Action**: `Allow`
   - **Include rule**: `Emails` -> enter your email address.
4. Save the application. Now anyone visiting `https://portainer.yourdomain.com` must pass Cloudflare email OTP / MFA before a single packet reaches your Ubuntu Server.

### 5.4 Activate the Tunnel on Your Ubuntu Server
Open `/etc/sketch-studio/app.env` on your Ubuntu Server:
```bash
sudo nano /etc/sketch-studio/app.env
```
Update these three lines with your real domain and tunnel token:
```ini
APP_DOMAIN=sketch.yourdomain.com
PORTAINER_DOMAIN=portainer.yourdomain.com
ALLOWED_ORIGINS=https://sketch.yourdomain.com,http://localhost:8880
TUNNEL_TOKEN=eyJhIjoi...paste_your_token_here...
```
Save (`Ctrl+O`, `Enter`) and exit (`Ctrl+X`).

Now apply the configuration and start the Cloudflare Tunnel container:
```bash
cd /opt/sketch-studio
docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.infra.yaml --profile tunnel up -d --force-recreate
docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.yaml -f docker/compose.prod.yaml up -d
```

Your application is now live worldwide over HTTPS at **`https://sketch.yourdomain.com`**!

---

## STEP 6: Monitoring & Container Management

### 6.1 Portainer CE Web UI
1. First time setup: If you haven't created your Portainer admin account yet, restart Portainer (`docker restart sketch-portainer`) and immediately open `https://portainer.yourdomain.com` (or via SSH tunnel `ssh -L 9443:127.0.0.1:9443 youruser@<server-ip>` -> `https://localhost:9443`).
2. Create your admin username and strong password.
3. Click **Get Started -> local environment** to view live container CPU, RAM, logs, and health states in real time.

### 6.2 Command-Line Monitoring & Logs
```bash
# Run full 10-point health check manually anytime
bash /opt/sketch-studio/infrastructure/scripts/health-check.sh

# View live container resource usage (CPU / RAM / Network I/O)
docker stats

# View structured JSON access logs from Caddy
tail -f /var/log/sketch-studio/access.log

# View automated 5-minute health-check cron logs
tail -f /var/log/sketch-studio/health.log

# View application container logs
docker logs -f --tail 100 sketch-web
docker logs -f --tail 100 sketch-bg-api
docker logs -f --tail 100 sketch-cloudflared
```

---

## STEP 7: Version Control, Updating, Rollbacks & Backups

### 7.1 Workflow for Making Changes & Updating Production
1. **On your development machine**:
   ```bash
   git add -A
   git commit -m "feat: describe your change"
   git push origin main
   ```
   GitHub Actions (`CI — Build, Test & Security Scan`) automatically runs unit tests, TypeScript checks, `npm audit`, and Trivy security scans on every push.

2. **On your Ubuntu Server (Pulling & Deploying the Update Safely)**:
   ```bash
   cd /opt/sketch-studio
   git pull --ff-only origin main
   docker compose --env-file /etc/sketch-studio/app.env -f docker/compose.yaml -f docker/compose.prod.yaml build
   bash infrastructure/scripts/deploy.sh 0.1.1
   ```
   What `deploy.sh` does automatically:
   - Saves your previous version tag to `/var/backups/sketch-studio/last-known-good-version`
   - Runs a full backup (`backup.sh`) of all Docker volumes and configs
   - Updates `APP_VERSION` and restarts the containers
   - Runs `health-check.sh` — and **automatically rolls back** if any health check fails!

### 7.2 Instant Manual Rollback
If you ever want to revert to the previous version:
```bash
cd /opt/sketch-studio
bash infrastructure/scripts/rollback.sh
```

### 7.3 Running Backups & Restore Drills Manually
Backups run automatically every night at `02:15 UTC` via `/etc/cron.d/sketch-studio-ops`, and a non-destructive restore test runs every Sunday at `02:30 UTC`. You can also trigger them manually anytime:
```bash
# Create an immediate backup in /var/backups/sketch-studio/
bash /opt/sketch-studio/infrastructure/scripts/backup.sh

# Verify the latest backup archive is 100% intact and recoverable
bash /opt/sketch-studio/infrastructure/scripts/restore-test.sh
```
