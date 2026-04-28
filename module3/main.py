"""
module3/main.py
────────────────
CLI for Module 3 — Alternate Supplier Recommender.

Commands:
  --run-once   Find all HIGH+ risk events and generate alternate recommendations
  --status     Show alternate recommendation stats

Usage:
  python -m module3.main --run-once
  python -m module3.main --status
"""

import argparse
import logging
import os
import sys

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


def cmd_run_once():
    from module3.pipeline import run_pipeline
    return run_pipeline()


def cmd_status():
    from module1.db.session import get_session, DB_BACKEND
    from module1.db.models import AlternateSupplier, RiskEvent

    with get_session() as session:
        total_alts = session.query(AlternateSupplier).count()
        total_events_with_alts = session.query(AlternateSupplier.risk_event_id).distinct().count()

        recent = (
            session.query(AlternateSupplier)
            .order_by(AlternateSupplier.created_at.desc())
            .limit(10)
            .all()
        )

        # Events still needing recommendations
        from sqlalchemy import exists
        pending = (
            session.query(RiskEvent)
            .filter(
                RiskEvent.risk_score >= 60,
                RiskEvent.supplier_id.isnot(None),
                ~exists().where(AlternateSupplier.risk_event_id == RiskEvent.id)
            )
            .count()
        )

    print("\n" + "═" * 65)
    print(f"  Module 3 — Alternate Recommender Status ({DB_BACKEND.upper()})")
    print("═" * 65)
    print(f"\n  Recommendations")
    print(f"    Total alternates generated: {total_alts}")
    print(f"    Risk events with alternates: {total_events_with_alts}")
    print(f"    HIGH+ events still pending:  {pending}")
    print(f"\n  Recent Recommendations")
    print("  " + "-" * 60)
    for a in recent:
        ts = a.created_at.strftime("%m-%d %H:%M") if a.created_at else "?"
        print(f"  [{ts}] #{a.rank} {a.alternate_name} ({a.country_code}) score={a.alt_score:.0f}")
    print("\n" + "═" * 65 + "\n")


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(description="Module 3 — Alternate Supplier Recommender")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-once", action="store_true")
    group.add_argument("--status",   action="store_true")
    args = parser.parse_args()

    try:
        if args.run_once: cmd_run_once()
        elif args.status: cmd_status()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.getLogger(__name__).error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
