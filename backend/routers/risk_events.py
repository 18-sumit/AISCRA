"""
backend/routers/risk_events.py
────────────────────────────────
Risk events endpoints — scored results from Module 2.
"""

from fastapi import APIRouter, Query
from typing import Optional

from module1.db.session import get_session
from module1.db.models import RiskEvent, Article, Supplier
from backend.utils import utc_iso

router = APIRouter()


def _get_current_thresholds():
    """Import thresholds from dashboard module (avoids circular imports)."""
    # Import here to avoid circular imports
    from backend.routers.dashboard import _thresholds
    return _thresholds


def _classify_severity_band(score: float) -> str:
    """Classify a risk score into a severity band using current thresholds."""
    thresholds = _get_current_thresholds()
    if score >= thresholds["critical"]:
        return "CRITICAL"
    elif score >= thresholds["high"]:
        return "HIGH"
    elif score >= thresholds["medium"]:
        return "MEDIUM"
    elif score >= thresholds["low"]:
        return "LOW"
    else:
        return "WATCH"


def _serialize(e: RiskEvent, article: Article = None, supplier: Supplier = None) -> dict:
    # Use dynamic classification based on current thresholds
    severity_band = _classify_severity_band(e.risk_score)
    
    return {
        "id":            e.id,
        "risk_score":    e.risk_score,
        "severity_band": severity_band,
        "event_type":    e.event_type,
        "commodity":     e.commodity,
        "is_indirect":   e.is_indirect,
        "impact_chain":  e.impact_chain,
        "time_horizon":  e.time_horizon,
        "alert_sent":    e.alert_sent,
        "created_at":    utc_iso(e.created_at),
        # Approximate score components (stored in affected_countries_json for now)
        "severity_score":    None,
        "dep_score":         None,
        "geo_score":         None,
        "recency_score":     None,
        "credibility_score": None,
        "article": {
            "id":               article.id if article else None,
            "headline":         article.headline if article else None,
            "url":              article.url if article else None,
            "source_name":      article.source_name if article else None,
            "published_at":     utc_iso(article.published_at) if article else None,
            "fetch_type":       article.fetch_type if article else None,
            "gemini_confidence":article.gemini_confidence if article else None,
        } if article else None,
        "supplier": {
            "id":                supplier.id if supplier else None,
            "name":              supplier.name if supplier else None,
            "country":           supplier.country if supplier else None,
            "country_code":      supplier.country_code if supplier else None,
            "tier":              supplier.tier if supplier else None,
            "criticality":       supplier.criticality if supplier else None,
            "dependency_weight": supplier.dependency_weight if supplier else None,
        } if supplier else None,
    }


@router.get("/")
def list_risk_events(
    severity: Optional[str] = Query(None, description="CRITICAL|HIGH|MEDIUM|LOW|WATCH"),
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0, ge=0),
):
    with get_session() as session:
        q = session.query(RiskEvent)
        total_all = q.count()
        events = q.order_by(RiskEvent.risk_score.desc()).offset(offset).limit(limit).all()

        result = []
        for e in events:
            article  = session.query(Article).filter_by(id=e.article_id).first()
            supplier = session.query(Supplier).filter_by(id=e.supplier_id).first() if e.supplier_id else None
            serialized = _serialize(e, article, supplier)
            
            # Filter by severity band if requested
            if severity is None or serialized["severity_band"] == severity.upper():
                result.append(serialized)

        # Count filtered results for total (after threshold-based classification)
        if severity:
            filtered_count = sum(1 for r in result)
            return {"total": filtered_count, "items": result}
        else:
            return {"total": total_all, "items": result}


@router.get("/summary")
def risk_summary():
    """Band counts for dashboard stats cards (uses current thresholds)."""
    with get_session() as session:
        bands = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "WATCH"]
        all_events = session.query(RiskEvent).all()
        
        # Classify all events using current thresholds
        counts = {b: 0 for b in bands}
        for event in all_events:
            band = _classify_severity_band(event.risk_score)
            counts[band] += 1
        
        counts["total"] = len(all_events)
        return counts
