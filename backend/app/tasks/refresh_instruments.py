"""CLI task: backfill instrument sectors via yfinance (primary) + Finnhub fallback.

Usage:
    python -m app.tasks.refresh_instruments
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    from app.db import SessionLocal
    from app.services.sync import backfill_all_sectors

    logger.info("Starting instrument sector backfill...")
    db = SessionLocal()
    try:
        updated = backfill_all_sectors(db)
        logger.info("Done. %d instrument(s) updated.", updated)
    except Exception:
        logger.exception("Sector backfill failed")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
