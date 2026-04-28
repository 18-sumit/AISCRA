"""
module2/stages/stage0_gemini.py
────────────────────────────────
Stage 0: Gemini supply chain impact screening for Track B (hot_news) articles.

Uses the new google-genai SDK (google-generativeai is deprecated).
Install: pip install google-genai

Rate limits (free tier):
  gemini-2.0-flash-lite: 30 req/min, 1500 req/day  ← we use this
  gemini-2.0-flash:      15 req/min, 1500 req/day
"""

import json
import logging
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

from gemini_api_utils import is_quota_error, rotate_api_key

BATCH_SIZE   = 10
BATCH_DELAY  = 5.0
REQUEST_DELAY = 2.5
MAX_RETRIES  = 3
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# Raised when the daily quota is gone — signals caller to abort Stage 0
class DailyQuotaExhausted(Exception):
    pass

# ─────────────────────────────────────────────────────────────────────────────
#  Gemini client — lazy init (new google-genai SDK) with fallback keys
# ─────────────────────────────────────────────────────────────────────────────
_client = None
_current_api_key = None

def _get_client(force_key=None):
    global _client, _current_api_key
    if force_key is not None:
        # Force switch to a different key
        _current_api_key = force_key
        _client = None
    
    if _client is None:
        try:
            from google import genai
            from gemini_api_utils import get_all_api_keys
            if _current_api_key is None:
                keys = get_all_api_keys()
                _current_api_key = keys[0] if keys else None
            if not _current_api_key:
                raise ValueError("No Gemini API keys found. Set GOOGLE_API_KEY, GOOGLE_API_KEY2-5, or GEMINI_KEY in .env")
            _client = genai.Client(api_key=_current_api_key)
            logger.info(f"Gemini client initialised with API key ({GEMINI_MODEL})")
        except ImportError:
            raise ImportError("google-genai not installed. Run: pip install google-genai")
    return _client


def _parse_retry_delay(error_str: str) -> float:
    match = re.search(r"retry[^\d]*(\d+)[\.\d]*s", str(error_str), re.IGNORECASE)
    if match:
        return float(match.group(1)) + 2.0
    return 60.0


def _is_daily_quota_exhausted(error_str: str) -> bool:
    """
    Daily quota errors have 'PerDay' in the quotaId AND 'limit: 0'.
    Per-minute errors have 'PerMinute' — those are worth retrying.
    """
    return "PerDay" in error_str and "limit: 0" in error_str


# ─────────────────────────────────────────────────────────────────────────────
#  Single article screening with retry
# ─────────────────────────────────────────────────────────────────────────────

def screen_article(article, system_prompt: str) -> Optional[dict]:
    global _client, _current_api_key
    
    for attempt in range(MAX_RETRIES):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            client = _get_client()
            body = (article.body or article.summary or "")[:3200]

            prompt = f"""{system_prompt}

ARTICLE HEADLINE: {article.headline}

ARTICLE BODY: {body}

Respond with this exact JSON structure and nothing else:
{{
  "is_supply_chain_risk": true or false,
  "plausibility": "high" or "medium" or "low",
  "confidence": 0.0 to 1.0,
  "affected_commodities": ["list of commodities at risk"],
  "affected_suppliers": ["supplier names from the profile that could be impacted"],
  "impact_chain": "step-by-step explanation of how this event reaches the supply chain",
  "time_horizon": "immediate" or "weeks" or "months"
}}"""

            from google.genai import types
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )

            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            parsed = json.loads(raw)
            if "is_supply_chain_risk" not in parsed:
                return None
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Gemini non-JSON for article {article.id}: {e}")
            return None

        except Exception as e:
            err_str = str(e)
            
            # Check if quota/token exhausted
            if is_quota_error(e):
                if _is_daily_quota_exhausted(err_str):
                    # Try fallback key
                    try:
                        fallback_key = rotate_api_key(_current_api_key or "")
                        if fallback_key != _current_api_key:
                            logger.warning(f"Daily quota exhausted for current key, switching to fallback key")
                            _get_client(force_key=fallback_key)
                            # Retry with new key
                            continue
                    except ValueError:
                        # No fallback keys available
                        pass
                    
                    raise DailyQuotaExhausted(
                        f"Daily Gemini quota exhausted for {GEMINI_MODEL}. "
                        f"Resets at midnight Pacific. Stage 0 will skip remaining hot_news articles."
                    )
                
                # Per-minute rate limit — wait and retry
                wait = _parse_retry_delay(err_str)
                logger.warning(
                    f"Rate limit hit for article {article.id} "
                    f"(attempt {attempt+1}/{MAX_RETRIES}) — waiting {wait:.0f}s"
                )
                time.sleep(wait)
                continue
            else:
                logger.error(f"Gemini API error for article {article.id}: {e}")
                return None

    logger.error(f"Article {article.id}: all {MAX_RETRIES} retries exhausted")
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Batch processor
# ─────────────────────────────────────────────────────────────────────────────

