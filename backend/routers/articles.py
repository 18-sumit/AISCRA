"""
backend/routers/articles.py
────────────────────────────
Article feed endpoints — paginated and filterable.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Query

from module1.db.session import get_session
from module1.db.models import Article
from backend.utils import utc_iso

router = APIRouter()


def _serialize(a: Article) -> dict:
    return {
        "id":                    a.id,
        "url":                   a.url,
        "headline":              a.headline,
        "summary":               a.summary,
        "source_name":           a.source_name,
        "source_domain":         a.source_domain,
        "published_at":          utc_iso(a.published_at),
        "fetched_at":            utc_iso(a.fetched_at),
        "fetch_type":            a.fetch_type,
        "is_relevant_prefilter": a.is_relevant_prefilter,
        "gemini_screened":       a.gemini_screened,
        "is_supply_chain_risk":  a.is_supply_chain_risk,
        "is_indirect_risk":      a.is_indirect_risk,
        "gemini_plausibility":   a.gemini_plausibility,
        "gemini_confidence":     a.gemini_confidence,
        "impact_chain":          a.impact_chain,
        "affected_commodities":  a.get_affected_commodities(),
        "affected_suppliers":    a.get_affected_suppliers(),
        "time_horizon":          a.time_horizon,
        "processed":             a.processed,
    }


@router.get("/")
def list_articles(
    fetch_type: Optional[str] = Query(None, description="'targeted' or 'hot_news'"),
    risk_only:  bool = Query(False, description="Only confirmed supply chain risks"),
    hours:      int  = Query(48, description="Articles from last N hours"),
    page:       int  = Query(1,  ge=1),
    page_size:  int  = Query(30, ge=1, le=100),
    search:     Optional[str] = Query(None, description="Search in headline"),
):
    """
    Paginated article feed. Supports filtering by track type, risk status,
    time window, and headline search.
    """
    with get_session() as session:
        q = session.query(Article)

        since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        q = q.filter(Article.fetched_at >= since)

        if fetch_type in ("targeted", "hot_news"):
            q = q.filter_by(fetch_type=fetch_type)

        if risk_only:
            q = q.filter_by(is_supply_chain_risk=True)

        if search:
            q = q.filter(Article.headline.ilike(f"%{search}%"))

        total = q.count()
        articles = (
            q.order_by(Article.fetched_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "pages":     (total + page_size - 1) // page_size,
            "items":     [_serialize(a) for a in articles],
        }


@router.get("/{article_id}")
def get_article(article_id: int):
    """Get a single article by ID."""
    with get_session() as session:
        a = session.query(Article).filter_by(id=article_id).first()
        if not a:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Article not found")
        return _serialize(a)
