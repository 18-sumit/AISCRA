"""
module1/ingestion/normalizer.py
────────────────────────────────
Maps all raw source formats into a standard NormalizedArticle dict.

Supported input formats:
  • NewsAPI JSON response article objects
  • GNews JSON response article objects
  • feedparser Entry objects (RSS / Atom)
  • GDELT CSV row dicts

Output is always a NormalizedArticle TypedDict with consistent fields.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Optional, TypedDict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Standard output structure
# ─────────────────────────────────────────────────────────────────────────────

class NormalizedArticle(TypedDict):
    url: str
    url_hash: str           # SHA-256 of lowercase-stripped URL
    headline: str
    body: Optional[str]     # Full article text (if extractable)
    summary: Optional[str]  # First ~3 sentences or API-provided description
    source_name: str
    source_domain: str
    published_at: Optional[datetime]
    fetch_type: str         # 'targeted' or 'hot_news'
    raw_source: str         # 'newsapi' | 'gnews' | 'rss' | 'gdelt'


# ─────────────────────────────────────────────────────────────────────────────
#  URL hashing
# ─────────────────────────────────────────────────────────────────────────────

def hash_url(url: str) -> str:
    """SHA-256 of lowercased, stripped URL. Used as primary dedup key."""
    cleaned = url.strip().lower().split("?")[0].rstrip("/")
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def extract_domain(url: str) -> str:
    """Extract domain from URL. Returns 'unknown' on failure."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip 'www.' prefix for consistency
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or "unknown"
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
#  Date parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(value) -> Optional[datetime]:
    """
    Parse a date from various formats into a timezone-aware UTC datetime.
    Accepts: ISO strings, feedparser time tuples, None.
    """
    if value is None:
        return None

    # feedparser returns time.struct_time tuples
    if hasattr(value, "tm_year"):
        try:
            import calendar
            ts = calendar.timegm(value)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Text cleaning
# ─────────────────────────────────────────────────────────────────────────────

def _clean_text(text: Optional[str]) -> Optional[str]:
    """Remove HTML tags, collapse whitespace, strip."""
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)       # strip HTML
    text = re.sub(r"&[a-z]+;", " ", text)       # decode common HTML entities
    text = re.sub(r"\s+", " ", text)            # collapse whitespace
    return text.strip() or None


def _extract_summary(body: Optional[str], headline: str, max_chars: int = 500) -> Optional[str]:
    """Extract first ~3 sentences as a summary."""
    text = body or headline
    if not text:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    summary = " ".join(sentences[:3])
    return summary[:max_chars] if summary else None


# ─────────────────────────────────────────────────────────────────────────────
#  Format-specific normalizers
# ─────────────────────────────────────────────────────────────────────────────

def normalize_newsapi(article: dict, fetch_type: str) -> Optional[NormalizedArticle]:
    """
    Normalize a single article object from the NewsAPI JSON response.

    NewsAPI article structure:
    {
        "source": {"id": "...", "name": "..."},
        "author": "...",
        "title": "...",
        "description": "...",   ← short blurb
        "url": "...",
        "urlToImage": "...",
        "publishedAt": "2024-01-01T12:00:00Z",
        "content": "..."        ← truncated at 200 chars on free tier
    }
    """
    url = article.get("url", "")
    if not url or url == "https://removed.com":
        return None

    headline = _clean_text(article.get("title")) or ""
    if not headline or headline.lower() in ("[removed]", ""):
        return None

    body = _clean_text(article.get("content") or article.get("description"))
    summary = _clean_text(article.get("description"))

    return NormalizedArticle(
        url=url,
        url_hash=hash_url(url),
        headline=headline,
        body=body,
        summary=summary,
        source_name=article.get("source", {}).get("name") or extract_domain(url),
        source_domain=extract_domain(url),
        published_at=_parse_date(article.get("publishedAt")),
        fetch_type=fetch_type,
        raw_source="newsapi",
    )


