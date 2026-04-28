"""
module1/db/models.py
────────────────────
All 8 SQLAlchemy ORM models for the Supply Chain Risk Analysis system.

Tables:
  1. articles          — ingested news from both tracks
  2. risk_events       — risks detected by Module 2 (written by M2, schema defined here)
  3. suppliers         — company supplier network from company_profile.yaml
  4. alternate_suppliers — recommendations from Module 3 (schema defined here)
  5. keyword_registry  — Track A search phrases per entity
  6. country_risk      — pre-seeded country risk scores
  7. source_credibility — pre-seeded domain credibility scores
  8. fetch_logs        — one row per ingestion run
"""

import json
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
#  1. ARTICLES
# ─────────────────────────────────────────────────────────────────────────────
class Article(Base):
    """
    Central news article table. Both Track A (targeted) and Track B (hot_news)
    articles land here. The fetch_type column distinguishes them.

    Processing state machine:
      Track A: gemini_screened=True,  processed=False  → straight to Stage 1
      Track B: gemini_screened=False, processed=False  → Stage 0 first
    """
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Identity & deduplication ──────────────────────────────────────────
    url_hash = Column(String(64), nullable=False, unique=True, index=True,
                      comment="SHA-256 of URL — primary dedup key")
    url = Column(Text, nullable=False)

    # ── Content ───────────────────────────────────────────────────────────
    headline = Column(Text, nullable=False)
    body = Column(Text, nullable=True)
    summary = Column(Text, nullable=True,
                     comment="First 3 sentences or newspaper3k summary")

    # ── Source metadata ───────────────────────────────────────────────────
    source_name = Column(String(120), nullable=True)
    source_domain = Column(String(120), nullable=True, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # ── Track classification ───────────────────────────────────────────────
    fetch_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="'targeted' (Track A) or 'hot_news' (Track B)"
    )

    # ── Pre-filter flags ──────────────────────────────────────────────────
    is_relevant_prefilter = Column(
        Boolean, default=None, nullable=True,
        comment="Track A keyword relevance pre-filter result"
    )

    # ── Gemini Stage 0 screening (Track B only) ───────────────────────────
    gemini_screened = Column(
        Boolean, default=False, nullable=False,
        comment="True once Gemini Stage 0 has evaluated this article"
    )
    is_supply_chain_risk = Column(
        Boolean, default=None, nullable=True,
        comment="Stage 0 verdict — None means not yet evaluated"
    )
    gemini_plausibility = Column(
        String(10), nullable=True,
        comment="'high' | 'medium' | 'low' from Stage 0"
    )
    gemini_confidence = Column(
        Float, nullable=True,
        comment="Stage 0 confidence score 0.0–1.0"
    )
    impact_chain = Column(
        Text, nullable=True,
        comment="Gemini Stage 0 step-by-step impact reasoning"
    )
    is_indirect_risk = Column(
        Boolean, default=False, nullable=False,
        comment="True for hot_news articles confirmed as indirect risks"
    )
    affected_commodities_json = Column(
        Text, nullable=True,
        comment="JSON list of commodities from Stage 0"
    )
    affected_suppliers_json = Column(
        Text, nullable=True,
        comment="JSON list of supplier names from Stage 0"
    )
    time_horizon = Column(
        String(20), nullable=True,
        comment="'immediate' | 'weeks' | 'months' from Stage 0"
    )

    # ── Module 2 processing ───────────────────────────────────────────────
    processed = Column(
        Boolean, default=False, nullable=False, index=True,
        comment="True once Module 2 has fully processed this article"
    )
    embedding_json = Column(
        Text, nullable=True,
        comment="JSON-serialised sentence-BERT embedding (384 floats for MiniLM)"
    )

    # ── Relationships ─────────────────────────────────────────────────────
    risk_events = relationship("RiskEvent", back_populates="article")

    # ── Constraints & indexes ─────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("fetch_type IN ('targeted', 'hot_news')", name="ck_articles_fetch_type"),
        Index("ix_articles_unprocessed", "processed", "gemini_screened"),
        Index("ix_articles_published_source", "published_at", "source_domain"),
    )

    def get_affected_commodities(self):
        return json.loads(self.affected_commodities_json) if self.affected_commodities_json else []

    def get_affected_suppliers(self):
        return json.loads(self.affected_suppliers_json) if self.affected_suppliers_json else []

    def get_embedding(self):
        return json.loads(self.embedding_json) if self.embedding_json else None

    def set_embedding(self, vector: list):
        self.embedding_json = json.dumps(vector)

    def __repr__(self):
        return f"<Article id={self.id} fetch_type={self.fetch_type} headline={self.headline[:60]!r}>"


