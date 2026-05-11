"""APScheduler background jobs for periodic Alpaca sync."""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

ET = ZoneInfo("America/New_York")


def _is_market_hours() -> bool:
    now_et = datetime.now(ET)
    weekday = now_et.weekday()  # 0=Mon, 6=Sun
    if weekday >= 5:
        return False
    hour = now_et.hour
    minute = now_et.minute
    # Market hours: 9:30 AM - 4:00 PM ET
    market_open = hour * 60 + minute >= 9 * 60 + 30
    market_close = hour * 60 + minute <= 16 * 60
    return market_open and market_close


def fast_sync_job() -> None:
    """Every 60s during market hours: positions + open orders."""
    if not _is_market_hours():
        return
    _run_sync(full=False)


def activity_sync_job() -> None:
    """Every 5 minutes: pull recent activities (dynamic lookback)."""
    _run_sync(full=False, activities_only=True)


def eod_snapshot_job() -> None:
    """End-of-day: snapshot equity."""
    _run_sync(full=True)


def instrument_refresh_job() -> None:
    """Nightly: refresh instrument metadata."""
    from app.db import SessionLocal
    from app.models.account import AlpacaAccount
    from app.services.sync import refresh_instruments

    db = SessionLocal()
    try:
        accounts = db.execute(select(AlpacaAccount).where(AlpacaAccount.active == True)).scalars().all()
        for acct in accounts:
            try:
                refresh_instruments(db, acct)
            except Exception as exc:
                logger.error("Instrument refresh error for account %s: %s", acct.id, exc)
    finally:
        db.close()


def _run_sync(full: bool = True, activities_only: bool = False) -> None:
    from app.db import SessionLocal
    from app.models.account import AlpacaAccount
    from app.services.sync import sync_account, _sync_activities, _sync_positions, _sync_orders
    from app.services.alpaca import get_trading_client

    db = SessionLocal()
    try:
        accounts = db.execute(select(AlpacaAccount).where(AlpacaAccount.active == True)).scalars().all()
        for acct in accounts:
            try:
                if activities_only:
                    client = get_trading_client(acct)
                    _sync_activities(db, client, acct)
                    db.commit()
                elif full:
                    sync_account(db, acct)
                else:
                    client = get_trading_client(acct)
                    _sync_positions(db, client, acct)
                    _sync_orders(db, client, acct)
                    db.commit()
            except Exception as exc:
                logger.error("Scheduler sync error for account %s: %s", acct.id, exc)
                db.rollback()
    finally:
        db.close()


# TODO: Add auto-reinvest job that checks DividendReinvestSettings.auto_reinvest_enabled
# for each account and triggers reinvestment when unreinvested dividend cash exceeds
# auto_reinvest_threshold. Wire into activity_sync_job or add a dedicated interval job.


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone=ET)

    # Fast sync every 60 seconds (filtered to market hours inside job)
    _scheduler.add_job(fast_sync_job, IntervalTrigger(seconds=60), id="fast_sync", replace_existing=True)

    # Activity sync every 5 minutes
    _scheduler.add_job(activity_sync_job, IntervalTrigger(minutes=5), id="activity_sync", replace_existing=True)

    # End-of-day snapshot at 4:15 PM ET weekdays
    _scheduler.add_job(
        eod_snapshot_job,
        CronTrigger(hour=16, minute=15, day_of_week="mon-fri", timezone=ET),
        id="eod_snapshot",
        replace_existing=True,
    )

    # Nightly instrument refresh at 2 AM ET
    _scheduler.add_job(
        instrument_refresh_job,
        CronTrigger(hour=2, minute=0, timezone=ET),
        id="instrument_refresh",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("APScheduler started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
