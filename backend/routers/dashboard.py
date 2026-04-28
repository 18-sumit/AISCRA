"""
backend/routers/dashboard.py
─────────────────────────────
Dashboard stats and summary endpoints.
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from sqlalchemy import func, text

from module1.db.session import get_session
from module1.db.models import Article, Supplier, FetchLog, CountryRisk, KeywordRegistry, RiskEvent, AlternateSupplier
from backend.utils import utc_iso

router = APIRouter()


@router.get("/stats")
def get_stats():
    """Top-level dashboard stats cards."""
    with get_session() as session:
        total_articles   = session.query(Article).count()
        track_a          = session.query(Article).filter_by(fetch_type="targeted").count()
        track_b          = session.query(Article).filter_by(fetch_type="hot_news").count()
        unprocessed      = session.query(Article).filter_by(processed=False).count()
        confirmed_risks  = session.query(Article).filter_by(is_supply_chain_risk=True).count()
        indirect_risks   = session.query(Article).filter_by(is_indirect_risk=True).count()
        active_suppliers = session.query(Supplier).filter_by(active=True).count()
        critical_suppliers = session.query(Supplier).filter_by(
            active=True, criticality="critical"
        ).count()

        # Articles in last 24 hours
        since_24h = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        articles_24h = session.query(Article).filter(
            Article.fetched_at >= since_24h
        ).count()

        # Last fetch time
        last_log = session.query(FetchLog).order_by(FetchLog.run_at.desc()).first()
        last_fetch = utc_iso(last_log.run_at) if last_log else None
        last_fetch_status = last_log.status if last_log else "never"

        # Keywords count
        n_keywords = session.query(KeywordRegistry).filter_by(active=True).count()

        # Gemini screened
        gemini_screened = session.query(Article).filter_by(
            fetch_type="hot_news", gemini_screened=True
        ).count()

    return {
        "total_articles":      total_articles,
        "track_a":             track_a,
        "track_b":             track_b,
        "articles_24h":        articles_24h,
        "unprocessed":         unprocessed,
        "confirmed_risks":     confirmed_risks,
        "indirect_risks":      indirect_risks,
        "active_suppliers":    active_suppliers,
        "critical_suppliers":  critical_suppliers,
        "n_keywords":          n_keywords,
        "gemini_screened":     gemini_screened,
        "last_fetch":          last_fetch,
        "last_fetch_status":   last_fetch_status,
    }


@router.get("/country-risk")
def get_country_risk():
    """All country risk scores for the risk map table."""
    with get_session() as session:
        rows = session.query(CountryRisk).order_by(CountryRisk.risk_score.desc()).all()
        return [
            {
                "country_name":  r.country_name,
                "country_code":  r.country_code,
                "risk_score":    r.risk_score,
                "risk_category": r.risk_category,
                "notes":         r.notes,
            }
            for r in rows
        ]


@router.get("/feed-summary")
def get_feed_summary():
    """Source domain breakdown for the last 200 articles."""
    with get_session() as session:
        rows = (
            session.query(Article.source_domain, func.count(Article.id).label("count"))
            .group_by(Article.source_domain)
            .order_by(func.count(Article.id).desc())
            .limit(15)
            .all()
        )
        return [{"domain": r.source_domain or "unknown", "count": r.count} for r in rows]


@router.get("/ingestion-timeline")
def get_ingestion_timeline():
    """Articles ingested per day for the last 14 days (chart data)."""
    with get_session() as session:
        since = datetime.now(tz=timezone.utc) - timedelta(days=14)
        rows = (
            session.query(Article)
            .filter(Article.fetched_at >= since)
            .all()
        )

    # Group by date + fetch_type
    from collections import defaultdict
    buckets: dict = defaultdict(lambda: {"targeted": 0, "hot_news": 0})
    for a in rows:
        if a.fetched_at:
            day = a.fetched_at.strftime("%Y-%m-%d")
            buckets[day][a.fetch_type] += 1

    return [
        {"date": day, "track_a": v["targeted"], "track_b": v["hot_news"]}
        for day, v in sorted(buckets.items())
    ]


@router.get("/module-status")
def get_module_status():
    """
    Real-time status for each module based on actual DB state.
    Used by Analytics view module status panel.
    """
    with get_session() as session:
        # Module 1 — active if there are any fetch logs
        m1_runs = session.query(FetchLog).count()
        m1_last = session.query(FetchLog).order_by(FetchLog.run_at.desc()).first()

        # Module 2 — active if there are any risk events
        m2_events = session.query(RiskEvent).count()
        m2_high   = session.query(RiskEvent).filter(RiskEvent.risk_score >= 60).count()
        m2_critical = session.query(RiskEvent).filter(RiskEvent.risk_score >= 80).count()
        m2_processed = session.query(Article).filter_by(processed=True).count()

        # Module 3 — active if there are any alternates generated
        m3_alts = session.query(AlternateSupplier).count()
        m3_events_covered = session.query(AlternateSupplier.risk_event_id).distinct().count()

        # Pending HIGH+ events without alternates
        from sqlalchemy import exists
        m3_pending = session.query(RiskEvent).filter(
            RiskEvent.risk_score >= 60,
            RiskEvent.supplier_id.isnot(None),
            ~exists().where(AlternateSupplier.risk_event_id == RiskEvent.id)
        ).count()

    def _status(active: bool, partial: bool = False) -> str:
        if active:   return "active"
        if partial:  return "partial"
        return "pending"

    return {
        "module1": {
            "status":    _status(m1_runs > 0),
            "runs":      m1_runs,
            "last_run":  utc_iso(m1_last.run_at) if m1_last else None,
        },
        "module2": {
            "status":      _status(m2_events > 0),
            "risk_events": m2_events,
            "high_plus":   m2_high,
            "critical":    m2_critical,
            "processed_articles": m2_processed,
        },
        "module3": {
            "status":          _status(m3_alts > 0, partial=m3_pending > 0),
            "alternates":      m3_alts,
            "events_covered":  m3_events_covered,
            "pending_events":  m3_pending,
        },
        "module4": {
            "status": "partial",  # dashboard live, AI agent pending
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Threshold configuration (in-memory, resets on server restart)
#  Persist to .env or DB in a future version
# ─────────────────────────────────────────────────────────────────────────────
_thresholds = {
    "critical": 80,
    "high":     60,
    "medium":   40,
    "low":      20,
}


def _classify_severity_band(score: float) -> str:
    """Classify a risk score into a severity band using current thresholds."""
    if score >= _thresholds["critical"]:
        return "CRITICAL"
    elif score >= _thresholds["high"]:
        return "HIGH"
    elif score >= _thresholds["medium"]:
        return "MEDIUM"
    elif score >= _thresholds["low"]:
        return "LOW"
    else:
        return "WATCH"


def _reclassify_all_events():
    """Reclassify all risk events based on current thresholds and update DB."""
    with get_session() as session:
        events = session.query(RiskEvent).all()
        for event in events:
            event.severity_band = _classify_severity_band(event.risk_score)
        session.commit()


@router.get("/thresholds")
def get_thresholds():
    return _thresholds


@router.post("/thresholds")
def set_thresholds(body: dict):
    for key in ("critical", "high", "medium", "low"):
        if key in body:
            val = int(body[key])
            _thresholds[key] = max(0, min(100, val))
    # Reclassify all events with new thresholds
    _reclassify_all_events()
    return _thresholds
