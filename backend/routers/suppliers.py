"""
backend/routers/suppliers.py
"""
from fastapi import APIRouter
from module1.db.session import get_session
from module1.db.models import Supplier

router = APIRouter()

@router.get("/")
def list_suppliers():
    with get_session() as session:
        rows = (
            session.query(Supplier)
            .filter_by(active=True)
            .order_by(Supplier.tier, Supplier.criticality)
            .all()
        )
        return [
            {
                "id":                r.id,
                "name":              r.name,
                "aliases":           r.get_aliases(),
                "commodity":         r.commodity,
                "country":           r.country,
                "country_code":      r.country_code,
                "tier":              r.tier,
                "criticality":       r.criticality,
                "dependency_weight": r.dependency_weight,
                "notes":             r.notes,
            }
            for r in rows
        ]
