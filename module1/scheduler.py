"""
module1/scheduler.py
─────────────────────
APScheduler-based ingestion scheduler.
Runs run_ingestion() every FETCH_INTERVAL_MINUTES minutes (default: 30).

No Kafka, no Redis, no external broker needed.
Uses BlockingScheduler for simplicity — runs in the main thread.

Usage:
    from module1.scheduler import start_scheduler
    start_scheduler(profile)    # blocks forever
"""

import logging
import os
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from module1.config.company_profile import CompanyProfile
from module1.ingestion.pipeline import run_ingestion

load_dotenv()
logger = logging.getLogger(__name__)

FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL_MINUTES", "30"))


def _run_job(profile: CompanyProfile):
    """Wrapped job function with top-level error handling."""
    try:
        run_ingestion(profile)
    except Exception as e:
        logger.error(f"Scheduler: ingestion job failed: {e}", exc_info=True)
        # Job failure does NOT crash the scheduler — it logs and continues


def start_scheduler(profile: CompanyProfile):
    """
    Start the blocking APScheduler.
    Runs an immediate first cycle, then every FETCH_INTERVAL_MINUTES.

    Handles SIGINT / SIGTERM for clean shutdown.
    """
    scheduler = BlockingScheduler(
        job_defaults={
            "coalesce": True,           # if a run is missed, run once (not catch-up)
            "max_instances": 1,         # never run two ingestion cycles simultaneously
            "misfire_grace_time": 120,  # allow up to 2 minutes of delay before skip
        },
        timezone="UTC",
    )

    scheduler.add_job(
        _run_job,
        trigger=IntervalTrigger(minutes=FETCH_INTERVAL),
        args=[profile],
        id="ingestion_job",
        name=f"Module 1 Ingestion ({profile.company.short_name})",
        next_run_time=datetime.now(tz=timezone.utc),  # run immediately on start
    )

    def _shutdown(signum, frame):
        logger.info("Received shutdown signal — stopping scheduler gracefully")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(f"Scheduler started: every {FETCH_INTERVAL} minutes")
    logger.info(f"Company: {profile.company.name}")
    logger.info(f"Next run: immediately, then every {FETCH_INTERVAL} minutes")
    logger.info("Press Ctrl+C to stop")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
