"""
module2/stages/stage3_severity.py
───────────────────────────────────
Stage 3: Sentiment and severity scoring.

Two models run and combine:

1. FinBERT (ProsusAI/finbert) — financial domain sentiment classifier
   Input: headline + first 3 sentences
   Output: positive / negative / neutral + confidence
   Falls back to keyword-based sentiment if model not available.

2. Rule-based event severity classifier
   Maps detected event types to severity bands (0–100):
     Natural disaster / facility destruction  → 85–100 (Critical)
     Sanctions / export ban / embargo         → 80–95  (Critical)
     Bankruptcy / plant shutdown              → 70–84  (High)
     Major strike / labor action              → 65–79  (High)
     Trade restriction / tariff increase      → 45–64  (Medium)
     Logistics delay / shipping disruption    → 35–49  (Medium)
     Political instability / civil unrest     → 20–40  (Low-Medium)
     Shortage warning / early signal          → 10–25  (Low)

Final severity score:
    (Rule_Base × 0.7) + (FinBERT_Negative_Confidence × 30)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Event type → severity band mapping
# ─────────────────────────────────────────────────────────────────────────────

EVENT_SEVERITY = {
    # Critical
    "natural_disaster":    (85, 100),
    "facility_fire":       (85, 100),
    "sanctions":           (80, 95),
    "export_ban":          (80, 95),
    "embargo":             (80, 95),
    "war":                 (80, 95),
    "conflict":            (70, 90),
    "bankruptcy":          (70, 84),
    "plant_shutdown":      (70, 84),
    "license_revocation":  (70, 84),
    "fda_warning":         (68, 82),
    # High
    "strike":              (65, 79),
    "labor_action":        (65, 79),
    "regulatory_action":   (55, 75),
    "import_alert":        (60, 78),
    "drug_recall":         (65, 80),
    # Medium
    "tariff":              (45, 64),
    "trade_restriction":   (45, 64),
    "shipping_delay":      (35, 49),
    "port_congestion":     (35, 49),
    "logistics_disruption":(35, 49),
    "energy_crisis":       (50, 70),
    "political_instability":(20, 45),
    "civil_unrest":        (20, 40),
    # Low
    "shortage_warning":    (10, 30),
    "price_increase":      (15, 35),
    "supply_tightness":    (10, 25),
    "other":               (15, 35),
    "none":                (5, 15),
}

# Keyword → event type mapping for rule-based detection
EVENT_KEYWORDS = {
    "natural_disaster": [
        "earthquake", "flood", "typhoon", "hurricane", "cyclone", "tsunami",
        "wildfire", "drought", "volcanic", "tornado", "storm"
    ],
    "facility_fire": [
        "plant fire", "factory fire", "explosion", "blast", "burned down",
        "facility fire", "manufacturing fire"
    ],
    "sanctions": [
        "sanctions", "sanctioned", "sanction", "blacklisted", "designated",
        "ofac", "eu sanctions", "us sanctions"
    ],
    "export_ban": [
        "export ban", "export restriction", "export control", "banned exports",
        "export halt", "export curb"
    ],
    "war": [
        "war", "invasion", "military attack", "airstrike", "bombing",
        "armed conflict", "military offensive"
    ],
    "conflict": [
        "conflict", "fighting", "clashes", "missile attack", "houthi",
        "red sea attack", "maritime attack"
    ],
    "bankruptcy": [
        "bankruptcy", "bankrupt", "insolvency", "insolvent", "chapter 11",
        "liquidation", "receivership"
    ],
    "plant_shutdown": [
        "plant shutdown", "facility shutdown", "manufacturing halt",
        "production stopped", "operations suspended", "facility closure",
        "plant closure", "closed facility"
    ],
    "fda_warning": [
        "fda warning letter", "warning letter", "fda action", "cgmp violation",
        "gmp violation", "483 observations", "consent decree", "import alert",
        "recall", "ema action", "cdsco", "usfda"
    ],
    "drug_recall": [
        "drug recall", "product recall", "voluntary recall", "mandatory recall",
        "contamination", "ndma", "nitrosamine"
    ],
    "strike": [
        "strike", "walkout", "labor strike", "workers strike", "union strike",
        "industrial action", "work stoppage"
    ],
    "tariff": [
        "tariff", "tariffs", "import duty", "customs duty", "trade war",
        "countervailing duty", "anti-dumping"
    ],
    "trade_restriction": [
        "trade restriction", "trade barrier", "import restriction",
        "quota", "trade dispute"
    ],
    "shipping_delay": [
        "shipping delay", "freight delay", "supply delay", "backlog",
        "bottleneck", "congestion", "rerouting", "cape of good hope"
    ],
    "port_congestion": [
        "port congestion", "port delay", "port closure", "harbor blocked",
        "canal blocked", "suez canal", "panama canal"
    ],
    "energy_crisis": [
        "energy crisis", "power outage", "gas shortage", "electricity shortage",
        "power cut", "rolling blackout", "gas rationing", "energy rationing"
    ],
    "political_instability": [
        "coup", "political crisis", "government collapse", "election violence",
        "political turmoil", "regime change", "protests"
    ],
    "shortage_warning": [
        "shortage", "supply shortage", "shortage warning", "supply constraints",
        "supply crunch", "tight supply"
    ],
    "price_increase": [
        "price increase", "price surge", "price spike", "cost increase",
        "inflation", "rising costs"
    ],
}


def detect_event_type(text: str, gemini_hint: Optional[str] = None) -> str:
    """
    Detect event type from text using keyword matching.
    Uses Gemini NER output as a priority hint if available.
    """
    if gemini_hint and gemini_hint != "other" and gemini_hint in EVENT_SEVERITY:
        return gemini_hint

    import re
    text_lower = text.lower()
    for event_type, keywords in EVENT_KEYWORDS.items():
        for kw in keywords:
            # Use word-boundary matching so 'war' doesn't hit inside 'warning'
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text_lower):
                return event_type

    return "other"


def get_severity_score(event_type: str) -> float:
    """
    Get a severity score (0–100) from the event type band.
    Uses the midpoint of the band.
    """
    lo, hi = EVENT_SEVERITY.get(event_type, (15, 35))
    return (lo + hi) / 2.0


# ─────────────────────────────────────────────────────────────────────────────
#  FinBERT sentiment (lazy load)
# ─────────────────────────────────────────────────────────────────────────────

_finbert = None
_finbert_available = None


def _get_finbert():
    global _finbert, _finbert_available
    if _finbert_available is False:
        return None
    if _finbert is not None:
        return _finbert

    try:
        from transformers import pipeline
        logger.info("Loading FinBERT sentiment model...")
        _finbert = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device=-1,
        )
        _finbert_available = True
        logger.info("FinBERT loaded ✓")
        return _finbert
    except Exception as e:
        logger.warning(f"FinBERT not available: {e} — using keyword sentiment fallback")
        _finbert_available = False
        return None


def _keyword_sentiment(text: str) -> float:
    """
    Simple keyword-based negative sentiment score (0.0–1.0).
    Used as fallback when FinBERT is not available.
    """
    negative_words = [
        "disruption", "shortage", "recall", "warning", "shutdown", "closure",
        "crisis", "attack", "ban", "embargo", "sanction", "bankruptcy",
        "delay", "risk", "threat", "violation", "contamination", "halt",
        "failure", "collapse", "surge", "spike", "restrict", "conflict",
        "war", "strike", "blocked", "suspended", "cancelled"
    ]
    positive_words = [
        "agreement", "partnership", "expansion", "growth", "investment",
        "approval", "launch", "success", "increase", "recovery"
    ]

    text_lower = text.lower()
    neg_count = sum(1 for w in negative_words if w in text_lower)
    pos_count = sum(1 for w in positive_words if w in text_lower)

    total = neg_count + pos_count
    if total == 0:
        return 0.3  # neutral baseline

    return min(neg_count / total, 1.0)


def get_finbert_negative_confidence(text: str) -> float:
    """
    Get FinBERT negative sentiment confidence (0.0–1.0).
    Falls back to keyword sentiment if model unavailable.
    """
    finbert = _get_finbert()
    if finbert is None:
        return _keyword_sentiment(text)

    try:
        # FinBERT works best on short financial text
        result = finbert(text[:512], truncation=True)
        label = result[0]["label"].lower()
        score = result[0]["score"]

        if label == "negative":
            return score
        elif label == "positive":
            return 1.0 - score
        else:  # neutral
            return 0.3
    except Exception as e:
        logger.error(f"FinBERT inference error: {e}")
        return _keyword_sentiment(text)


# ─────────────────────────────────────────────────────────────────────────────
#  Main Stage 3 runner
# ─────────────────────────────────────────────────────────────────────────────

def run_stage3(article) -> dict:
    """
    Run sentiment and severity scoring for one article.

    Returns dict with:
        event_type: str
        rule_severity: float (0–100)
        finbert_negative: float (0–1)
        combined_severity: float (0–100)
    """
    # Build text for analysis
    text = article.headline + ". " + (article.body or article.summary or "")[:500]

    # Detect event type (use Gemini hint from Stage 2 if available)
    gemini_hint = getattr(article, "_gemini_event_type", None)
    event_type = detect_event_type(text, gemini_hint)

    # Rule-based severity
    rule_severity = get_severity_score(event_type)

    # Also check Gemini severity hint from Stage 2
    gemini_severity_hint = getattr(article, "_gemini_severity", None)
    if gemini_severity_hint:
        severity_boost = {
            "critical": 10, "high": 5, "medium": 0, "low": -5, "none": -10
        }
        rule_severity = min(100, rule_severity + severity_boost.get(gemini_severity_hint, 0))

    # FinBERT / keyword sentiment (use headline only for speed)
    finbert_negative = get_finbert_negative_confidence(article.headline)

    # Combined severity formula from blueprint:
    # Final = (Rule_Base × 0.7) + (FinBERT_Negative × 30)
    combined = (rule_severity * 0.7) + (finbert_negative * 30)
    combined = max(0.0, min(100.0, combined))

    result = {
        "event_type":        event_type,
        "rule_severity":     rule_severity,
        "finbert_negative":  finbert_negative,
        "combined_severity": combined,
    }

    logger.debug(
        f"  Stage 3: event={event_type} rule={rule_severity:.1f} "
        f"finbert_neg={finbert_negative:.2f} → severity={combined:.1f}"
    )

    return result
