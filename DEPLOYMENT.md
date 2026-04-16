# Snowbird — Lab VM Deployment Guide

End-to-end GitOps setup: push to `main` → GitHub Actions runs tests, builds images,
pushes to GHCR, SSHes into your VM, deploys, runs smoke tests, auto-rolls-back on
failure.

```
              ┌──────────────────────────┐
┌──────────┐  │   GitHub Actions (CI)    │   ┌──────────────────┐
│  git push│─▶│ 1. pytest (23 tests)     │──▶│  GHCR registry   │
└──────────┘  │ 2. tsc --noEmit + build  │   │  snowbird-backend│
              │ 3. build & push images   │   │  snowbird-frontend│
              └──────────┬───────────────┘   └────────┬─────────┘
                         │                            │ pull
                         ▼                            ▼
              ┌──────────────────────────┐   ┌──────────────────┐
              │   GitHub Actions (CD)    │──▶│   Lab VM         │
              │ SSH → pull → up -d       │   │  /opt/snowbird   │
              │ smoke test → keep|revert │   │  docker compose  │
              └──────────────────────────┘   └──────────────────┘
```

## Part 1 — One-time VM setup

1. **SSH into the VM** and run the bootstrap script:
   ```bash
   # Option A: pipe from the repo after you push it
   curl -fsSL https://raw.githubusercontent.com/<you>/snowbird/main/scripts/bootstrap_vm.sh | bash

   # Option B: scp the file over
   scp scripts/bootstrap_vm.sh vm:~/
   ssh vm "bash bootstrap_vm.sh"
   ```
   The script installs Docker, creates `/opt/snowbird`, generates a `.env` with a
   fresh Fernet `SECRET_KEY`, and prints a dedicated SSH deploy key you'll paste
   into GitHub.

2. **Copy runtime files to the VM**:
   ```bash
   scp docker-compose.prod.yml vm:/opt/snowbird/
   scp scripts/smoke_test.sh   vm:/opt/snowbird/scripts/
   ssh vm "chmod +x /opt/snowbird/scripts/smoke_test.sh"
   ```

3. **Edit `/opt/snowbird/.env`** on the VM — set `IMAGE_NAMESPACE` to your GitHub
   username or org (all lowercase, matches the GHCR path).

## Part 2 — GitHub repo setup

1. **Push the code** to a GitHub repo you own.

2. **Create a Personal Access Token** with `read:packages` scope:
   - GitHub → Settings → Developer settings → Personal access tokens → Fine-grained
   - Scope it to just this repo, `Packages: Read`.

3. **Add Actions secrets** at `Settings → Secrets and variables → Actions → New repository secret`:

   | Secret | Value |
   |---|---|
   | `VM_HOST` | VM hostname or IP reachable from GitHub |
   | `VM_USER` | SSH user on the VM (from bootstrap) |
   | `VM_SSH_PORT` | (optional) SSH port, defaults to 22 |
   | `VM_SSH_KEY` | Private key printed by `bootstrap_vm.sh` |
   | `GHCR_READ_TOKEN` | PAT from step 2 |
   | `SMOKE_ALPACA_KEY` | (optional) Paper-trading API key for end-to-end smoke |
   | `SMOKE_ALPACA_SECRET` | (optional) Paired secret |

   If you skip the `SMOKE_ALPACA_*` secrets, the smoke test still validates auth,
   health, and the frontend bundle — just not a live Alpaca roundtrip.

4. **(If GitHub can't reach your VM directly)** expose the VM's SSH port through
   Tailscale/Cloudflare Tunnel/port-forward. Alternative: swap to a pull-based
   flow by replacing `deploy.yml` with a Watchtower container on the VM.

## Part 3 — Deploy

### Automatic
Push to `main`. Actions runs CI → builds images → SSHes to the VM → deploys →
smoke-tests → rolls back on failure. Watch the run at `Actions` tab.

### Manual redeploy / pin a specific tag
`Actions → Deploy — SSH + smoke + auto-rollback → Run workflow →` enter a tag
like `sha-abc1234` or `latest`.

### First deploy
The first build populates GHCR. You may need to make the packages public (or
ensure the VM has the `GHCR_READ_TOKEN` so `docker login` works there too). The
CD workflow handles `docker login` automatically as part of each deploy.

## Part 4 — Validation that runs on every update

### CI (runs before any deploy)
- **23 pytest cases** covering:
  - Password hashing, JWT sign/verify, Fernet roundtrip + tamper detection
  - Model CRUD and encrypted-secret storage
  - TWR / daily returns / drawdown / empty-data handling (analytics math)
  - Bucket drift with single and nested holdings
  - Dividend history filter, year filter, per-symbol aggregation
  - API smoke: register → login → `/me` → auth enforcement
- **Frontend typecheck** (`tsc --noEmit`) + production `vite build`

### Post-deploy (runs on the VM)
- Backend `/api/health` poll (up to 60s)
- Frontend bundle served from port 8080
- Demo user login → JWT → authenticated `/api/accounts` call
- **If `SMOKE_ALPACA_*` secrets are set**: adds a paper account, runs `/test`,
  forces a full `/sync`, fetches the portfolio summary, places a **$1 notional
  market BUY on AAPL**, then cancels it. Proves the entire stack end-to-end
  against Alpaca paper.

### Auto-rollback
If any smoke check fails, the workflow:
1. Reverts `IMAGE_TAG` in `.env` to the previous value
2. Re-pulls + `up -d` with the old tag
3. Re-runs smoke against the old version
4. Fails the GitHub Actions run loudly so you know to investigate

Last 5 successful tags are kept in `/opt/snowbird/.deploy_history`.

## Part 5 — Day-two operations

| What you want | How |
|---|---|
| View logs | `ssh vm "cd /opt/snowbird && docker compose -f docker-compose.prod.yml logs -f backend"` |
| Manual rollback | `ssh vm "cd /opt/snowbird && sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=sha-OLD/' .env && docker compose -f docker-compose.prod.yml up -d"` |
| Run smoke on demand | `ssh vm "bash /opt/snowbird/scripts/smoke_test.sh"` |
| DB backup | `ssh vm "docker exec $(docker ps -qf name=db) pg_dump -U snowbird snowbird | gzip > ~/backups/snowbird-$(date +%F).sql.gz"` |
| DB restore | `gunzip -c backup.sql.gz | docker exec -i <db_container> psql -U snowbird snowbird` |
| Update TLS cert | Place a Caddy or nginx reverse proxy in front of port 8080 |

## Part 6 — Hardening checklist before exposing to the internet

- [ ] Put Caddy / nginx / Traefik with TLS in front of `:8080`
- [ ] Restrict SSH to your source IP or a wireguard/tailscale network
- [ ] Change demo credentials (create your own user then delete `demo@local`)
- [ ] Back up `.env` somewhere secure (the `SECRET_KEY` encrypts your Alpaca secrets)
- [ ] Point `POSTGRES_PASSWORD` to something strong and back up `pgdata`
- [ ] Enable GitHub branch protection on `main` so tests must pass before merge
- [ ] (Optional) Add Dependabot + weekly security scans on the Dockerfiles
