"""
module3/pipeline.py
────────────────────
Module 3 orchestrator.

Finds all HIGH+ risk events that don't yet have alternate recommendations,
runs the ranking formula, generates rationale, and writes to alternate_suppliers table.

Triggered by:
  - Module 2 completing a run (called from module2/pipeline.py)
  - CLI: python -m module3.main --run-once
"""

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

HIGH_THRESHOLD = 60.0  # minimum risk_score to trigger alternate recommendations


def _get_unresolved_risk_events(session) -> list:
    """
    Find HIGH+ risk events that have no alternate recommendations yet.
    """
    from module1.db.models import RiskEvent, AlternateSupplier
    from sqlalchemy import and_, not_, exists

    events = (
        session.query(RiskEvent)
        .filter(
            RiskEvent.risk_score >= HIGH_THRESHOLD,
            RiskEvent.supplier_id.isnot(None),
            ~exists().where(AlternateSupplier.risk_event_id == RiskEvent.id)
        )
        .order_by(RiskEvent.risk_score.desc())
        .all()
    )
    return events


def process_risk_event(risk_event, session, profile) -> list:
    """
    Generate alternate supplier recommendations for one risk event.
    Returns list of AlternateSupplier ORM objects created.
    """
    from module1.db.models import Supplier, AlternateSupplier
    from module3.data_sources import get_all_candidates
    from module3.ranker import rank_candidates, _get_country_risk
    from module3.rationale import generate_all_rationales

    # Load the disrupted supplier
    disrupted = session.query(Supplier).filter_by(id=risk_event.supplier_id).first()
    if not disrupted:
        logger.warning(f"  Supplier id={risk_event.supplier_id} not found — skipping")
        return []

    commodity = risk_event.commodity or disrupted.commodity or ""
    logger.info(
        f"  Processing: {disrupted.name} ({commodity}) "
        f"score={risk_event.risk_score:.1f} [{risk_event.severity_band}]"
    )

    # Get country risk for the disrupted supplier
    dis_risk_score, dis_risk_cat = _get_country_risk(disrupted.country_code or "XX", session)

    # Find candidates
    candidates = get_all_candidates(
        disrupted_supplier_id=disrupted.id,
        disrupted_commodity=commodity,
        profile=profile,
        session=session,
    )

    if not candidates:
        logger.info(f"  No alternate candidates found for '{commodity}'")
        return []

    # Rank candidates
    top_scored = rank_candidates(
        candidates=candidates,
        disrupted_supplier=disrupted,
        disrupted_risk_score=dis_risk_score,
        disrupted_risk_category=dis_risk_cat,
        session=session,
        top_n=5,
    )

    if not top_scored:
        logger.info("  Ranking produced no results")
        return []

    # Generate rationale for top 3
    top_3 = top_scored[:3]
    rationales = generate_all_rationales(
        top_scored=top_3,
        disrupted_supplier_name=disrupted.name,
        commodity=commodity,
        impact_chain=risk_event.impact_chain,
        is_indirect=bool(risk_event.is_indirect),
        delay=1.5,
    )

    # Write to DB
    created = []
    for rank, (entry, rationale) in enumerate(zip(top_3, rationales), 1):
        c = entry["candidate"]
        alt = AlternateSupplier(
            risk_event_id=risk_event.id,
            disrupted_supplier_id=disrupted.id,
            alternate_name=c.name,
            country=c.country,
            country_code=c.country_code,
            capacity_fit=c.capacity_fit,
            lead_time_weeks=c.lead_time_weeks,
            alt_score=entry["alt_score"],
            track_record_score=entry["track_rec_score"],
            geographic_safety_score=entry["geo_safety_score"],
            rationale=rationale,
            rank=rank,
            created_at=datetime.now(tz=timezone.utc),
        )
        session.add(alt)
        created.append(alt)
        logger.info(
            f"    #{rank} {c.name} ({c.country_code}) "
            f"score={entry['alt_score']:.0f}"
        )

    return created


def run_pipeline() -> dict:
    """
    Full Module 3 pipeline run.
    Finds all unresolved HIGH+ risk events and generates alternate recommendations.
    """
    from module1.db.session import get_session
    from module1.config.company_profile import load_profile

    start = time.time()
    profile = load_profile()

    logger.info("=" * 60)
    logger.info(f"Module 3 Alternate Recommender — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Company: {profile.company.name}")
    logger.info("=" * 60)

    stats = {"events_processed": 0, "alternates_created": 0, "errors": 0}

    with get_session() as session:
        events = _get_unresolved_risk_events(session)
        logger.info(f"Found {len(events)} unresolved HIGH+ risk events")

        for event in events:
            try:
                created = process_risk_event(event, session, profile)
                stats["alternates_created"] += len(created)
                stats["events_processed"]   += 1
            except Exception as e:
                logger.error(f"  Error processing risk_event id={event.id}: {e}", exc_info=True)
                stats["errors"] += 1

        session.commit()

    elapsed = time.time() - start
    logger.info(
        f"Module 3 complete in {elapsed:.1f}s — "
        f"events={stats['events_processed']} "
        f"alternates={stats['alternates_created']} "
        f"errors={stats['errors']}"
    )
    return stats
