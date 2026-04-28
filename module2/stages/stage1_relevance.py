"""
module2/stages/stage1_relevance.py
────────────────────────────────────
Stage 1: Relevance classification.

Determines whether an article is genuinely supply-chain-relevant.

Strategy (tried in order):
  1. BART zero-shot (facebook/bart-large-mnli) — no training data needed, ~1.6GB
  2. Gemini fallback — if transformers not available or model not downloaded

Track A articles that passed the keyword pre-filter are assumed relevant
(is_relevant_prefilter=True) and skip the expensive model call.

Track B articles confirmed by Gemini Stage 0 (is_supply_chain_risk=True)
are also already confirmed relevant — they skip Stage 1 too.

Stage 1 only meaningfully runs on:
  - Track A articles where is_relevant_prefilter=False (keyword didn't match but
    came through RSS/GDELT) — these need a second opinion
  - Any article that somehow bypassed pre-filtering
"""

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.6  # probability above which article is classified as relevant

CANDIDATE_LABELS = [
    "supply chain disruption",
    "pharmaceutical manufacturing",
    "drug shortage",
    "trade restriction",
    "geopolitical risk to manufacturing",
    "shipping logistics problem",
    "factory shutdown",
    "regulatory enforcement action",
]

NOT_RELEVANT_LABELS = [
    "entertainment news",
    "sports",
    "celebrity gossip",
    "unrelated politics",
]


# ─────────────────────────────────────────────────────────────────────────────
#  BART zero-shot classifier (lazy load)
# ─────────────────────────────────────────────────────────────────────────────

_bart_pipeline = None
_bart_available = None


def _get_bart():
    global _bart_pipeline, _bart_available
    if _bart_available is False:
        return None
    if _bart_pipeline is not None:
        return _bart_pipeline

    try:
        from transformers import pipeline
        logger.info("Loading BART zero-shot classifier (first run downloads ~1.6GB)...")
        _bart_pipeline = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=-1,  # CPU
        )
        _bart_available = True
        logger.info("BART classifier loaded ✓")
        return _bart_pipeline
    except Exception as e:
        logger.warning(f"BART not available: {e} — will use Gemini fallback")
        _bart_available = False
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Gemini fallback classifier
# ─────────────────────────────────────────────────────────────────────────────

def _classify_with_gemini(text: str) -> float:
    """
    Use Gemini to classify relevance when BART is unavailable.
    Returns probability 0.0–1.0. Uses new google-genai SDK.
    """
    try:
        from google import genai
        from google.genai import types
        from gemini_api_utils import rotate_api_key, is_quota_error, get_all_api_keys
        
        keys = get_all_api_keys()
        api_key = keys[0] if keys else None
        if not api_key:
            return 0.5

        # Try with primary key, fallback to secondary if exhausted
        for attempt in range(2):
            try:
                client = genai.Client(api_key=api_key)

                prompt = f"""Is the following news article relevant to pharmaceutical supply chain risks?
Consider: drug shortages, API manufacturing disruptions, regulatory actions, trade restrictions,
shipping/logistics problems, geopolitical events affecting pharma supply chains.

Article: {text[:1000]}

Respond with ONLY a number between 0.0 and 1.0 representing relevance probability.
1.0 = definitely supply chain relevant, 0.0 = completely irrelevant."""

                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite-preview",
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=10),
                )
                score = float(response.text.strip())
                return max(0.0, min(1.0, score))
            
            except Exception as e:
                if is_quota_error(e) and attempt == 0:
                    # Try fallback key
                    try:
                        api_key = rotate_api_key(api_key)
                        logger.warning(f"Quota exhausted, trying fallback key for relevance check")
                        continue
                    except ValueError:
                        logger.error(f"Gemini relevance fallback failed and no more keys available: {e}")
                        return 0.5
                else:
                    logger.error(f"Gemini relevance fallback failed: {e}")
                    return 0.5

    except Exception as e:
        logger.error(f"Gemini relevance fallback failed: {e}")
        return 0.5


# ─────────────────────────────────────────────────────────────────────────────
#  Main classification function
# ─────────────────────────────────────────────────────────────────────────────

def classify_relevance(article) -> tuple:
    """
    Classify whether an article is supply-chain-relevant.

    Fast-path shortcuts:
      - Track B confirmed by Gemini Stage 0 → always relevant
      - Track A with keyword pre-filter match → always relevant

    Returns:
        (is_relevant: bool, confidence: float, method: str)
    """
    # Fast-path: already confirmed relevant
    if article.is_supply_chain_risk is True:
        return True, 1.0, "stage0_confirmed"

    if article.fetch_type == "targeted" and article.is_relevant_prefilter:
        return True, 0.9, "keyword_prefilter"

    # Build text input
    text = article.headline or ""
    if article.summary:
        text += " " + article.summary
    if article.body:
        text += " " + article.body[:500]
    text = text.strip()

    if not text:
        return False, 0.0, "empty_text"

    # Try BART zero-shot
    bart = _get_bart()
    if bart is not None:
        try:
            result = bart(
                text[:1024],
                candidate_labels=CANDIDATE_LABELS,
                multi_label=False,
            )
            # Top score across all supply-chain-relevant labels
            top_score = result["scores"][0] if result["scores"] else 0.0
            is_relevant = top_score >= RELEVANCE_THRESHOLD
            return is_relevant, top_score, "bart_zero_shot"
        except Exception as e:
            logger.error(f"BART classification failed: {e}")

    # Gemini fallback
    score = _classify_with_gemini(text)
    return score >= RELEVANCE_THRESHOLD, score, "gemini_fallback"


def run_stage1(articles: list) -> list:
    """
    Run Stage 1 on a list of Article ORM objects.
    Returns subset that passed relevance classification, with confidence scores attached.
    """
    passed = []
    for article in articles:
        is_relevant, confidence, method = classify_relevance(article)

        logger.debug(
            f"  Stage 1 [{method}] {confidence:.2f} "
            f"{'✓' if is_relevant else '✗'} — {article.headline[:60]}"
        )

        if is_relevant:
            # Store confidence on article object for Stage 5 scoring
            article._stage1_confidence = confidence
            article._stage1_method = method
            passed.append(article)

    logger.info(f"Stage 1: {len(passed)}/{len(articles)} articles passed relevance filter")
    return passed