# ─────────────────────────────────────────────────────────────────────────────
#  2. RISK EVENTS  (written by Module 2; schema defined here)
# ─────────────────────────────────────────────────────────────────────────────
class RiskEvent(Base):
    """
    One row per supply chain risk detected and scored by Module 2.
    References the source article and the affected supplier.
    """
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)

    commodity = Column(String(200), nullable=True)
    risk_score = Column(Float, nullable=False, comment="0–100 composite score")
    severity_band = Column(
        String(20), nullable=True,
        comment="CRITICAL | HIGH | MEDIUM | LOW | WATCH"
    )
    event_type = Column(String(100), nullable=True,
                        comment="e.g. 'Sanctions', 'Natural Disaster', 'FDA Warning'")

    is_indirect = Column(Boolean, default=False, nullable=False)
    impact_chain = Column(Text, nullable=True)
    affected_countries_json = Column(Text, nullable=True)
    time_horizon = Column(String(20), nullable=True)

    alert_sent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────
    article = relationship("Article", back_populates="risk_events")
    supplier = relationship("Supplier", back_populates="risk_events")
    alternate_suppliers = relationship("AlternateSupplier", back_populates="risk_event")

    def get_affected_countries(self):
        return json.loads(self.affected_countries_json) if self.affected_countries_json else []

    def __repr__(self):
        return f"<RiskEvent id={self.id} score={self.risk_score} band={self.severity_band}>"


# ─────────────────────────────────────────────────────────────────────────────
#  3. SUPPLIERS
# ─────────────────────────────────────────────────────────────────────────────
class Supplier(Base):
    """
    Company's supplier network loaded from company_profile.yaml at --init-db time.
    Re-seeded every time the YAML is updated and --init-db is re-run.
    """
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    name_aliases_json = Column(Text, nullable=True,
                               comment="JSON list of alternate names / abbreviations")
    commodity = Column(String(300), nullable=True)
    country = Column(String(100), nullable=True)
    country_code = Column(String(5), nullable=True, index=True)
    tier = Column(Integer, nullable=False, comment="1=direct, 2=sub-supplier, 3=raw material")
    criticality = Column(String(20), nullable=True,
                         comment="critical | high | medium | low")
    dependency_weight = Column(Float, nullable=True,
                               comment="0.0–1.0 fraction of commodity from this supplier")
    notes = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Relationships ─────────────────────────────────────────────────────
    risk_events = relationship("RiskEvent", back_populates="supplier")

    __table_args__ = (
        CheckConstraint("tier IN (1, 2, 3)", name="ck_suppliers_tier"),
        CheckConstraint("dependency_weight >= 0.0 AND dependency_weight <= 1.0",
                        name="ck_suppliers_dep_weight"),
    )

    def get_aliases(self) -> list:
        return json.loads(self.name_aliases_json) if self.name_aliases_json else []

    def all_names(self) -> list:
        """Supplier name + all aliases — used for entity matching."""
        return [self.name] + self.get_aliases()

    def __repr__(self):
        return f"<Supplier id={self.id} name={self.name!r} tier={self.tier}>"


# ─────────────────────────────────────────────────────────────────────────────
#  4. ALTERNATE SUPPLIERS  (written by Module 3; schema defined here)
# ─────────────────────────────────────────────────────────────────────────────
class AlternateSupplier(Base):
    """
    Ranked alternate supplier recommendations generated by Module 3
    when a risk event scores >= HIGH threshold (60+).
    """
    __tablename__ = "alternate_suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    risk_event_id = Column(Integer, ForeignKey("risk_events.id"), nullable=False, index=True)
    disrupted_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    alternate_name = Column(String(200), nullable=False)
    country = Column(String(100), nullable=True)
    country_code = Column(String(5), nullable=True)
    capacity_fit = Column(String(20), nullable=True,
                          comment="high | medium | low")
    lead_time_weeks = Column(Float, nullable=True)
    alt_score = Column(Float, nullable=True, comment="0–100 ranking score from M3 formula")
    track_record_score = Column(Float, nullable=True)
    geographic_safety_score = Column(Float, nullable=True)
    rationale = Column(Text, nullable=True, comment="Gemini-generated 2–3 sentence rationale")
    rank = Column(Integer, nullable=True, comment="1=best recommendation")
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── Relationships ─────────────────────────────────────────────────────
    risk_event = relationship("RiskEvent", back_populates="alternate_suppliers")

    def __repr__(self):
        return f"<AlternateSupplier name={self.alternate_name!r} score={self.alt_score} rank={self.rank}>"


