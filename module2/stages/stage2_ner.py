"""
module2/stages/stage2_ner.py
──────────────────────────────
Stage 2: Named Entity Recognition — two-tier approach.

Tier 1: spaCy en_core_web_lg (fast, offline, ~750MB)
  - Extracts: ORG, GPE, PRODUCT, EVENT entity types
  - ~5ms per article on CPU

Tier 2: Gemini function calling (triggered when Tier 1 returns nothing useful)
  - Resolves ambiguities ('Apple' = company vs fruit)
  - Extracts: company_name, commodity, country, event_type, disruption_severity

For articles confirmed as indirect risks by Stage 0:
  - Gemini's affected_suppliers and affected_commodities are used directly
    as additional entity signals even if the article text never names them

Output: list of ExtractedEntity dicts attached to the article
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# spaCy entity types we care about
RELEVANT_ENTITY_TYPES = {"ORG", "GPE", "PRODUCT", "EVENT", "FAC", "NORP"}

# Minimum entity text length (filter out single letters, etc.)
MIN_ENTITY_LEN = 3


@dataclass
class ExtractedEntity:
    text: str
    entity_type: str      # ORG | GPE | PRODUCT | EVENT | COMMODITY | COMPANY
    source: str           # 'spacy' | 'gemini' | 'stage0'
    confidence: float = 1.0
    normalized: Optional[str] = None  # cleaned version for matching


# ─────────────────────────────────────────────────────────────────────────────
#  Tier 1: spaCy
# ─────────────────────────────────────────────────────────────────────────────

_spacy_nlp = None
_spacy_available = None


def _get_spacy():
    global _spacy_nlp, _spacy_available
    if _spacy_available is False:
        return None
    if _spacy_nlp is not None:
        return _spacy_nlp

    try:
        import spacy
        try:
            _spacy_nlp = spacy.load("en_core_web_lg")
            logger.info("spaCy en_core_web_lg loaded ✓")
        except OSError:
            # Try smaller model
            try:
                _spacy_nlp = spacy.load("en_core_web_sm")
                logger.warning("spaCy: en_core_web_lg not found, using en_core_web_sm")
            except OSError:
                logger.warning(
                    "spaCy models not installed. Run: "
                    "python -m spacy download en_core_web_lg"
                )
                _spacy_available = False
                return None
        _spacy_available = True
        return _spacy_nlp
    except ImportError:
        logger.warning("spaCy not installed — skipping Tier 1 NER")
        _spacy_available = False
        return None


def _extract_with_spacy(text: str) -> list:
    """Run spaCy NER and return list of ExtractedEntity."""
    nlp = _get_spacy()
    if nlp is None:
        return []

    doc = nlp(text[:5000])  # spaCy has a token limit
    entities = []

    for ent in doc.ents:
        if ent.label_ not in RELEVANT_ENTITY_TYPES:
            continue
        if len(ent.text.strip()) < MIN_ENTITY_LEN:
            continue

        entities.append(ExtractedEntity(
            text=ent.text.strip(),
            entity_type=ent.label_,
            source="spacy",
            confidence=0.85,
            normalized=ent.text.strip().lower(),
        ))

    return entities


# ─────────────────────────────────────────────────────────────────────────────
#  Tier 2: Gemini NER
# ─────────────────────────────────────────────────────────────────────────────

def _extract_with_gemini(article) -> list:
    """
    Use Gemini to extract supply-chain-relevant entities.
    Uses new google-genai SDK with fallback key support.
    """
    try:
        from google import genai
        from google.genai import types
        from gemini_api_utils import rotate_api_key, is_quota_error, get_all_api_keys
        
        keys = get_all_api_keys()
        api_key = keys[0] if keys else None
        if not api_key:
            return []

        # Try with primary key, fallback to secondary if exhausted
        for attempt in range(2):
            try:
                client = genai.Client(api_key=api_key)
                text = article.headline + ". " + (article.body or article.summary or "")[:1000]

                prompt = f"""Extract supply-chain-relevant entities from this article.
Return ONLY valid JSON, no other text:

