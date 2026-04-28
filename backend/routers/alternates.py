"""
backend/routers/alternates.py
──────────────────────────────
Alternate supplier recommendations endpoints.
"""

from fastapi import APIRouter, Query
from typing import Optional

from module1.db.session import get_session
from module1.db.models import AlternateSupplier, RiskEvent, Supplier
from backend.utils import utc_iso

router = APIRouter()


def _serialize_alt(a: AlternateSupplier, risk_event: RiskEvent = None, disrupted: Supplier = None) -> dict:
    return {
        "id":                    a.id,
        "rank":                  a.rank,
        "alternate_name":        a.alternate_name,
        "country":               a.country,
        "country_code":          a.country_code,
        "capacity_fit":          a.capacity_fit,
        "lead_time_weeks":       a.lead_time_weeks,
        "alt_score":             a.alt_score,
        "geographic_safety_score": a.geographic_safety_score,
        "track_record_score":    a.track_record_score,
        "rationale":             a.rationale,
        "created_at":            utc_iso(a.created_at),
        "risk_event": {
            "id":            risk_event.id if risk_event else None,
            "risk_score":    risk_event.risk_score if risk_event else None,
            "severity_band": risk_event.severity_band if risk_event else None,
            "event_type":    risk_event.event_type if risk_event else None,
            "is_indirect":   risk_event.is_indirect if risk_event else None,
            "impact_chain":  risk_event.impact_chain if risk_event else None,
            "commodity":     risk_event.commodity if risk_event else None,
        } if risk_event else None,
        "disrupted_supplier": {
            "id":           disrupted.id if disrupted else None,
            "name":         disrupted.name if disrupted else None,
            "country":      disrupted.country if disrupted else None,
            "country_code": disrupted.country_code if disrupted else None,
            "tier":         disrupted.tier if disrupted else None,
            "criticality":  disrupted.criticality if disrupted else None,
        } if disrupted else None,
    }


@router.get("/")
def list_alternates(
    risk_event_id: Optional[int] = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    """List alternate supplier recommendations, optionally filtered by risk event."""
    with get_session() as session:
        q = session.query(AlternateSupplier)
        if risk_event_id:
            q = q.filter_by(risk_event_id=risk_event_id)
        total = q.count()
        alts = q.order_by(AlternateSupplier.created_at.desc(), AlternateSupplier.rank).limit(limit).all()

        result = []
        for a in alts:
            re = session.query(RiskEvent).filter_by(id=a.risk_event_id).first()
            dis = session.query(Supplier).filter_by(id=a.disrupted_supplier_id).first() if a.disrupted_supplier_id else None
            result.append(_serialize_alt(a, re, dis))

        return {"total": total, "items": result}


@router.get("/by-risk-event/{risk_event_id}")
def get_alternates_for_event(risk_event_id: int):
    """Get all alternates for a specific risk event, sorted by rank."""
    with get_session() as session:
        alts = (
            session.query(AlternateSupplier)
            .filter_by(risk_event_id=risk_event_id)
            .order_by(AlternateSupplier.rank)
            .all()
        )
        re = session.query(RiskEvent).filter_by(id=risk_event_id).first()
        dis = session.query(Supplier).filter_by(id=re.supplier_id).first() if re and re.supplier_id else None
        return [_serialize_alt(a, re, dis) for a in alts]


@router.get("/summary")
def alternates_summary():
    """How many risk events have alternates vs still pending."""
    with get_session() as session:
        from sqlalchemy import exists
        total_alts = session.query(AlternateSupplier).count()
        events_covered = session.query(AlternateSupplier.risk_event_id).distinct().count()
        pending = (
            session.query(RiskEvent)
            .filter(
                RiskEvent.risk_score >= 60,
                RiskEvent.supplier_id.isnot(None),
                ~exists().where(AlternateSupplier.risk_event_id == RiskEvent.id)
            )
            .count()
        )
        return {
            "total_alternates": total_alts,
            "events_covered":   events_covered,
            "events_pending":   pending,
        }
