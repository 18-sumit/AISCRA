"""
module3/rationale.py
─────────────────────
Generates concise procurement rationale for each recommended alternate.

For direct risks:
  "Aurobindo Pharma is recommended as a primary alternate for Cardiovascular APIs
   given its established ARB portfolio and geographically diversified Indian
   manufacturing base, with an estimated 2–3 week qualification lead time."

For indirect risks, prepends one sentence summarising the propagation pathway:
  "The Red Sea shipping disruption is expected to raise solvent costs within
   4–6 weeks, placing Gujarat Alkalies at risk. [Alternate rationale...]"

Falls back to a template-generated rationale if the LLM is unavailable,
so Module 3 always produces output regardless of API key status.
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

_client = None

def _get_client(force_key=None):
    """
    Get Gemini client, optionally forcing a specific API key.
    """
    try:
        from google import genai
        from gemini_api_utils import get_all_api_keys
        if force_key:
            api_key = force_key
        else:
            keys = get_all_api_keys()
            api_key = keys[0] if keys else None
        if not api_key:
            return None, None
        return genai.Client(api_key=api_key), api_key
    except Exception:
        return None, None


def _template_rationale(scored_entry: dict, disrupted_name: str, commodity: str) -> str:
    """
    Fallback: generate rationale from structured data without an LLM.
    Always produces a reasonable output.
    """
    c = scored_entry["candidate"]
    geo_desc = "geographically diversified" if scored_entry["geo_safety_score"] > 70 else "regionally available"
    cap_desc = c.capacity_fit
    lt = c.lead_time_weeks
    lt_str = f"{int(lt)}–{int(lt)+2} weeks" if lt < 12 else f"{int(lt)} weeks"

    return (
        f"{c.name} is a recommended alternate for {commodity} sourcing, "
        f"offering {cap_desc} capacity from a {geo_desc} {c.country} base "
        f"with an estimated lead time of {lt_str}. "
        f"Geographic diversification away from the disrupted supplier "
        f"({disrupted_name}) reduces concentrated sourcing risk."
    )


def generate_rationale(
    scored_entry: dict,
    disrupted_supplier_name: str,
    commodity: str,
    impact_chain: str = None,
    is_indirect: bool = False,
    rank: int = 1,
) -> str:
    """
    Generate a 2–3 sentence procurement rationale for one alternate.

    Args:
        scored_entry:           Scored candidate dict from ranker
        disrupted_supplier_name: Name of the disrupted supplier
        commodity:              Commodity at risk
        impact_chain:           Propagation pathway text (for indirect risks)
        is_indirect:            Whether this is an indirect risk event
        rank:                   Rank position (1 = top recommendation)

    Returns:
        Rationale string
    """
    from gemini_api_utils import rotate_api_key, is_quota_error, get_all_api_keys
    
    keys = get_all_api_keys()
    api_key = keys[0] if keys else None
    if not api_key:
        return _template_rationale(scored_entry, disrupted_supplier_name, commodity)

    c = scored_entry["candidate"]

    # Build context prefix for indirect risks
    indirect_context = ""
    if is_indirect and impact_chain:
        # Truncate impact chain to one sentence for the prompt
        first_sentence = impact_chain.split("→")[0].strip() if "→" in impact_chain else impact_chain[:200]
        indirect_context = f"This is an indirect exposure: {first_sentence}. "

    prompt = f"""Write a 2-sentence procurement recommendation for the following alternate supplier.
Be specific and professional. Do not use marketing language.

Context: {disrupted_supplier_name} ({commodity}) has been flagged as a supply chain risk.
{indirect_context}
Alternate supplier #{rank}:
  Name: {c.name}
  Country: {c.country} (country risk score: {scored_entry['country_risk']:.0f}/100)
  Capacity fit: {c.capacity_fit}
  Lead time: {c.lead_time_weeks} weeks
  Alternate score: {scored_entry['alt_score']:.0f}/100
  Geographic safety score: {scored_entry['geo_safety_score']:.0f}/100 (higher = safer diversification)
  {f'Notes: {c.notes}' if c.notes else ''}

Write exactly 2 sentences. First: why this supplier is recommended.
Second: any qualification or risk consideration.
No bullet points. No preamble."""

    # Try with primary key, fallback to secondary if exhausted
    for attempt in range(2):
        try:
            from google.genai import types
            client, used_key = _get_client(api_key)
            if client is None:
                return _template_rationale(scored_entry, disrupted_supplier_name, commodity)
                
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=150,
                ),
            )
            text = response.text.strip()
            # Prepend indirect context summary if needed
            if is_indirect and impact_chain and "→" in impact_chain:
                chain_summary = " → ".join(
                    p.strip() for p in impact_chain.split("→")[:3]
                )
                return f"Indirect exposure pathway: {chain_summary}. {text}"
            return text

        except Exception as e:
            if is_quota_error(e) and attempt == 0:
                logger.debug(f"Quota exhausted for {api_key[:20]}..., trying fallback")
                api_key = rotate_api_key(api_key)
                continue
            else:
                logger.debug(f"Rationale LLM failed for {c.name}: {e} — using template")
                return _template_rationale(scored_entry, disrupted_supplier_name, commodity)


def generate_all_rationales(
    top_scored: list,
    disrupted_supplier_name: str,
    commodity: str,
    impact_chain: str = None,
    is_indirect: bool = False,
    delay: float = 1.5,
) -> list:
    """
    Generate rationales for top-N alternates with rate limit delay between calls.
    Returns list of rationale strings, same order as top_scored.
    """
    rationales = []
    for i, entry in enumerate(top_scored, 1):
        rationale = generate_rationale(
            entry,
            disrupted_supplier_name=disrupted_supplier_name,
            commodity=commodity,
            impact_chain=impact_chain,
            is_indirect=is_indirect,
            rank=i,
        )
        rationales.append(rationale)
        if i < len(top_scored):
            time.sleep(delay)

    return rationales