def run_stage0(session, profile) -> dict:
    from module1.db.models import Article

    unscreened = (
        session.query(Article)
        .filter_by(fetch_type="hot_news", gemini_screened=False)
        .order_by(Article.fetched_at.desc())
        .all()
    )

    if not unscreened:
        logger.info("Stage 0: No unscreened hot_news articles")
        return {"screened": 0, "risks": 0, "skipped": 0}

    logger.info(f"Stage 0: {len(unscreened)} articles to screen with {GEMINI_MODEL}")
    logger.info(f"  Estimated time: ~{len(unscreened) * REQUEST_DELAY / 60:.1f} minutes")

    system_prompt = profile.build_stage0_system_prompt()
    stats = {"screened": 0, "risks": 0, "skipped": 0, "errors": 0}
    batches = [unscreened[i:i+BATCH_SIZE] for i in range(0, len(unscreened), BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        logger.info(f"  Stage 0 batch {batch_idx+1}/{len(batches)} ({len(batch)} articles)")

        for article in batch:
            try:
                result = screen_article(article, system_prompt)
            except DailyQuotaExhausted as e:
                logger.warning(f"⚠ {e}")
                logger.warning(
                    f"Stage 0 aborted after {stats['screened']} articles. "
                    f"Remaining {len(unscreened) - stats['screened']} hot_news articles "
                    f"will be screened on next run once quota resets. "
                    f"Continuing with Track A articles now."
                )
                session.commit()
                stats["skipped"] = len(unscreened) - stats["screened"]
                return stats

            if result is None:
                article.gemini_screened = True
                article.is_supply_chain_risk = False
                stats["errors"] += 1
            else:
                is_risk = bool(result.get("is_supply_chain_risk", False))
                article.gemini_screened = True
                article.is_supply_chain_risk = is_risk
                article.gemini_plausibility = result.get("plausibility")
                article.gemini_confidence = float(result.get("confidence", 0.0))
                article.time_horizon = result.get("time_horizon")

                if is_risk:
                    article.is_indirect_risk = True
                    article.impact_chain = result.get("impact_chain")
                    article.affected_commodities_json = json.dumps(
                        result.get("affected_commodities", [])
                    )
                    article.affected_suppliers_json = json.dumps(
                        result.get("affected_suppliers", [])
                    )
                    stats["risks"] += 1
                    logger.info(
                        f"    ✓ RISK [{article.gemini_plausibility}]: "
                        f"{article.headline[:60]} "
                        f"(conf={article.gemini_confidence:.2f})"
                    )

            stats["screened"] += 1
            time.sleep(REQUEST_DELAY)

        session.commit()

        if batch_idx < len(batches) - 1:
            logger.debug(f"  Batch complete — waiting {BATCH_DELAY}s")
            time.sleep(BATCH_DELAY)

    logger.info(
        f"Stage 0 complete: {stats['screened']} screened, "
        f"{stats['risks']} risks found, {stats['errors']} errors"
    )
    return stats


