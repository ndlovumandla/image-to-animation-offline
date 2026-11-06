# Operations, Monitoring & Disaster Recovery Runbook (`docs/operations-runbook.md`)

## 1. Routine Health Verification

Run the automated health check at any time:
```bash
bash infrastructure/scripts/health-check.sh
```
It verifies:
1. Docker daemon responsiveness.
2. Running state and health probes of `sketch-web`, `sketch-bg-api`, `sketch-caddy`, and `sketch-portainer`.
3. End-to-end HTTP responses through Caddy (`/healthz`, `/`, `/api-health`) and security headers (`X-Content-Type-Options: nosniff`).
4. Root disk usage (`< 85%`) and RAM usage (`< 90%`).

---

## 2. Centralised Logging & Inspection

- **Caddy Structured JSON Access Logs**: Stored on the host at `/var/log/sketch-studio/access.log` with automatic rotation (`10 MiB` max file size, 5 rotated files kept).
  ```bash
  tail -f /var/log/sketch-studio/access.log
  ```
- **Application Container Logs**: All containers use Docker's `json-file` driver with `max-size: 10m` and `max-file: 3`:
  ```bash
  docker logs -f --tail 100 sketch-web
  docker logs -f --tail 100 sketch-bg-api
  docker logs -f --tail 100 sketch-caddy
  ```

---

## 3. Automated Backups & Restore Verification

### 3.1 Running a Backup
```bash
bash infrastructure/scripts/backup.sh
```
Archives `sketch_u2net_models`, `sketch_portainer_data`, `sketch_caddy_data`, `infrastructure/caddy`, `docker/`, and `/etc/sketch-studio` into `/var/backups/sketch-studio/sketch-studio-backup-<UTC-TIMESTAMP>.tar.gz` alongside a `.sha256` checksum manifest, and prunes backups older than 14 days.

### 3.2 Verifying Backup Integrity (Non-Destructive Restore Drill)
```bash
bash infrastructure/scripts/restore-test.sh
```
Verifies the cryptographic `.sha256` checksum, extracts the bundle into an isolated `/tmp/sketch-restore-verify-*` sandbox, and tests every nested volume archive (`tar -tzf`).

### 3.3 Scheduling Nightly Backups via Cron
Add the following entry to `/etc/cron.d/sketch-studio-ops`:
```cron
# Nightly backup at 02:15 UTC + weekly restore verification on Sundays at 02:30 UTC
15 2 * * * mandla /bin/bash /opt/sketch-studio/infrastructure/scripts/backup.sh >> /var/log/sketch-studio/backup.log 2>&1
30 2 * * 0 mandla /bin/bash /opt/sketch-studio/infrastructure/scripts/restore-test.sh >> /var/log/sketch-studio/backup.log 2>&1
*/5 * * * * mandla /bin/bash /opt/sketch-studio/infrastructure/scripts/health-check.sh >> /var/log/sketch-studio/health.log 2>&1
```