def normalize_gnews(article: dict, fetch_type: str) -> Optional[NormalizedArticle]:
    """
    Normalize a single article from the GNews JSON response.

    GNews article structure:
    {
        "title": "...",
        "description": "...",
        "content": "...",
        "url": "...",
        "image": "...",
        "publishedAt": "2024-01-01T12:00:00Z",
        "source": {"name": "...", "url": "..."}
    }
    """
    url = article.get("url", "")
    if not url:
        return None

    headline = _clean_text(article.get("title")) or ""
    if not headline:
        return None

    body = _clean_text(article.get("content") or article.get("description"))
    summary = _clean_text(article.get("description"))

    return NormalizedArticle(
        url=url,
        url_hash=hash_url(url),
        headline=headline,
        body=body,
        summary=summary,
        source_name=article.get("source", {}).get("name") or extract_domain(url),
        source_domain=extract_domain(url),
        published_at=_parse_date(article.get("publishedAt")),
        fetch_type=fetch_type,
        raw_source="gnews",
    )


def normalize_rss(entry, source_name: str, fetch_type: str) -> Optional[NormalizedArticle]:
    """
    Normalize a feedparser Entry object from any RSS/Atom feed.

    feedparser unifies RSS 0.9/1.0/2.0 and Atom — we read:
      entry.link, entry.title, entry.summary, entry.content,
      entry.published_parsed (time struct) or entry.updated_parsed
    """
    url = entry.get("link", "")
    if not url:
        return None

    headline = _clean_text(entry.get("title")) or ""
    if not headline:
        return None

    # body: prefer full content, fall back to summary
    body = None
    if entry.get("content"):
        # content is a list of dicts with 'value'
        body = _clean_text(entry.content[0].get("value")) if entry.content else None
    if not body:
        body = _clean_text(entry.get("summary"))

    summary = _extract_summary(body, headline)

    pub_date = _parse_date(
        entry.get("published_parsed") or entry.get("updated_parsed")
    )

    return NormalizedArticle(
        url=url,
        url_hash=hash_url(url),
        headline=headline,
        body=body,
        summary=summary,
        source_name=source_name,
        source_domain=extract_domain(url),
        published_at=pub_date,
        fetch_type=fetch_type,
        raw_source="rss",
    )


def normalize_gdelt(row: dict, fetch_type: str) -> Optional[NormalizedArticle]:
    """
    Normalize a GDELT Events CSV row.

    GDELT 2.0 Events CSV columns (15-minute export):
    GlobalEventID, Day, MonthYear, Year, FractionDate,
    Actor1Code, Actor1Name, Actor1CountryCode, ...
    SOURCEURL, ...

    We use: SOURCEURL as the URL, Actor1Name + EventCode description as headline.
    """
    url = row.get("SOURCEURL", "").strip()
    if not url or not url.startswith("http"):
        return None

    # Build a headline from available fields
    actor = row.get("Actor1Name", "").strip().title()
    actor2 = row.get("Actor2Name", "").strip().title()
    event_desc = row.get("EventCode", "").strip()

    if actor and actor2:
        headline = f"{actor} — {actor2}: Event {event_desc}"
    elif actor:
        headline = f"{actor}: Global Event {event_desc}"
    else:
        headline = f"GDELT Event {event_desc}"

    # Date from Day column: YYYYMMDD
    pub_date = None
    day_str = str(row.get("Day", "")).strip()
    if len(day_str) == 8:
        try:
            pub_date = datetime(
                int(day_str[:4]), int(day_str[4:6]), int(day_str[6:8]),
                tzinfo=timezone.utc
            )
        except ValueError:
            pass

    return NormalizedArticle(
        url=url,
        url_hash=hash_url(url),
        headline=headline,
        body=None,  # GDELT rows have no body — fetched later if needed
        summary=None,
        source_name="GDELT",
        source_domain=extract_domain(url),
        published_at=pub_date,
        fetch_type=fetch_type,
        raw_source="gdelt",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_article(article: NormalizedArticle) -> bool:
    """
    Reject articles that are clearly unusable:
    - No URL
    - No headline or headline is a single word
    - URL is not http/https
    """
    if not article.get("url") or not article.get("headline"):
        return False
    url = article["url"]
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    if len(article["headline"].split()) < 3:
        return False
    return True