{{
  "companies": ["list of company or organization names"],
  "commodities": ["list of commodities, chemicals, drugs, or materials"],
  "countries": ["list of country names"],
  "event_type": "one of: sanctions|bankruptcy|shutdown|strike|tariff|shipping_delay|natural_disaster|regulatory_action|shortage|conflict|other",
  "disruption_severity": "one of: critical|high|medium|low|none"
}}

Article: {text}"""

                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite-preview",
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=256),
                )

                raw = response.text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                parsed = json.loads(raw)
                entities = []

                for company in parsed.get("companies", []):
                    if company and len(company) >= MIN_ENTITY_LEN:
                        entities.append(ExtractedEntity(
                            text=company, entity_type="ORG", source="gemini",
                            confidence=0.90, normalized=company.lower()
                        ))

                for commodity in parsed.get("commodities", []):
                    if commodity and len(commodity) >= MIN_ENTITY_LEN:
                        entities.append(ExtractedEntity(
                            text=commodity, entity_type="COMMODITY", source="gemini",
                            confidence=0.85, normalized=commodity.lower()
                        ))

                for country in parsed.get("countries", []):
                    if country and len(country) >= MIN_ENTITY_LEN:
                        entities.append(ExtractedEntity(
                            text=country, entity_type="GPE", source="gemini",
                            confidence=0.90, normalized=country.lower()
                        ))

                article._gemini_event_type = parsed.get("event_type", "other")
                article._gemini_severity = parsed.get("disruption_severity", "none")

                return entities
            
            except Exception as e:
                if is_quota_error(e) and attempt == 0:
                    logger.warning(f"Quota exhausted for {api_key[:20]}..., trying fallback key")
                    api_key = rotate_api_key(api_key)
                    continue
                else:
                    logger.error(f"Gemini NER failed for article {article.id}: {e}")
                    return []

    except ImportError as e:
        logger.error(f"Failed to import Gemini: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 0 supplement: extract entities from Gemini screening output
# ─────────────────────────────────────────────────────────────────────────────

def _extract_from_stage0(article) -> list:
    """
    For indirect risk articles, use Stage 0 Gemini output as entity signals.
    These are supplier and commodity names Gemini identified even though
    the article text never mentioned them.
    """
    entities = []

    for supplier_name in article.get_affected_suppliers():
        if supplier_name:
            entities.append(ExtractedEntity(
                text=supplier_name, entity_type="ORG", source="stage0",
                confidence=0.95, normalized=supplier_name.lower()
            ))

    for commodity in article.get_affected_commodities():
        if commodity:
            entities.append(ExtractedEntity(
                text=commodity, entity_type="COMMODITY", source="stage0",
                confidence=0.90, normalized=commodity.lower()
            ))

    return entities


# ─────────────────────────────────────────────────────────────────────────────
#  Main NER runner
# ─────────────────────────────────────────────────────────────────────────────

def run_stage2(article) -> list:
    """
    Extract named entities from one article using the two-tier approach.
    Augments with Stage 0 output for indirect risk articles.

    Returns: list of ExtractedEntity
    """
    text = article.headline + ". " + (article.body or article.summary or "")[:2000]

    # Tier 1: spaCy
    entities = _extract_with_spacy(text)
    useful = [e for e in entities if e.entity_type in {"ORG", "GPE"}]

    # Tier 2: Gemini — triggered if Tier 1 found nothing useful
    if not useful:
        logger.debug(f"  Stage 2 Tier 2 (Gemini) for article {article.id}")
        gemini_entities = _extract_with_gemini(article)
        entities.extend(gemini_entities)

    # Supplement with Stage 0 output (indirect risk articles)
    if article.is_indirect_risk:
        stage0_entities = _extract_from_stage0(article)
        entities.extend(stage0_entities)

    # Deduplicate by normalized text
    seen = set()
    deduped = []
    for e in entities:
        key = (e.normalized or e.text.lower(), e.entity_type)
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    logger.debug(
        f"  Stage 2: {len(deduped)} entities for article {article.id} "
        f"({len([e for e in deduped if e.source == 'spacy'])} spaCy, "
        f"{len([e for e in deduped if e.source == 'gemini'])} Gemini, "
        f"{len([e for e in deduped if e.source == 'stage0'])} Stage0)"
    )

    return deduped
