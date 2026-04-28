"""
module3/data_sources.py
────────────────────────
Loads candidate alternate suppliers from two sources:

1. company_profile.yaml → alternates section (pre-seeded by commodity)
2. The suppliers table itself — lower-tier or secondary suppliers that
   supply the same commodity can serve as alternates for a disrupted primary

Returns a unified list of AlternateCandidate dicts for the ranker.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AlternateCandidate:
    name: str
    country: str
    country_code: str
    capacity_fit: str        # 'high' | 'medium' | 'low'
    lead_time_weeks: float
    commodity: str
    source: str              # 'yaml_seed' | 'supplier_db'
    notes: str = ""
    track_record_score: Optional[float] = None  # 0–100, None = use country default


def _capacity_to_score(capacity_fit: str) -> float:
    return {"high": 85.0, "medium": 55.0, "low": 25.0}.get(capacity_fit, 55.0)


def _lead_time_to_score(weeks: float) -> float:
    """Shorter lead time → higher score. Normalised 0–100."""
    if weeks <= 2:   return 95.0
    if weeks <= 4:   return 80.0
    if weeks <= 6:   return 65.0
    if weeks <= 8:   return 50.0
    if weeks <= 12:  return 35.0
    return 20.0


def load_yaml_alternates(profile, disrupted_commodity: str) -> list:
    """
    Load pre-seeded alternates from company_profile.yaml.
    Matches on commodity name (case-insensitive partial match).
    """
    candidates = []
    commodity_lower = disrupted_commodity.lower()

    for group in profile.alternates:
        # Match if any word from the disrupted commodity appears in the group name
        group_lower = group.for_commodity.lower()
        commodity_words = set(commodity_lower.split()) - {"api", "apis", "and", "the", "of"}
        group_words = set(group_lower.split()) - {"api", "apis", "and", "the", "of"}

        if not (commodity_words & group_words):
            continue

        for alt in group.suppliers:
            candidates.append(AlternateCandidate(
                name=alt.name,
                country=alt.country,
                country_code=alt.country_code,
                capacity_fit=alt.capacity_fit,
                lead_time_weeks=float(alt.lead_time_weeks),
                commodity=group.for_commodity,
                source="yaml_seed",
                notes=alt.notes,
            ))

    logger.debug(f"  YAML alternates for '{disrupted_commodity}': {len(candidates)}")
    return candidates


def load_db_alternates(disrupted_supplier_id: int, disrupted_commodity: str, session) -> list:
    """
    Find other suppliers in the DB that supply a similar commodity.
    These can serve as alternates — especially Tier-2 suppliers stepping up.
    Excludes the disrupted supplier itself.
    """
    from module1.db.models import Supplier

    commodity_words = set(
        disrupted_commodity.lower().split()
    ) - {"api", "apis", "and", "the", "of", "for", "pharmaceutical"}

    all_suppliers = (
        session.query(Supplier)
        .filter(Supplier.active == True)
        .filter(Supplier.id != disrupted_supplier_id)
        .all()
    )

    candidates = []
    for s in all_suppliers:
        if not s.commodity:
            continue
        supplier_words = set(
            s.commodity.lower().split()
        ) - {"api", "apis", "and", "the", "of", "for", "pharmaceutical"}

        # At least 2 words in common → same commodity family
        if len(commodity_words & supplier_words) >= 2:
            # Estimate capacity: Tier 1 = high, Tier 2 = medium, Tier 3 = low
            capacity = {1: "high", 2: "medium", 3: "low"}.get(s.tier, "medium")
            # Lead time estimate: Tier 1 = 2–4w, Tier 2 = 4–8w, Tier 3 = 8–12w
            lead_time = {1: 3.0, 2: 6.0, 3: 10.0}.get(s.tier, 6.0)

            candidates.append(AlternateCandidate(
                name=s.name,
                country=s.country or "",
                country_code=s.country_code or "XX",
                capacity_fit=capacity,
                lead_time_weeks=lead_time,
                commodity=s.commodity,
                source="supplier_db",
                notes=s.notes or "",
                track_record_score=None,
            ))

    logger.debug(f"  DB alternates for '{disrupted_commodity}': {len(candidates)}")
    return candidates


def get_all_candidates(
    disrupted_supplier_id: int,
    disrupted_commodity: str,
    profile,
    session,
) -> list:
    """
    Combine YAML seeds + DB alternates, deduplicated by name.
    YAML seeds take priority over DB entries for the same supplier.
    """
    yaml_candidates = load_yaml_alternates(profile, disrupted_commodity)
    db_candidates   = load_db_alternates(disrupted_supplier_id, disrupted_commodity, session)

    seen_names = {c.name.lower() for c in yaml_candidates}
    unique_db = [c for c in db_candidates if c.name.lower() not in seen_names]

    all_candidates = yaml_candidates + unique_db
    logger.info(f"  Total candidates: {len(all_candidates)} ({len(yaml_candidates)} YAML, {len(unique_db)} DB)")
    return all_candidates
