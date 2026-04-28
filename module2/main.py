"""
module2/main.py
────────────────
CLI for Module 2 — Risk Analysis Engine.

Commands:
  --run-once        Run one full pipeline cycle and exit
  --run-continuous  Run every FETCH_INTERVAL_MINUTES (same schedule as M1)
  --status          Show risk event stats and recent high-risk articles

Usage:
  python -m module2.main --run-once
  python -m module2.main --status
  python -m module2.main --run-continuous
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

import colorlog
from dotenv import load_dotenv

load_dotenv()


def _setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s:%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={"DEBUG": "cyan", "INFO": "green", "WARNING": "yellow",
                    "ERROR": "red", "CRITICAL": "bold_red"},
    ))
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger().addHandler(handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)


def cmd_run_once():
    from module2.pipeline import run_pipeline
    return run_pipeline()


def cmd_status():
    from module1.db.session import get_session, DB_BACKEND
    from module1.db.models import RiskEvent, Article, Supplier

    with get_session() as session:
        total_events = session.query(RiskEvent).count()
        critical = session.query(RiskEvent).filter_by(severity_band="CRITICAL").count()
        high     = session.query(RiskEvent).filter_by(severity_band="HIGH").count()
        medium   = session.query(RiskEvent).filter_by(severity_band="MEDIUM").count()
        low      = session.query(RiskEvent).filter_by(severity_band="LOW").count()

        unprocessed = session.query(Article).filter_by(processed=False).count()
        unscreened  = session.query(Article).filter_by(
            fetch_type="hot_news", gemini_screened=False
        ).count()

        recent = (
            session.query(RiskEvent)
            .order_by(RiskEvent.created_at.desc())
            .limit(10)
            .all()
        )

    print("\n" + "═" * 65)
    print(f"  Module 2 — Risk Analysis Status ({DB_BACKEND.upper()})")
    print("═" * 65)
    print(f"\n  Risk Events")
    print(f"    Total:     {total_events}")
    print(f"    CRITICAL:  {critical}  ← immediate action")
    print(f"    HIGH:      {high}    ← show alternates")
    print(f"    MEDIUM:    {medium}")
    print(f"    LOW:       {low}")
    print(f"\n  Pending")
    print(f"    Unprocessed articles:  {unprocessed}")
    print(f"    Unscreened hot_news:   {unscreened}")
    print(f"\n  Recent Risk Events")
    print("  " + "-" * 60)
    for e in recent:
        ts = e.created_at.strftime("%m-%d %H:%M") if e.created_at else "?"
        print(f"  [{ts}] [{e.severity_band:8}] score={e.risk_score:.1f}  {e.event_type}")
    print("\n" + "═" * 65 + "\n")


def cmd_run_continuous():
    from module2.pipeline import run_pipeline
    interval = int(os.getenv("FETCH_INTERVAL_MINUTES", "30")) * 60
    logger = logging.getLogger(__name__)
    logger.info(f"Module 2: continuous mode, every {interval//60} minutes. Ctrl+C to stop.")

    while True:
        try:
            run_pipeline()
        except KeyboardInterrupt:
            logger.info("Stopped.")
            break
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
        logger.info(f"Next run in {interval//60} minutes…")
        time.sleep(interval)


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(description="Module 2 — Risk Analysis Engine")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-once",       action="store_true")
    group.add_argument("--run-continuous", action="store_true")
    group.add_argument("--status",         action="store_true")

    args = parser.parse_args()

    try:
        if args.run_once:       cmd_run_once()
        elif args.run_continuous: cmd_run_continuous()
        elif args.status:       cmd_status()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.getLogger(__name__).error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
