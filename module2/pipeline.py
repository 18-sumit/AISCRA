"""
module2/pipeline.py
────────────────────
Module 2 orchestrator. Picks up unprocessed articles from the DB
and runs them through all 7 stages, writing risk_events rows.

Article processing state machine:
  Track B, gemini_screened=False → Stage 0 → Stage 1 → ... → Stage 6
  Track A / Stage 0 confirmed    → Stage 1 → ... → Stage 6

An article is marked processed=True only after the full pipeline completes.
"""

import json
import logging
import time
from datetime import datetime, timezone

from module1.db.models import Article, RiskEvent, Supplier
from module1.db.session import get_session
from module1.config.company_profile import load_profile

from module2.stages.stage0_gemini  import run_stage0
from module2.stages.stage1_relevance import run_stage1
from module2.stages.stage2_ner     import run_stage2
from module2.stages.stage3_severity import run_stage3
from module2.stages.stage4_matching import run_stage4
from module2.stages.stage5_scoring  import run_stage5
from module2.stages.stage6_graph    import run_stage6

logger = logging.getLogger(__name__)


def _fetch_unprocessed(session, limit: int = 100) -> list:
    """
    Fetch articles ready for Module 2 processing.
    Track B articles that haven't been Gemini-screened yet are excluded —
    Stage 0 will screen them first, then they'll be picked up next run.
    """
    return (
        session.query(Article)
        .filter(
            Article.processed == False,
            # Only process articles that are either:
            # - Track A (targeted), OR
            # - Track B that have been screened by Gemini AND confirmed as risks
            (
                (Article.fetch_type == "targeted") |
                (
                    (Article.fetch_type == "hot_news") &
                    (Article.gemini_screened == True) &
                    (Article.is_supply_chain_risk == True)
                )
            )
        )
        .order_by(Article.fetched_at.desc())
        .limit(limit)
        .all()
    )


def _save_risk_event(session, article, matched_supplier, score_result: dict, stage6_result: dict):
    """Write one risk_events row to the DB."""
    risk_event = RiskEvent(
        article_id=article.id,
        supplier_id=matched_supplier.supplier_id,
        commodity=matched_supplier.commodity,
        risk_score=score_result["risk_score"],
        severity_band=score_result["severity_band"],
        event_type=score_result["event_type"],
        is_indirect=article.is_indirect_risk,
        impact_chain=article.impact_chain,
        affected_countries_json=json.dumps(stage6_result.get("affected_nodes", [])),
        time_horizon=article.time_horizon,
        alert_sent=False,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(risk_event)
    return risk_event


def process_article(article, suppliers: list, profile, session) -> list:
    """
    Run one article through Stages 1–6.
    Returns list of RiskEvent objects created (one per matched supplier).
    """
    # Stage 1: Relevance classification
    relevant = run_stage1([article])
    if not relevant:
        article.processed = True
        logger.debug(f"  Article {article.id} failed Stage 1 — not relevant")
        return []

    # Stage 2: Named Entity Recognition
    entities = run_stage2(article)

    # Stage 3: Sentiment + Severity
    severity_result = run_stage3(article)

    # Stage 4: Entity-Supplier Matching
    matched_suppliers = run_stage4(article, entities, suppliers)

    if not matched_suppliers:
        article.processed = True
        logger.debug(f"  Article {article.id}: no suppliers matched")
        return []

    # Stages 5 + 6: Score + Graph propagation (once per matched supplier)
    risk_events = []
    for matched in matched_suppliers:
        score_result = run_stage5(article, matched, severity_result, session)
        stage6_result = run_stage6(
            matched,
            score_result["risk_score"],
            suppliers,
            profile.company.name,
        )

        risk_event = _save_risk_event(session, article, matched, score_result, stage6_result)
        risk_events.append(risk_event)

        logger.info(
            f"  ✓ Risk: [{score_result['severity_band']}] "
            f"{matched.supplier_name} — {article.headline[:55]} "
            f"(score={score_result['risk_score']:.1f})"
        )

    article.processed = True
    return risk_events


def run_pipeline(limit: int = 100) -> dict:
    """
    Full Module 2 pipeline run.

    Step 1: Run Stage 0 on all unscreened hot_news articles.
    Step 2: Process all ready articles through Stages 1–6.

    Returns stats dict.
    """
    start = time.time()
    profile = load_profile()

    logger.info("=" * 60)
    logger.info(f"Module 2 Risk Analysis — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Company: {profile.company.name}")
    logger.info("=" * 60)

    # Load active suppliers once (used across all articles)
    with get_session() as session:
        suppliers = session.query(Supplier).filter_by(active=True).all()
        # Detach from session for use across session boundaries
        session.expunge_all()

    logger.info(f"Loaded {len(suppliers)} active suppliers")

    stats = {
        "stage0_screened":  0,
        "stage0_risks":     0,
        "articles_processed": 0,
        "risk_events_created": 0,
        "errors": 0,
    }

    # ── Stage 0: Screen all unscreened hot_news ──────────────────────────────
    with get_session() as session:
        # Re-attach suppliers to this session
        from sqlalchemy import inspect
        attached_suppliers = session.query(Supplier).filter_by(active=True).all()

        s0_stats = run_stage0(session, profile)
        stats["stage0_screened"] = s0_stats.get("screened", 0)
        stats["stage0_risks"]    = s0_stats.get("risks", 0)

    # ── Stages 1–6: Process ready articles ───────────────────────────────────
    with get_session() as session:
        articles = _fetch_unprocessed(session, limit=limit)
        all_suppliers = session.query(Supplier).filter_by(active=True).all()

        logger.info(f"Stages 1–6: {len(articles)} articles to process")

        for article in articles:
            try:
                risk_events = process_article(article, all_suppliers, profile, session)
                stats["risk_events_created"] += len(risk_events)
                stats["articles_processed"]  += 1
            except Exception as e:
                logger.error(f"  Error processing article {article.id}: {e}", exc_info=True)
                article.processed = True  # mark processed to avoid infinite retry
                stats["errors"] += 1

        session.commit()

    elapsed = time.time() - start
    logger.info(
        f"Module 2 complete in {elapsed:.1f}s — "
        f"screened={stats['stage0_screened']} "
        f"risks_from_B={stats['stage0_risks']} "
        f"processed={stats['articles_processed']} "
        f"risk_events={stats['risk_events_created']} "
        f"errors={stats['errors']}"
    )
    return stats


def dispatch_alerts_after_run():
    """Called at end of Module 2 run to send notifications for new HIGH+ events."""
    try:
        from module4.notifications import check_and_dispatch_pending_alerts
        check_and_dispatch_pending_alerts()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"Alert dispatch skipped: {e}")