# ─────────────────────────────────────────────────────────────────────────────
#  5. KEYWORD REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
class KeywordRegistry(Base):
    """
    Track A search phrases per entity. Loaded from company_profile.yaml.
    Batched into NewsAPI / GNews keyword queries.
    """
    __tablename__ = "keyword_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False, index=True,
                      comment="supplier | commodity | logistics | regulatory | geopolitical")
    entity_name = Column(String(200), nullable=False)
    keywords_json = Column(Text, nullable=False,
                           comment="JSON list of search phrase strings")
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_keywords(self) -> list:
        return json.loads(self.keywords_json) if self.keywords_json else []

    def __repr__(self):
        return f"<KeywordRegistry entity={self.entity_name!r} category={self.category}>"


# ─────────────────────────────────────────────────────────────────────────────
#  6. COUNTRY RISK
# ─────────────────────────────────────────────────────────────────────────────
class CountryRisk(Base):
    """
    Pre-seeded country risk scores used in Stage 5 risk score formula.
    Updated periodically (or via the --update-country-risk CLI command).
    """
    __tablename__ = "country_risk"

    id = Column(Integer, primary_key=True, autoincrement=True)
    country_name = Column(String(100), nullable=False)
    country_code = Column(String(5), nullable=False, unique=True, index=True)
    risk_score = Column(Float, nullable=False, comment="0–100")
    risk_category = Column(
        String(20), nullable=False,
        comment="stable | moderate | high | critical"
    )
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_country_risk_score"),
        CheckConstraint(
            "risk_category IN ('stable', 'moderate', 'high', 'critical')",
            name="ck_country_risk_category"
        ),
    )

    def __repr__(self):
        return f"<CountryRisk {self.country_code} score={self.risk_score} ({self.risk_category})>"


# ─────────────────────────────────────────────────────────────────────────────
#  7. SOURCE CREDIBILITY
# ─────────────────────────────────────────────────────────────────────────────
class SourceCredibility(Base):
    """
    Pre-seeded domain-level credibility scores used in Stage 5.
    Higher score = more weight given to risk events from this source.
    """
    __tablename__ = "source_credibility"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(150), nullable=False, unique=True, index=True)
    credibility_score = Column(Float, nullable=False, comment="0–100")
    category = Column(String(20), nullable=True,
                      comment="tier1 | tier2 | tier3")
    source_type = Column(String(50), nullable=True,
                         comment="wire_service | trade_pub | government | regional | unknown")
    notes = Column(String(300), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "credibility_score >= 0 AND credibility_score <= 100",
            name="ck_source_credibility_score"
        ),
    )

    def __repr__(self):
        return f"<SourceCredibility domain={self.domain!r} score={self.credibility_score}>"


# ─────────────────────────────────────────────────────────────────────────────
#  8. FETCH LOGS
# ─────────────────────────────────────────────────────────────────────────────
class FetchLog(Base):
    """
    One row per ingestion run per source. Records throughput and errors
    for monitoring and debugging.
    """
    __tablename__ = "fetch_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = Column(String(100), nullable=False,
                    comment="e.g. 'newsapi_track_a', 'rss_reuters_world', 'gdelt_track_b'")
    fetch_type = Column(String(20), nullable=True,
                        comment="'targeted' or 'hot_news'")
    articles_fetched = Column(Integer, default=0)
    articles_new = Column(Integer, default=0,
                          comment="Passed dedup — actually written to DB")
    articles_relevant = Column(Integer, default=0,
                               comment="Passed keyword pre-filter (Track A only)")
    duration_seconds = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="success",
                    comment="success | partial | failed | skipped")
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return (f"<FetchLog source={self.source!r} new={self.articles_new} "
                f"status={self.status} at={self.run_at}>")
