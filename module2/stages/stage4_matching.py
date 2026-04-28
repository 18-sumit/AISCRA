"""
module2/stages/stage4_matching.py
───────────────────────────────────
Stage 4: Entity-Supplier Matching.

Connects extracted entity names (from Stage 2) to the company's supplier
database using three methods tried in order:

  1. Exact match — string equality between entity and supplier name/alias
  2. Fuzzy match — RapidFuzz token_set_ratio > 88 threshold
  3. Semantic match — cosine similarity between sentence-BERT embeddings > 0.82

For indirect risk articles (from Stage 0), Gemini's affected_suppliers list
is used as an additional high-confidence matching signal.

Country matching: also checks if extracted GPE entities match supplier countries
(enables "China export ban → affects all Chinese suppliers" logic).

Returns: list of MatchedSupplier dicts, each linking an entity to a supplier
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 88    # RapidFuzz token_set_ratio
SEMANTIC_THRESHOLD = 0.82

@dataclass
class MatchedSupplier:
    supplier_id: int
    supplier_name: str
    commodity: str
    country_code: str
    tier: int
    criticality: str
    dependency_weight: float
    match_method: str       # 'exact' | 'alias' | 'fuzzy' | 'semantic' | 'stage0' | 'country'
    match_score: float      # 0.0–1.0
    matched_entity: str     # the raw entity text that triggered the match


# ─────────────────────────────────────────────────────────────────────────────
#  RapidFuzz (lazy import)
# ─────────────────────────────────────────────────────────────────────────────

_rapidfuzz_available = None

def _fuzzy_ratio(a: str, b: str) -> float:
    global _rapidfuzz_available
    if _rapidfuzz_available is False:
        return 0.0
    try:
        from rapidfuzz import fuzz
        _rapidfuzz_available = True
        return fuzz.token_set_ratio(a, b)
    except ImportError:
        if _rapidfuzz_available is None:
            logger.warning("rapidfuzz not installed — fuzzy matching disabled. Run: pip install rapidfuzz")
        _rapidfuzz_available = False
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  Semantic matching (sentence-BERT)
# ─────────────────────────────────────────────────────────────────────────────

_encoder = None
_encoder_available = None

def _get_encoder():
    global _encoder, _encoder_available
    if _encoder_available is False:
        return None
    if _encoder is not None:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
        _encoder_available = True
        return _encoder
    except Exception as e:
        logger.warning(f"sentence-transformers not available: {e}")
        _encoder_available = False
        return None

def _cosine(a, b) -> float:
    import numpy as np
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0

def _semantic_similarity(entity: str, supplier_name: str) -> float:
    encoder = _get_encoder()
    if encoder is None:
        return 0.0
    try:
        vecs = encoder.encode([entity, supplier_name], normalize_embeddings=True)
        return _cosine(vecs[0], vecs[1])
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  Core matching logic
# ─────────────────────────────────────────────────────────────────────────────

def _match_entity_to_suppliers(entity_text: str, suppliers: list) -> list:
    """
    Try to match one entity text against all suppliers.
    Returns list of MatchedSupplier (may be multiple matches).
    """
    entity_lower = entity_text.lower().strip()
    matches = []

    for supplier in suppliers:
        # Method 1: Exact match against name
        if entity_lower == supplier.name.lower():
            matches.append(MatchedSupplier(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                commodity=supplier.commodity or "",
                country_code=supplier.country_code or "",
                tier=supplier.tier,
                criticality=supplier.criticality or "medium",
                dependency_weight=supplier.dependency_weight or 0.0,
                match_method="exact",
                match_score=1.0,
                matched_entity=entity_text,
            ))
            continue

        # Method 2: Alias match
        for alias in supplier.get_aliases():
            if entity_lower == alias.lower():
                matches.append(MatchedSupplier(
                    supplier_id=supplier.id,
                    supplier_name=supplier.name,
                    commodity=supplier.commodity or "",
                    country_code=supplier.country_code or "",
                    tier=supplier.tier,
                    criticality=supplier.criticality or "medium",
                    dependency_weight=supplier.dependency_weight or 0.0,
                    match_method="alias",
                    match_score=0.95,
                    matched_entity=entity_text,
                ))
                break
        else:
            # Method 3: Fuzzy match
            best_ratio = 0.0
            for name in supplier.all_names():
                ratio = _fuzzy_ratio(entity_lower, name.lower())
                best_ratio = max(best_ratio, ratio)

            if best_ratio >= FUZZY_THRESHOLD:
                matches.append(MatchedSupplier(
                    supplier_id=supplier.id,
                    supplier_name=supplier.name,
                    commodity=supplier.commodity or "",
                    country_code=supplier.country_code or "",
                    tier=supplier.tier,
                    criticality=supplier.criticality or "medium",
                    dependency_weight=supplier.dependency_weight or 0.0,
                    match_method="fuzzy",
                    match_score=best_ratio / 100.0,
                    matched_entity=entity_text,
                ))
                continue

            # Method 4: Semantic similarity
            sim = _semantic_similarity(entity_lower, supplier.name.lower())
            if sim >= SEMANTIC_THRESHOLD:
                matches.append(MatchedSupplier(
                    supplier_id=supplier.id,
                    supplier_name=supplier.name,
                    commodity=supplier.commodity or "",
                    country_code=supplier.country_code or "",
                    tier=supplier.tier,
                    criticality=supplier.criticality or "medium",
                    dependency_weight=supplier.dependency_weight or 0.0,
                    match_method="semantic",
                    match_score=sim,
                    matched_entity=entity_text,
                ))

    return matches


def _match_country_to_suppliers(country_text: str, suppliers: list) -> list:
    """
    Match a country entity to all suppliers from that country.
    Enables "China trade war → all Chinese suppliers affected" logic.
    Only for high-confidence country matches (exact name match).
    """
    COUNTRY_MAP = {
        "china": "CN", "india": "IN", "germany": "DE", "switzerland": "CH",
        "usa": "US", "united states": "US", "uk": "GB", "united kingdom": "GB",
        "france": "FR", "japan": "JP", "south korea": "KR", "korea": "KR",
        "russia": "RU", "iran": "IR", "taiwan": "TW", "israel": "IL",
        "saudi arabia": "SA", "mexico": "MX", "brazil": "BR",
    }

    country_lower = country_text.lower()
    country_code = COUNTRY_MAP.get(country_lower)
    if not country_code:
        return []

    matches = []
    for supplier in suppliers:
        if supplier.country_code == country_code:
            matches.append(MatchedSupplier(
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                commodity=supplier.commodity or "",
                country_code=supplier.country_code or "",
                tier=supplier.tier,
                criticality=supplier.criticality or "medium",
                dependency_weight=supplier.dependency_weight or 0.0,
                match_method="country",
                match_score=0.70,  # lower confidence — geographic, not direct
                matched_entity=country_text,
            ))
    return matches


# ─────────────────────────────────────────────────────────────────────────────
#  Main Stage 4 runner
# ─────────────────────────────────────────────────────────────────────────────

def run_stage4(article, entities: list, suppliers: list) -> list:
    """
    Match extracted entities to suppliers.

    Args:
        article:   Article ORM object
        entities:  list of ExtractedEntity from Stage 2
        suppliers: list of Supplier ORM objects (active suppliers)

    Returns:
        list of MatchedSupplier, deduplicated by supplier_id
        (highest-confidence match per supplier wins)
    """
    all_matches = []

    # Match ORG and COMMODITY entities to suppliers
    for entity in entities:
        if entity.entity_type in ("ORG", "COMMODITY", "COMPANY"):
            matches = _match_entity_to_suppliers(entity.text, suppliers)
            # Mark Stage 0 entities with higher confidence
            for m in matches:
                if entity.source == "stage0":
                    m.match_method = "stage0"
                    m.match_score = min(m.match_score + 0.1, 1.0)
            all_matches.extend(matches)

        elif entity.entity_type == "GPE":
            # Country matching — adds geographic exposure signal
            country_matches = _match_country_to_suppliers(entity.text, suppliers)
            all_matches.extend(country_matches)

    # Deduplicate: keep highest-confidence match per supplier_id
    best_by_supplier: dict = {}
    for m in all_matches:
        if m.supplier_id not in best_by_supplier:
            best_by_supplier[m.supplier_id] = m
        elif m.match_score > best_by_supplier[m.supplier_id].match_score:
            best_by_supplier[m.supplier_id] = m

    result = list(best_by_supplier.values())

    logger.debug(
        f"  Stage 4: {len(result)} suppliers matched for article {article.id} "
        f"({[m.supplier_name for m in result]})"
    )

    return result
