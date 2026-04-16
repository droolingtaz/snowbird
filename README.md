# Snowbird — Self-Hosted Portfolio Analytics + Trading

A self-hosted web application combining portfolio analytics (like Snowball Analytics) with live and paper trading via Alpaca Markets. All your portfolio data stays on your own server.

> **Disclaimer:** This software is for **educational and personal use only**. Live trading involves real money and real risk. The authors are not responsible for any financial losses. Always paper-trade first. This is not financial advice.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Browser (port 8080)                  │
│              React 18 + Vite + Tailwind SPA              │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP
┌───────────────────────▼─────────────────────────────────┐
│                   nginx (frontend container)             │
│    /          → serves built SPA (static files)         │
│    /api/*     → proxy → backend:8000                    │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP
┌───────────────────────▼─────────────────────────────────┐
│              FastAPI backend (port 8000)                  │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐ │
│  │  Auth    │  │  API     │  │   APScheduler          │ │
│  │  (JWT)   │  │ Routers  │  │   Background Sync      │ │
│  └──────────┘  └──────────┘  └────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │         SQLAlchemy 2.0 + Alembic                     │ │
│  └──────────────────┬───────────────────────────────────┘ │
└────────────────────┬┼────────────────────────────────────┘
                     ││
          ┌──────────┘└──────────┐
          │                      │
┌─────────▼──────┐    ┌──────────▼──────┐
│  PostgreSQL 16  │    │   Redis 7        │
│  (pgdata vol)   │    │   (cache/queue)  │
└─────────────────┘    └──────────────────┘
                              │
                  ┌───────────▼──────────────┐
                  │   Alpaca Markets API      │
                  │   paper-api / live API    │
                  └──────────────────────────┘
```

---

## Deploying to a lab VM with CI/CD

For GitOps deployment (GitHub Actions → SSH → your VM → automated smoke tests → auto-rollback), see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

---

## Quickstart

### Prerequisites
- Docker + Docker Compose (v2)
- An Alpaca Markets account (free paper trading at alpaca.markets)

### 1. Clone and configure

```bash
git clone <your-repo> snowbird
cd snowbird
cp .env.example .env
```

Edit `.env` and set:
```bash
# Generate a real Fernet key:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste the output as SECRET_KEY in .env
```

### 2. Start

```bash
docker compose up -d
```

The backend runs Alembic migrations and seeds a demo user automatically on first start.

### 3. Open

Navigate to **http://localhost:8080**

Login with the demo account:
- **Email:** `demo@local`
- **Password:** `demo12345`

---

## Adding Alpaca Credentials

1. Log in, go to **Settings** → **Alpaca Accounts** → **Add Account**
2. Select **Paper** or **Live** mode
3. Enter your API Key ID and Secret Key from [Alpaca Dashboard](https://app.alpaca.markets/brokerage/paper-trading)
4. Click **Test Connection** to verify, then **Save**
5. Use the **account switcher** in the top bar to select your active account

### Paper vs Live

| Mode  | Color  | URL                                |
|-------|--------|------------------------------------|
| Paper | Blue   | https://paper-api.alpaca.markets  |
| Live  | Green  | https://api.alpaca.markets         |

Start with **Paper** to test strategies without risking real money.

---

## Security Notes

- **API secrets are encrypted at rest** using [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/) with your `SECRET_KEY`. The plaintext secret is never stored in the database.
- **JWT tokens** are signed with the same `SECRET_KEY`. Keep this value secret and back it up — if you change it, all sessions and encrypted API secrets become invalid.
- **Self-host only.** This app has no rate-limiting, CORS restrictions, or email verification by design. Do **not** expose it directly to the internet.
- For remote access, place a **reverse proxy with TLS** (e.g., Caddy or nginx) in front of port 8080, and add authentication at the proxy layer (e.g., basic auth, Cloudflare Access).
- Postgres data is stored in a named Docker volume (`pgdata`). Back it up regularly.

---

## Configuration Reference

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Fernet key + JWT secret | **required** |
| `POSTGRES_USER` | Postgres username | `snowbird` |
| `POSTGRES_PASSWORD` | Postgres password | `snowbird_secret` |
| `POSTGRES_DB` | Postgres database name | `snowbird` |
| `POSTGRES_HOST` | Postgres host | `db` |
| `POSTGRES_PORT` | Postgres port | `5432` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `RISK_FREE_RATE` | Annual risk-free rate for Sharpe | `0.045` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT expiry | `10080` (7 days) |

---

## Background Sync Schedule

The backend runs these jobs automatically for each connected Alpaca account:

| Job | Schedule | Description |
|---|---|---|
| Fast sync | Every 60s (market hours) | Account balance, positions, open orders |
| Activity sync | Every 5 min | Last 7 days of trades, dividends, fees |
| End-of-day snapshot | After 4:15 PM ET | Portfolio equity snapshot for TWR calculation |
| Instrument refresh | 2:00 AM nightly | Update symbol metadata (sector, asset class) |

---

## Development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # edit for local postgres
alembic upgrade head
python seed.py
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev  # http://localhost:5173
```

---

## Implementation Notes

- **No Celery** — uses APScheduler in-process for simplicity. For high-volume use, consider migrating to Celery + Redis.
- **No email verification / 2FA / password reset** — out of scope for v1. Add at the nginx layer or via a separate auth proxy.
- **Fractional shares** — rebalancer respects whole-share mode by flooring quantities; enable fractional by account type.
- **Rate limiting** — if Alpaca rate-limits market data requests, the last known quote is served from Redis cache.
