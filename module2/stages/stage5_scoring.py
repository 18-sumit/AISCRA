"""
module2/stages/stage5_scoring.py
──────────────────────────────────
Stage 5: Risk Score Calculation.

Formula:
    Risk Score = (Severity × 0.35)
               + (Dependency Criticality × 0.30)
               + (Geographic Risk × 0.15)
               + (Recency × 0.12)
               + (Source Credibility × 0.08)

Indirect risk adjustment:
    If article.is_indirect_risk:
        final_score = calculated_score × gemini_confidence

Alert thresholds:
    80–100 → CRITICAL  (red alert, Slack + email + auto-briefing)
    60–79  → HIGH      (orange alert, show alternates)
    40–59  → MEDIUM    (yellow, in risk feed)
    20–39  → LOW       (blue, logged)
    0–19   → WATCH     (grey, stored only)
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Weights — must sum to 1.0
W_SEVERITY    = 0.35
W_CRITICALITY = 0.30
W_GEO_RISK    = 0.15
W_RECENCY     = 0.12
W_CREDIBILITY = 0.08

# Dependency criticality scores
CRITICALITY_SCORES = {
    # single-source, no alternative
    "critical": 92.5,
    # primary supplier, few alternatives
    "high": 77.0,
    # one of several suppliers
    "medium": 49.5,
    # easily replaceable
    "low": 22.0,
}

# Alert thresholds
ALERT_BANDS = [
    (80, "CRITICAL"),
    (60, "HIGH"),
    (40, "MEDIUM"),
    (20, "LOW"),
    (0,  "WATCH"),
]


def get_alert_band(score: float) -> str:
    for threshold, band in ALERT_BANDS:
        if score >= threshold:
            return band
    return "WATCH"


def recency_score(published_at: Optional[datetime]) -> float:
    """
    Exponential decay: score = 100 × e^(−0.05 × hours_since_publication)
    At 0h → 100, at 24h → 30, at 72h → 3
    """
    if published_at is None:
        return 50.0  # unknown age — use neutral value

    now = datetime.now(tz=timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    hours = max(0, (now - published_at).total_seconds() / 3600)
    return 100.0 * math.exp(-0.05 * hours)


def source_credibility_score(source_domain: Optional[str], session) -> float:
    """
    Look up domain in source_credibility table.
    Falls back to 20 (unknown source) if not found.
    """
    if not source_domain:
        return 20.0

    try:
        from module1.db.models import SourceCredibility
        row = session.query(SourceCredibility).filter_by(domain=source_domain).first()
        if row:
            return row.credibility_score
        # Try parent domain (strip subdomain)
        parts = source_domain.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            row = session.query(SourceCredibility).filter_by(domain=parent).first()
            if row:
                return row.credibility_score
    except Exception as e:
        logger.error(f"Source credibility lookup failed: {e}")

    return 20.0  # unknown source


def geo_risk_score(country_code: Optional[str], session) -> float:
    """
    Look up country risk score from country_risk table.
    Falls back to 50 (moderate) if not found.
    """
    if not country_code:
        return 50.0

    try:
        from module1.db.models import CountryRisk
        row = session.query(CountryRisk).filter_by(country_code=country_code).first()
        if row:
            return row.risk_score
    except Exception as e:
        logger.error(f"Country risk lookup failed: {e}")

    return 50.0  # unknown country → moderate


def run_stage5(article, matched_supplier, severity_result: dict, session) -> dict:
    """
    Calculate the composite risk score for one article–supplier pair.

    Args:
        article:          Article ORM object
        matched_supplier: MatchedSupplier from Stage 4
        severity_result:  dict from Stage 3 (combined_severity, event_type, etc.)
        session:          SQLAlchemy session for DB lookups

    Returns:
        dict with risk_score, severity_band, and all component scores
    """
    # Component 1: Severity (from Stage 3)
    severity = severity_result.get("combined_severity", 30.0)

    # Component 2: Dependency criticality (from supplier record)
    dep_criticality = CRITICALITY_SCORES.get(
        matched_supplier.criticality, CRITICALITY_SCORES["medium"]
    )
    # Adjust by actual dependency weight (0.0–1.0)
    dep_weight = matched_supplier.dependency_weight or 0.5
    dep_score = dep_criticality * (0.7 + 0.3 * dep_weight)  # weight scales score ±30%

    # Component 3: Geographic risk
    geo = geo_risk_score(matched_supplier.country_code, session)

    # Component 4: Recency
    recency = recency_score(article.published_at)

    # Component 5: Source credibility
    credibility = source_credibility_score(article.source_domain, session)

    # Weighted sum
    raw_score = (
        severity    * W_SEVERITY    +
        dep_score   * W_CRITICALITY +
        geo         * W_GEO_RISK    +
        recency     * W_RECENCY     +
        credibility * W_CREDIBILITY
    )
    raw_score = max(0.0, min(100.0, raw_score))

    # Indirect risk confidence adjustment
    final_score = raw_score
    if article.is_indirect_risk and article.gemini_confidence:
        final_score = raw_score * article.gemini_confidence
        logger.debug(
            f"  Stage 5: indirect risk adjustment "
            f"{raw_score:.1f} × {article.gemini_confidence:.2f} = {final_score:.1f}"
        )

    final_score = max(0.0, min(100.0, final_score))
    severity_band = get_alert_band(final_score)

    result = {
        "risk_score":      round(final_score, 2),
        "raw_score":       round(raw_score, 2),
        "severity_band":   severity_band,
        "severity_score":  round(severity, 2),
        "dep_score":       round(dep_score, 2),
        "geo_score":       round(geo, 2),
        "recency_score":   round(recency, 2),
        "credibility_score": round(credibility, 2),
        "event_type":      severity_result.get("event_type", "other"),
        "is_indirect":     article.is_indirect_risk,
        "gemini_confidence": article.gemini_confidence,
    }

    logger.debug(
        f"  Stage 5: score={final_score:.1f} [{severity_band}] | "
        f"sev={severity:.1f} dep={dep_score:.1f} geo={geo:.1f} "
        f"rec={recency:.1f} cred={credibility:.1f}"
    )

    return result
