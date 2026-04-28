"""
module3/ranker.py
──────────────────
Alternate supplier ranking formula.

Alternate Score = (Capacity Fit × 0.35) + (Geographic Safety × 0.30)
               + (Lead Time Score × 0.20) + (Track Record × 0.15)

Geographic Safety is the most important design decision:
  - Alternates in the SAME country as the disrupted supplier are penalised
  - Alternates in the SAME risk category are moderately penalised
  - Alternates in lower-risk countries score higher

This means a China disruption will surface European/Indian alternates
above other Chinese suppliers, even if those are nominally available.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Formula weights
W_CAPACITY   = 0.35
W_GEO_SAFETY = 0.30
W_LEAD_TIME  = 0.20
W_TRACK_REC  = 0.15

# Country-level manufacturing quality defaults (when no DB data)
COUNTRY_TRACK_RECORD = {
    "CH": 92, "DE": 90, "US": 88, "GB": 87, "JP": 90, "SE": 88, "FR": 85,
    "IN": 72, "CN": 68, "KR": 82, "SG": 85, "AU": 84, "CA": 86,
    "MX": 62, "BR": 58, "ZA": 55, "IL": 80, "BE": 86, "NL": 87,
    "FI": 88, "DK": 89, "NO": 88, "IE": 88, "IT": 80, "ES": 78,
}


def _capacity_score(capacity_fit: str) -> float:
    return {"high": 88.0, "medium": 55.0, "low": 25.0}.get(capacity_fit, 55.0)


def _lead_time_score(weeks: float) -> float:
    """Shorter lead time = higher score. Exponential decay."""
    if weeks <= 2:  return 95.0
    if weeks <= 4:  return 82.0
    if weeks <= 6:  return 68.0
    if weeks <= 8:  return 54.0
    if weeks <= 12: return 38.0
    return 20.0


def _geo_safety_score(
    candidate_country_code: str,
    disrupted_country_code: str,
    candidate_risk_score: float,
    disrupted_risk_score: float,
    disrupted_risk_category: str,
) -> float:
    """
    Compute geographic safety score (0–100).

    Same country as disrupted supplier → heavy penalty (score capped at 20)
    Same risk category as disrupted → moderate penalty
    Lower-risk country → higher score
    """
    # Same country as disrupted supplier — very risky recommendation
    if candidate_country_code == disrupted_country_code:
        return 15.0

    # Base score: invert the candidate's country risk (lower risk = higher safety score)
    base_safety = 100.0 - candidate_risk_score

    # Penalise if in same risk category as disrupted supplier
    same_category_penalty = 0.0
    if disrupted_risk_category in ("critical", "high"):
        # If disrupted supplier is in a high-risk country, penalise other high-risk candidates
        if candidate_risk_score >= 50:
            same_category_penalty = 15.0

    return max(5.0, min(100.0, base_safety - same_category_penalty))


def _track_record_score(candidate, session) -> float:
    """
    Look up source credibility / manufacturing quality.
    Falls back to country-level default.
    """
    if candidate.track_record_score is not None:
        return candidate.track_record_score

    return float(COUNTRY_TRACK_RECORD.get(candidate.country_code, 60.0))


def _get_country_risk(country_code: str, session) -> tuple:
    """Returns (risk_score, risk_category) for a country code."""
    try:
        from module1.db.models import CountryRisk
        row = session.query(CountryRisk).filter_by(country_code=country_code).first()
        if row:
            return row.risk_score, row.risk_category
    except Exception:
        pass
    return 50.0, "moderate"


def score_candidate(
    candidate,
    disrupted_country_code: str,
    disrupted_risk_score: float,
    disrupted_risk_category: str,
    session,
) -> dict:
    """
    Score one alternate candidate. Returns scoring breakdown dict.
    """
    capacity   = _capacity_score(candidate.capacity_fit)
    lead_time  = _lead_time_score(candidate.lead_time_weeks)
    track_rec  = _track_record_score(candidate, session)

    cand_risk, cand_risk_cat = _get_country_risk(candidate.country_code, session)

    geo_safety = _geo_safety_score(
        candidate_country_code=candidate.country_code,
        disrupted_country_code=disrupted_country_code,
        candidate_risk_score=cand_risk,
        disrupted_risk_score=disrupted_risk_score,
        disrupted_risk_category=disrupted_risk_category,
    )

    total = (
        capacity   * W_CAPACITY   +
        geo_safety * W_GEO_SAFETY +
        lead_time  * W_LEAD_TIME  +
        track_rec  * W_TRACK_REC
    )
    total = round(min(100.0, max(0.0, total)), 2)

    return {
        "candidate":        candidate,
        "alt_score":        total,
        "capacity_score":   round(capacity, 2),
        "geo_safety_score": round(geo_safety, 2),
        "lead_time_score":  round(lead_time, 2),
        "track_rec_score":  round(track_rec, 2),
        "country_risk":     round(cand_risk, 1),
        "country_risk_cat": cand_risk_cat,
    }


def rank_candidates(
    candidates: list,
    disrupted_supplier,
    disrupted_risk_score: float,
    disrupted_risk_category: str,
    session,
    top_n: int = 5,
) -> list:
    """
    Score and rank all candidates. Returns top_n sorted by alt_score descending.
    """
    if not candidates:
        return []

    disrupted_country = disrupted_supplier.country_code or "XX"

    scored = [
        score_candidate(
            c, disrupted_country,
            disrupted_risk_score, disrupted_risk_category,
            session,
        )
        for c in candidates
    ]

    # Sort by total score descending
    scored.sort(key=lambda x: x["alt_score"], reverse=True)

    top = scored[:top_n]

    for i, entry in enumerate(top, 1):
        logger.debug(
            f"    #{i} {entry['candidate'].name} ({entry['candidate'].country_code}) "
            f"score={entry['alt_score']} "
            f"[cap={entry['capacity_score']:.0f} geo={entry['geo_safety_score']:.0f} "
            f"lt={entry['lead_time_score']:.0f} tr={entry['track_rec_score']:.0f}]"
        )

    return top
