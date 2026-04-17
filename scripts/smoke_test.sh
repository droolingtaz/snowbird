#!/usr/bin/env bash
# Post-deploy smoke test. Runs on the VM after `docker compose up`.
#
# Checks:
#   1. Backend /api/health responds 200
#   2. Frontend bundle served on :8080
#   3. Login with demo credentials
#   4. (optional) Alpaca paper trading flow: sync, place $1 order, cancel
#
# Exit code 0 on success, non-zero triggers rollback.

set -euo pipefail

BACKEND="${SMOKE_BACKEND_URL:-http://localhost:8080}"
DEMO_EMAIL="${SMOKE_DEMO_EMAIL:-demo@example.com}"
DEMO_PASSWORD="${SMOKE_DEMO_PASSWORD:-demo12345}"
# Optional — set these to enable the full Alpaca paper trading smoke test
ALPACA_KEY="${SMOKE_ALPACA_KEY:-}"
ALPACA_SECRET="${SMOKE_ALPACA_SECRET:-}"

log()   { echo "[smoke] $*"; }
fail()  { echo "[smoke][FAIL] $*" >&2; exit 1; }

# ---- 1. Wait for backend health -----------------------------------------
log "Waiting for backend at $BACKEND ..."
for i in {1..60}; do
    if curl -fsS "$BACKEND/api/health" >/dev/null 2>&1; then
        log "Backend healthy after ${i}s"
        break
    fi
    sleep 1
    [ "$i" = "60" ] && fail "Backend did not respond within 60s"
done

# ---- 2. Frontend bundle -------------------------------------------------
log "Checking frontend bundle ..."
curl -fsS "$BACKEND/" | grep -qi 'snowbird\|<div id="root"' \
    || fail "Frontend root not served"
log "Frontend OK"

# ---- 3. Auth flow -------------------------------------------------------
log "Registering demo user (idempotent) ..."
curl -sS -o /dev/null -X POST "$BACKEND/api/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$DEMO_EMAIL\",\"password\":\"$DEMO_PASSWORD\"}" || true

log "Logging in ..."
TOKEN=$(curl -fsS -X POST "$BACKEND/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$DEMO_EMAIL\",\"password\":\"$DEMO_PASSWORD\"}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
[ -n "$TOKEN" ] || fail "Login did not return a token"

log "Verifying /api/auth/me ..."
ME=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BACKEND/api/auth/me")
echo "$ME" | grep -q "$DEMO_EMAIL" || fail "/me did not return demo email"

log "Listing accounts ..."
curl -fsS -H "Authorization: Bearer $TOKEN" "$BACKEND/api/accounts" >/dev/null \
    || fail "GET /accounts failed"

# ---- 4. Alpaca paper trading smoke test (optional) ----------------------
if [ -n "$ALPACA_KEY" ] && [ -n "$ALPACA_SECRET" ]; then
    log "Running Alpaca paper trading smoke test ..."

    AUTH="Authorization: Bearer $TOKEN"
    JSON="Content-Type: application/json"

    # Add a paper account (idempotent: if already present, we reuse)
    log "  -> Adding paper Alpaca account ..."
    ACCT_RESP=$(curl -sS -X POST "$BACKEND/api/accounts" \
        -H "$AUTH" -H "$JSON" \
        -d "{\"label\":\"smoke-paper\",\"mode\":\"paper\",\"api_key\":\"$ALPACA_KEY\",\"api_secret\":\"$ALPACA_SECRET\"}" || true)
    ACCT_ID=$(curl -fsS -H "$AUTH" "$BACKEND/api/accounts" \
        | python3 -c 'import sys,json; xs=json.load(sys.stdin); print([a["id"] for a in xs if a["label"]=="smoke-paper"][0])')
    [ -n "$ACCT_ID" ] || fail "Could not create/find smoke-paper account"
    log "  -> Account id: $ACCT_ID"

    log "  -> Testing Alpaca connection ..."
    curl -fsS -X POST -H "$AUTH" "$BACKEND/api/accounts/$ACCT_ID/test" >/dev/null \
        || fail "Alpaca connection test failed"

    log "  -> Syncing ..."
    curl -fsS -X POST -H "$AUTH" "$BACKEND/api/accounts/$ACCT_ID/sync" >/dev/null \
        || fail "Account sync failed"

    log "  -> Fetching portfolio summary ..."
    SUMMARY=$(curl -fsS -H "$AUTH" "$BACKEND/api/portfolio/summary?account_id=$ACCT_ID")
    echo "$SUMMARY" | python3 -m json.tool >/dev/null || fail "Summary not valid JSON"

    log "  -> Placing $1 notional paper BUY on AAPL ..."
    ORDER=$(curl -sS -X POST "$BACKEND/api/orders" \
        -H "$AUTH" -H "$JSON" \
        -d "{\"account_id\":$ACCT_ID,\"symbol\":\"AAPL\",\"side\":\"buy\",\"type\":\"market\",\"notional\":1,\"time_in_force\":\"day\"}")
    ORDER_ID=$(echo "$ORDER" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("id",""))' 2>/dev/null || echo "")

    if [ -n "$ORDER_ID" ]; then
        log "  -> Order $ORDER_ID placed. Cancelling ..."
        curl -sS -X DELETE -H "$AUTH" "$BACKEND/api/orders/$ORDER_ID?account_id=$ACCT_ID" >/dev/null || true
    else
        # Market may be closed or fractional not enabled — acceptable; log the response
        log "  -> Order placement returned: $ORDER  (non-fatal if market closed)"
    fi
    log "Alpaca paper smoke test completed"
else
    log "Skipping Alpaca paper smoke test (SMOKE_ALPACA_KEY / SECRET not set)"
fi

log "All smoke checks passed"
