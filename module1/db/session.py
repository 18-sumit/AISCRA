"""
module1/db/session.py
─────────────────────
Database engine and session factory.
Reads DB_TYPE from .env: "sqlite" (default) or "postgresql".

Usage:
    from module1.db.session import get_session, engine
    with get_session() as session:
        articles = session.query(Article).all()
"""

import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
#  Engine construction
# ─────────────────────────────────────────────────────────────────────────────

def _build_engine():
    db_type = os.getenv("DB_TYPE", "sqlite").lower()

    if db_type == "postgresql":
        url = os.getenv("POSTGRES_URL")
        if not url:
            raise ValueError("DB_TYPE=postgresql but POSTGRES_URL is not set in .env")
        engine = create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,   # detect stale connections
            echo=False,
        )
        return engine, "postgresql"

    else:
        # SQLite (default — zero setup)
        sqlite_path = os.getenv("SQLITE_PATH", "./data/supply_chain.db")
        db_file = Path(sqlite_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(
            f"sqlite:///{db_file}",
            connect_args={"check_same_thread": False},
            echo=False,
        )

        # Enable WAL mode for concurrent readers + one writer
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        return engine, "sqlite"


engine, DB_BACKEND = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# ─────────────────────────────────────────────────────────────────────────────
#  Public helpers
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def get_session() -> Session:
    """
    Context manager that yields a SQLAlchemy session, commits on success,
    rolls back on error, and always closes.

    Usage:
        with get_session() as session:
            session.add(article)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Quick health check — returns True if DB is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
