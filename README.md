# Snowbird

Self-hosted portfolio analytics and paper-trading dashboard built on [Alpaca Markets](https://alpaca.markets). Track positions, dividends, allocation, benchmarks, and income goals — all on your own server.

> **Disclaimer:** This software is for **educational and personal use only**. Live trading involves real money and real risk. The authors are not responsible for any financial losses. Always paper-trade first. This is not financial advice.

---

## Features

### Portfolio tracking
- Real-time positions, open orders, and account equity via Alpaca sync
- Today P/L and Total P/L stat tiles (computed from `equity - last_equity`)
- Daily equity snapshots for time-weighted return (TWR) calculation
- Historical portfolio backfill (up to 1 year of daily snapshots on first sync)

### Benchmarking
- SPY overlay on the portfolio performance chart with period filter (1D, 1W, 1M, 3M, YTD, 1Y)
- IEX data feed for paper accounts (free tier — no SIP subscription required)
- Normalized rebasing (portfolio and benchmark both start at 100 within the selected window)

### Dividend analytics
- Future payments chart (confirmed vs. estimated, 12-month forward projection)
- Received dividends by month (trailing 12 months)
- Year-over-year dividend growth (grouped bars, current year + N-1 prior years)
- Dividend calendar with pay dates and projected income

### Dashboard KPI tiles
- IRR (Internal Rate of Return) — XIRR via `pyxirr`, supports 1Y / ALL / 3M / 1M periods
- Passive income — forward 12-month dividend projection, current yield %, YoY growth
- Top gainers / losers — ranked by absolute dollar change with live quotes

### Allocation breakdown
- Group by: Sector, Asset Class, ETF Category, or Bucket
- Curated ETF classification map for known symbols (deterministic, no API calls)
- yfinance fallback for unknown symbols with throttle + exponential backoff
- Finnhub fallback for non-ETF stock profiles (free tier)
- Dropdown selection persisted in `localStorage`

### Planning
- Upcoming events calendar — ex-dividend dates, dividend payments, and earnings calls (Finnhub)
- Income goal — set an annual passive-income target with assumed growth rate and monthly contributions
- Equity projection chart (30-year forward) with progress ring and ETA

### Dividend reinvestment
- One-click reinvestment of accumulated dividend cash
- Configurable tax withholding rate (default 24%) — tax portion buys a tax-reserve ETF (default CSHI)
- Remainder distributed across existing bucket targets using the drift-aware rebalance engine
- Dedicated "Tax Reserve" bucket auto-created per account (excluded from regular drift math)
- Full audit trail of every reinvestment run (preview, executed, or failed) with order details
- Settings panel: adjust tax rate, tax-reserve symbol, and auto-reinvest toggle (auto-trigger deferred to a future release)

### Background jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| Fast sync | Every 60s (market hours only) | Account balance, positions, open orders |
| Activity sync | Every 5 min | Recent activities with dynamic lookback (7–90 day window based on gap) |
| EOD snapshot | 4:15 PM ET weekdays | Portfolio equity snapshot for TWR calculation |
| Instrument refresh | 2:00 AM ET nightly | Update symbol metadata (sector, asset class, ETF category) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (port 8080)                       │
│               React 18 + Vite + Tailwind SPA                │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────┐
│                 nginx (frontend container)                    │
│     /       → serves built SPA (static files)               │
│     /api/*  → proxy → backend:8000                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────┐
│               FastAPI backend (port 8000)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐   │
│  │  Auth    │  │   API    │  │   APScheduler            │   │
│  │  (JWT)   │  │  Routers │  │   Background Sync        │   │
│  └──────────┘  └──────────┘  └──────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐    │
│  │          SQLAlchemy 2.0 + Alembic                    │    │
│  └──────────────┬───────────────────────────────────────┘    │
└─────────────────┼────────────────────────────────────────────┘
                  │
     ┌────────────┴──────────────┐
     │                           │
┌────▼────────────┐   ┌─────────▼───────┐
│  PostgreSQL 16  │   │    Redis 7      │
│  (pgdata vol)   │   │  (cache/queue)  │
└─────────────────┘   └─────────────────┘

External data sources:
  • Alpaca Markets API (positions, orders, activities, portfolio history)
  • Finnhub (earnings calendar, stock profiles — free tier)
  • yfinance (ETF classification fallback — no API key)
```

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLAlchemy 2.0, Alembic migrations, APScheduler, alpaca-py 0.26.0, pyxirr, httpx |
| Data sources | Alpaca Markets (IEX feed for paper accounts), Finnhub (free tier), yfinance 0.2.50 + curl_cffi |
| Frontend | React 18, Vite, Tailwind CSS, Recharts, TanStack React Query, Zustand, Lucide icons |
| Typography | SF Pro system font stack (Apple devices), Segoe UI / Roboto fallbacks, JetBrains Mono (monospace) |
| Database | PostgreSQL 16, Redis 7 |
| Infrastructure | Docker Compose, GHCR images, GitHub Actions (CI + self-hosted runner deploy) |
| Language | Python 3.11, TypeScript 5.4 |

---

## Local development

### Prerequisites

- Docker + Docker Compose v2
- An Alpaca Markets account (free paper trading at [alpaca.markets](https://alpaca.markets))

### 1. Clone and configure

```bash
git clone https://github.com/droolingtaz/snowbird.git
cd snowbird
cp backend/.env.example .env
```

Edit `.env` and generate a real Fernet key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output as `SECRET_KEY` in `.env`.

### 2. Start

```bash
docker compose up -d
```

The backend automatically runs Alembic migrations and seeds a demo user on first start.

### 3. Open

Navigate to **http://localhost:8080**

Login with the demo account:
- **Email:** `demo@local`
- **Password:** `demo12345`

### 4. Connect Alpaca

1. Go to **Settings** > **Alpaca Accounts** > **Add Account**
2. Select **Paper** mode
3. Enter your API Key ID and Secret Key from the [Alpaca Dashboard](https://app.alpaca.markets/brokerage/paper-trading)
4. Click **Test Connection** to verify, then **Save**
5. Use the **account switcher** in the top bar to select your active account

### Running without Docker

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example ../.env  # edit for local postgres/redis
alembic upgrade head
python seed.py
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev  # http://localhost:5173
```

---

## Environment variables

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Fernet key for encrypting Alpaca secrets + signing JWTs | **required** |
| `POSTGRES_USER` | Postgres username | `snowbird` |
| `POSTGRES_PASSWORD` | Postgres password | `snowbird_secret` |
| `POSTGRES_DB` | Postgres database name | `snowbird` |
| `POSTGRES_HOST` | Postgres host | `db` |
| `POSTGRES_PORT` | Postgres port | `5432` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `FINNHUB_API_KEY` | Finnhub API key for earnings calendar + stock profiles. Events widget falls back to dividends-only if unset. | _none_ |
| `YFINANCE_PER_CALL_SLEEP_SECONDS` | Sleep between yfinance API calls | `7` |
| `YFINANCE_MAX_RETRIES` | Max retry attempts on yfinance 429s | `5` |
| `YFINANCE_BACKOFF_BASE_SECONDS` | Base delay for exponential backoff | `30` |
| `YFINANCE_BACKOFF_MULTIPLIER` | Backoff multiplier | `2` |
| `YFINANCE_BACKOFF_MAX_SECONDS` | Max backoff delay | `600` |
| `YFINANCE_JITTER_MAX_SECONDS` | Max random jitter added to backoff | `5` |
| `RISK_FREE_RATE` | Annual risk-free rate for Sharpe calculations | `0.045` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiry | `10080` (7 days) |

---

## Data classification pipeline

Instrument metadata (sector, asset class, ETF category) is populated by the nightly instrument refresh job and follows a tiered lookup strategy:

1. **Curated ETF map** — `backend/app/data/etf_classifications.json` contains deterministic metadata for known ETF symbols. Loaded once via `@lru_cache`. Symbols found here get `is_etf`, `asset_class`, `etf_category`, `sector`, and `name` written directly — no external API calls.

2. **yfinance fallback** — Unknown symbols are classified via `yf.Ticker(symbol).info` with Redis caching (24h TTL). Calls are throttled at 7s per call (configurable) with exponential backoff on 429s (30s base, 2x multiplier, 600s max, up to 5 retries with 0–5s random jitter).

3. **Finnhub fallback** — For non-ETF stocks, `GET /api/v1/stock/profile2` provides sector and industry data. Used only when yfinance doesn't populate the field.

Manual backfill:

```bash
docker compose exec backend python -m app.tasks.refresh_instruments
```

---

## Deployment

Snowbird is deployed via GitHub Actions to a self-hosted runner on an Ubuntu 24.04 VM.

### CI pipeline (`ci.yml`)

Three jobs run on every push/PR to `main`:
1. **Backend tests** — `pytest` against a Postgres 16 service container
2. **Frontend typecheck & build** — `tsc --noEmit` + `vite build`
3. **Build & push images** — builds Docker images and pushes to GHCR (main branch only, after tests pass)

### Deploy pipeline (`deploy.yml`)

Triggered after images are built and pushed:
1. Checks out repo on the self-hosted runner
2. Syncs scripts, compose file, and systemd units to `/opt/snowbird`
3. Pulls new GHCR images (`sha-<commit>` tags)
4. Runs `docker compose -f docker-compose.prod.yml up -d`
5. Runs post-deploy smoke test (adds paper account, tests connection, syncs, checks portfolio summary)
6. On smoke failure: **auto-rollback** to the previous image tag, then re-runs smoke to verify rollback

### Additional automation

- **Nightly Postgres backups** — systemd timer at 03:30, 14-day retention, gzip-compressed dumps in `/var/backups/snowbird/`
- **Weekly GHCR image pruning** — GitHub Actions workflow (Sundays 02:00 UTC), keeps 10 most recent tags per image, prunes images older than 2 weeks

For full deployment setup (VM provisioning, runner setup, systemd units, sudoers), see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

---

## Security notes

- **API secrets are encrypted at rest** using [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/) with your `SECRET_KEY`. Plaintext secrets are never stored in the database.
- **JWT tokens** are signed with the same `SECRET_KEY`. Keep this value secret — changing it invalidates all sessions and encrypted API secrets.
- **Self-host only.** No rate-limiting, CORS restrictions, or email verification by design. Do **not** expose directly to the internet.
- For remote access, use a **reverse proxy with TLS** (e.g., Caddy or nginx) and add authentication at the proxy layer.
- Postgres data is stored in a named Docker volume (`pgdata`). Back it up regularly.

---

## Recent changelog (PRs #15–#30)

| PR | Title |
|----|-------|
| [#15](https://github.com/droolingtaz/snowbird/pull/15) | Future payments, dividends received, and YoY growth charts |
| [#16](https://github.com/droolingtaz/snowbird/pull/16) | IRR, passive income, and daily movers dashboard tiles |
| [#17](https://github.com/droolingtaz/snowbird/pull/17) | Upcoming events calendar and income goal with ETA projection |
| [#18](https://github.com/droolingtaz/snowbird/pull/18) | Bundle pyxirr in Docker image + return 200 for empty goal state |
| [#19](https://github.com/droolingtaz/snowbird/pull/19) | Wire SPY benchmark to Alpaca account + IEX data feed for paper |
| [#20](https://github.com/droolingtaz/snowbird/pull/20) | Fix BarSet `.data` dict access (alpaca-py 0.26.0 compat) |
| [#21](https://github.com/droolingtaz/snowbird/pull/21) | Honor period param in benchmark endpoint (filter date window) |
| [#22](https://github.com/droolingtaz/snowbird/pull/22) | Wire `useBenchmark` hook into Dashboard for SPY overlay |
| [#23](https://github.com/droolingtaz/snowbird/pull/23) | Persist allocation dropdown in localStorage + Finnhub sector backfill |
| [#24](https://github.com/droolingtaz/snowbird/pull/24) | Add `is_etf` / `etf_category` / `asset_class` columns + migration 0003 |
| [#25](https://github.com/droolingtaz/snowbird/pull/25) | Replace Finnhub ETF endpoints with yfinance (Finnhub premium-gated) |
| [#26](https://github.com/droolingtaz/snowbird/pull/26) | Install ca-certificates in Docker image for yfinance TLS |
| [#27](https://github.com/droolingtaz/snowbird/pull/27) | Throttle yfinance calls + exponential backoff for 429 rate limits |
| [#28](https://github.com/droolingtaz/snowbird/pull/28) | Fix today_pl/total_pl always returning 0 (AttributeError on `equity_previous_close`) |
| [#29](https://github.com/droolingtaz/snowbird/pull/29) | Curated ETF classification map (bypass yfinance/Finnhub for known symbols) |
| [#30](https://github.com/droolingtaz/snowbird/pull/30) | SF Pro / Apple system font stack app-wide |
