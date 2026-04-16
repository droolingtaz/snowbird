from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.accounts import router as accounts_router
from app.api.portfolio import router as portfolio_router
from app.api.holdings import router as holdings_router
from app.api.orders import router as orders_router
from app.api.dividends import router as dividends_router
from app.api.analytics import router as analytics_router
from app.api.buckets import router as buckets_router
from app.api.market import router as market_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.workers.scheduler import start_scheduler
    start_scheduler()
    yield
    # Shutdown
    from app.workers.scheduler import stop_scheduler
    stop_scheduler()


app = FastAPI(
    title="Snowbird API",
    version="1.0.0",
    description="Self-hosted portfolio analytics + Alpaca trading",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(accounts_router, prefix="/api")
app.include_router(portfolio_router, prefix="/api")
app.include_router(holdings_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(dividends_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(buckets_router, prefix="/api")
app.include_router(market_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
