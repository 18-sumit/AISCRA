"""
run_all.py
───────────
AISCRA Master Orchestrator. Runs all modules in sequence, then repeats.

Order:
  1. Module 1 — Data Ingestion        (fetch + dedup + save articles)
  2. Module 2 — Risk Analysis         (Stage 0 screen + Stages 1–6 score)
  3. Module 3 — Alternate Recommender (rank + rationale for HIGH+ events)
  4. Module 4 — AI Analysis + Email   (generate briefing + send PDF report)

Usage:
  python run_all.py                  # run once and exit
  python run_all.py --schedule       # run now, then every 30 minutes forever
  python run_all.py --interval 60    # run now, then every 60 minutes
  python run_all.py --schedule --skip-m1   # skip ingestion, just analyze + recommend + send report
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

import colorlog
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s:%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        },
    ))
    logging.getLogger().setLevel(getattr(logging, level, logging.INFO))
    logging.getLogger().addHandler(handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)


logger = logging.getLogger("orchestrator")


# ─────────────────────────────────────────────────────────────────────────────
#  Individual module runners
# ─────────────────────────────────────────────────────────────────────────────

def run_module1() -> dict:
    logger.info("─" * 60)
    logger.info("▶  MODULE 1 — Data Ingestion")
    logger.info("─" * 60)
    try:
        from module1.ingestion.pipeline import run_ingestion
        from module1.config.company_profile import load_profile
        profile = load_profile()
        return run_ingestion(profile)
    except Exception as e:
        logger.error(f"Module 1 failed: {e}", exc_info=True)
        return {"error": str(e)}


def run_module2() -> dict:
    logger.info("─" * 60)
    logger.info("▶  MODULE 2 — Risk Analysis")
    logger.info("─" * 60)
    try:
        from module2.pipeline import run_pipeline
        return run_pipeline()
    except Exception as e:
        logger.error(f"Module 2 failed: {e}", exc_info=True)
        return {"error": str(e)}


def run_module3() -> dict:
    logger.info("─" * 60)
    logger.info("▶  MODULE 3 — Alternate Recommender")
    logger.info("─" * 60)
    try:
        from module3.pipeline import run_pipeline
        return run_pipeline()
    except Exception as e:
        logger.error(f"Module 3 failed: {e}", exc_info=True)
        return {"error": str(e)}


def run_module4() -> dict:
    logger.info("─" * 60)
    logger.info("▶  MODULE 4 — AI Analysis & Email Report")
    logger.info("─" * 60)
    try:
        from module4.notifications import send_email_briefing
        from module4.agent import generate_weekly_briefing
        
        logger.info("  Generating briefing…")
        briefing = generate_weekly_briefing()
        
        logger.info("  Sending analysis report via email…")
        email_sent = send_email_briefing(briefing)
        
        if email_sent:
            logger.info("  ✓ Email with PDF report sent")
        else:
            logger.warning("  ✗ Email send failed or not configured")
        
        return {"briefing_sent": email_sent}
    except Exception as e:
        logger.error(f"Module 4 failed: {e}", exc_info=True)
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  Full pipeline run
# ─────────────────────────────────────────────────────────────────────────────

def run_all(skip_m1: bool = False, skip_m2: bool = False, skip_m3: bool = False) -> dict:
    start = time.time()
    ts    = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    logger.info("═" * 60)
    logger.info(f"  AISCRA — Full Pipeline Run")
    logger.info(f"  {ts}")
    logger.info("═" * 60)

    results = {}

    if not skip_m1:
        results["module1"] = run_module1()
    else:
        logger.info("  Module 1 skipped (--skip-m1)")

    if not skip_m2:
        results["module2"] = run_module2()
    else:
        logger.info("  Module 2 skipped (--skip-m2)")

    if not skip_m3:
        results["module3"] = run_module3()
    else:
        logger.info("  Module 3 skipped (--skip-m3)")

    # Always run Module 4 (send email report)
    results["module4"] = run_module4()

    elapsed = time.time() - start

    logger.info("═" * 60)
    logger.info(f"  All modules complete in {elapsed:.1f}s")

    # Summary line
    m1 = results.get("module1", {})
    m2 = results.get("module2", {})
    m3 = results.get("module3", {})
    m4 = results.get("module4", {})

    parts = []
    if m1 and "error" not in m1:
        saved = m1.get("track_a", {}).get("saved", 0) + m1.get("track_b", {}).get("saved", 0)
        parts.append(f"M1: {saved} new articles")
    if m2 and "error" not in m2:
        parts.append(f"M2: {m2.get('risk_events_created', 0)} risk events")
    if m3 and "error" not in m3:
        parts.append(f"M3: {m3.get('alternates_created', 0)} alternates")
    if m4 and "error" not in m4:
        parts.append(f"M4: {'Report sent' if m4.get('briefing_sent') else 'Report skipped'}")

    if parts:
        logger.info("  " + " · ".join(parts))

    errors = [k for k, v in results.items() if isinstance(v, dict) and "error" in v]
    if errors:
        logger.warning(f"  Errors in: {', '.join(errors)}")

    logger.info("═" * 60)
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Scheduler
# ─────────────────────────────────────────────────────────────────────────────

def schedule(interval_minutes: int, skip_m1: bool, skip_m2: bool, skip_m3: bool):
    interval_secs = interval_minutes * 60

    def _shutdown(sig, frame):
        logger.info("Shutdown signal received — stopping")
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(f"Scheduler started — every {interval_minutes} minutes. Ctrl+C to stop.")
    logger.info(f"  Module 1 (ingestion):    {'SKIP' if skip_m1 else 'RUN'}")
    logger.info(f"  Module 2 (risk analysis):{'SKIP' if skip_m2 else 'RUN'}")
    logger.info(f"  Module 3 (alternates):   {'SKIP' if skip_m3 else 'RUN'}")

    run_number = 0
    while True:
        run_number += 1
        logger.info(f"\n  ── Run #{run_number} ──")
        run_all(skip_m1=skip_m1, skip_m2=skip_m2, skip_m3=skip_m3)

        next_run = datetime.now(tz=timezone.utc)
        logger.info(
            f"  Next run in {interval_minutes} minutes "
            f"(at {next_run.strftime('%H:%M UTC')} + {interval_minutes}m)"
        )
        time.sleep(interval_secs)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="AISCRA — AI Supply Chain Risk Analysis Master Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all.py                        # run all modules once, send report
  python run_all.py --schedule             # run now, repeat every 30 minutes
  python run_all.py --schedule --interval 60   # repeat every 60 minutes
  python run_all.py --skip-m1              # skip ingestion (use existing articles)
  python run_all.py --schedule --skip-m1  # analyze + recommend + send on schedule
        """,
    )

    parser.add_argument(
        "--schedule", action="store_true",
        help="Run on a repeating schedule instead of once",
    )
    parser.add_argument(
        "--interval", type=int, default=None,
        help="Schedule interval in minutes (default: FETCH_INTERVAL_MINUTES from .env or 30)",
    )
    parser.add_argument("--skip-m1", action="store_true", help="Skip Module 1 (ingestion)")
    parser.add_argument("--skip-m2", action="store_true", help="Skip Module 2 (risk analysis)")
    parser.add_argument("--skip-m3", action="store_true", help="Skip Module 3 (alternates)")

    args = parser.parse_args()

    interval = args.interval or int(os.getenv("FETCH_INTERVAL_MINUTES", "30"))

    try:
        if args.schedule:
            schedule(
                interval_minutes=interval,
                skip_m1=args.skip_m1,
                skip_m2=args.skip_m2,
                skip_m3=args.skip_m3,
            )
        else:
            run_all(
                skip_m1=args.skip_m1,
                skip_m2=args.skip_m2,
                skip_m3=args.skip_m3,
            )
    except KeyboardInterrupt:
        logger.info("Interrupted — exiting")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
