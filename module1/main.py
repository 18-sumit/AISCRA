"""
module1/main.py
────────────────
CLI entry point for Module 1.

Commands:
  --init-db    Create all DB tables, seed reference data, load company profile
  --once       Run one ingestion cycle across all Track A and Track B sources
  --status     Show DB statistics and 10 most recent articles
  --schedule   Start the 30-minute scheduler (runs indefinitely)

Usage:
  python -m module1.main --init-db
  python -m module1.main --once
  python -m module1.main --status
  python -m module1.main --schedule
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import colorlog
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
#  Logging setup
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "./logs/ingestion.log")

    # Ensure log directory exists
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Coloured console handler
    console_handler = colorlog.StreamHandler()
    console_handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s:%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        }
    ))

    # File handler (no colour)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("feedparser").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_init_db():
    """Create all DB tables and seed reference data from company_profile.yaml."""
    from module1.db.models import Base
    from module1.db.session import engine, DB_BACKEND
    from module1.db.seed import run_all_seeds
    from module1.config.company_profile import load_profile
    from module1.db.session import get_session

    logger.info(f"Initializing database (backend: {DB_BACKEND})")

    # Create all tables
    Base.metadata.create_all(engine)
    logger.info("✅ All 8 DB tables created (or already exist)")

    # Seed reference data
    profile = load_profile()
    logger.info(f"Company profile loaded: {profile.company.name}")

    with get_session() as session:
        run_all_seeds(session, profile.to_dict())

    logger.info(f"✅ Database initialized successfully")
    logger.info(f"   Company: {profile.company.name}")
    logger.info(f"   Suppliers: {len(profile.suppliers)}")
    logger.info(f"   Keywords: {len(profile.get_all_keywords())}")
    logger.info(f"   RSS feeds: Track A={len(profile.rss_feeds.track_a)}, Track B={len(profile.rss_feeds.track_b)}")

    # Show connection info
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    if db_type == "sqlite":
        sqlite_path = os.getenv("SQLITE_PATH", "./data/supply_chain.db")
        logger.info(f"   SQLite DB: {Path(sqlite_path).resolve()}")
    else:
        logger.info(f"   PostgreSQL: {os.getenv('POSTGRES_URL', '(not set)')}")


def cmd_once():
    """Run one complete ingestion cycle and exit."""
    from module1.config.company_profile import load_profile
    from module1.ingestion.pipeline import run_ingestion

    profile = load_profile()
    logger.info(f"Running one-shot ingestion for: {profile.company.name}")
    results = run_ingestion(profile)
    logger.info("One-shot ingestion complete ✓")
    return results


def cmd_status():
    """Show database statistics and recent articles."""
    from module1.db.models import Article, FetchLog, Supplier, KeywordRegistry
    from module1.db.session import get_session, DB_BACKEND, check_connection

    if not check_connection():
        logger.error("Cannot connect to database. Run --init-db first.")
        sys.exit(1)

    with get_session() as session:
        n_articles = session.query(Article).count()
        n_targeted = session.query(Article).filter_by(fetch_type="targeted").count()
        n_hot_news = session.query(Article).filter_by(fetch_type="hot_news").count()
        n_processed = session.query(Article).filter_by(processed=True).count()
        n_unprocessed = session.query(Article).filter_by(processed=False).count()
        n_screened = session.query(Article).filter_by(
            fetch_type="hot_news", gemini_screened=True
        ).count()
        n_risks = session.query(Article).filter_by(is_supply_chain_risk=True).count()
        n_suppliers = session.query(Supplier).filter_by(active=True).count()
        n_keywords = session.query(KeywordRegistry).filter_by(active=True).count()

        recent = (
            session.query(Article)
            .order_by(Article.fetched_at.desc())
            .limit(10)
            .all()
        )

        recent_logs = (
            session.query(FetchLog)
            .order_by(FetchLog.run_at.desc())
            .limit(5)
            .all()
        )

    print("\n" + "═" * 65)
    print(f"  Supply Chain Risk — Module 1 Status ({DB_BACKEND.upper()})")
    print("═" * 65)
    print(f"\n  Articles")
    print(f"    Total:        {n_articles:,}")
    print(f"    Track A:      {n_targeted:,}")
    print(f"    Track B:      {n_hot_news:,}")
    print(f"    Processed:    {n_processed:,}")
    print(f"    Unprocessed:  {n_unprocessed:,}")
    print(f"    Gemini-screened (Track B): {n_screened:,}")
    print(f"    Confirmed risks:           {n_risks:,}")
    print(f"\n  Config")
    print(f"    Active suppliers:    {n_suppliers}")
    print(f"    Active keywords:     {n_keywords}")
    print(f"\n  Recent Articles (last 10)")
    print("  " + "-" * 60)
    for a in recent:
        ts = a.fetched_at.strftime("%m-%d %H:%M") if a.fetched_at else "?"
        track = "A" if a.fetch_type == "targeted" else "B"
        print(f"  [{ts}] [{track}] {a.headline[:55]}")

    if recent_logs:
        print(f"\n  Recent Fetch Runs (last 5)")
        print("  " + "-" * 60)
        for log in recent_logs:
            ts = log.run_at.strftime("%m-%d %H:%M") if log.run_at else "?"
            print(f"  [{ts}] {log.source}: {log.articles_fetched} fetched, "
                  f"{log.articles_new} new [{log.status}] ({log.duration_seconds:.1f}s)")

    print("\n" + "═" * 65 + "\n")


def cmd_schedule():
    """Start the 30-minute scheduler."""
    from module1.config.company_profile import load_profile
    from module1.scheduler import start_scheduler

    profile = load_profile()
    logger.info(f"Starting scheduler for: {profile.company.name}")
    start_scheduler(profile)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI parser
# ─────────────────────────────────────────────────────────────────────────────

def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="Module 1 — Supply Chain Risk Data Ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  --init-db    Create all DB tables and seed reference data
  --once       Run one ingestion cycle and exit
  --status     Show DB statistics and recent articles
  --schedule   Start the 30-minute ingestion scheduler (runs indefinitely)

Examples:
  python -m module1.main --init-db
  python -m module1.main --once
  python -m module1.main --status
  python -m module1.main --schedule
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init-db", action="store_true",
                       help="Initialize database: create tables and seed data")
    group.add_argument("--once", action="store_true",
                       help="Run one ingestion cycle and exit")
    group.add_argument("--status", action="store_true",
                       help="Show database statistics")
    group.add_argument("--schedule", action="store_true",
                       help="Start the scheduled 30-minute ingestion loop")

    args = parser.parse_args()

    try:
        if args.init_db:
            cmd_init_db()
        elif args.once:
            cmd_once()
        elif args.status:
            cmd_status()
        elif args.schedule:
            cmd_schedule()
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.error("Hint: make sure company_profile.yaml exists in the project root")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted — exiting")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
