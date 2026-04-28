"""
backend/routers/logs.py
"""
from fastapi import APIRouter
from module1.db.session import get_session
from module1.db.models import FetchLog
from backend.utils import utc_iso

router = APIRouter()

@router.get("/")
def list_logs(limit: int = 20):
    with get_session() as session:
        rows = (
            session.query(FetchLog)
            .order_by(FetchLog.run_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":               r.id,
                "run_at":           utc_iso(r.run_at),
                "source":           r.source,
                "fetch_type":       r.fetch_type,
                "articles_fetched": r.articles_fetched,
                "articles_new":     r.articles_new,
                "articles_relevant":r.articles_relevant,
                "duration_seconds": r.duration_seconds,
                "status":           r.status,
                "error_message":    r.error_message,
            }
            for r in rows
        ]
