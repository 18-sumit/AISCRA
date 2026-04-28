"""
module1/ingestion/pipeline.py
──────────────────────────────
Orchestrates the full Module 1 ingestion pipeline for one run.

Pipeline flow:
  1. Launch Track A and Track B fetchers in parallel
  2. Normalize all articles to standard format
  3. Keyword relevance pre-filter (Track A only)
  4. Batch deduplication (URL hash + semantic)
  5. Save unique articles to DB
  6. Write fetch_log entry

Called by the scheduler every FETCH_INTERVAL_MINUTES minutes,
or once via CLI --once flag.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from module1.config.company_profile import CompanyProfile
from module1.db.models import Article, FetchLog
from module1.db.session import get_session
from module1.dedup.deduplicator import Deduplicator
from module1.ingestion.normalizer import NormalizedArticle
from module1.ingestion.track_a.gdelt_fetcher import GDELTFetcher
from module1.ingestion.track_a.gnews_fetcher import GNewsFetcher
from module1.ingestion.track_a.newsapi_fetcher import NewsAPIFetcher
from module1.ingestion.track_a.rss_fetcher import RSSFetcher

load_dotenv()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Keyword relevance pre-filter (Track A)
# ─────────────────────────────────────────────────────────────────────────────

def keyword_pre_filter(article: NormalizedArticle, keywords: list) -> bool:
    """
    Check if an article's headline or body contains any of the supply chain keywords.
    Uses word-level matching (not substring) to avoid false positives.

    Returns True if relevant.
    """
    text = (article.get("headline") or "").lower()
    if article.get("body"):
        text += " " + article["body"][:1000].lower()
    if article.get("summary"):
        text += " " + article["summary"].lower()

    for kw in keywords:
        kw_lower = kw.lower()
        # Word-boundary check: phrase must appear as a phrase, not mid-word
        if kw_lower in text:
            return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
#  DB persistence
# ─────────────────────────────────────────────────────────────────────────────

def _save_articles(
    articles: list,
    embeddings: dict,
    session: Session,
) -> int:
    """
    Save a list of deduplicated NormalizedArticle dicts to the articles table.
    Returns number of articles saved.
    """
    saved = 0
    for article in articles:
        embedding = embeddings.get(article["url_hash"])

        db_article = Article(
            url_hash=article["url_hash"],
            url=article["url"],
            headline=article["headline"],
            body=article.get("body"),
            summary=article.get("summary"),
            source_name=article.get("source_name"),
            source_domain=article.get("source_domain"),
            published_at=article.get("published_at"),
            fetched_at=datetime.now(tz=timezone.utc),
            fetch_type=article["fetch_type"],
            is_relevant_prefilter=article.get("is_relevant_prefilter"),
            # Track A articles skip Stage 0 (gemini_screened=True means "no need to screen")
            gemini_screened=(article["fetch_type"] == "targeted"),
            is_indirect_risk=False,
            processed=False,
            embedding_json=json.dumps(embedding) if embedding else None,
        )
        session.add(db_article)
        saved += 1

    return saved


def _write_fetch_log(
    session: Session,
    source: str,
    fetch_type: str,
    articles_fetched: int,
    articles_new: int,
    articles_relevant: int,
    duration_seconds: float,
    status: str = "success",
    error_message: Optional[str] = None,
):
    """Write a fetch_log entry for monitoring."""
    session.add(FetchLog(
        run_at=datetime.now(tz=timezone.utc),
        source=source,
        fetch_type=fetch_type,
        articles_fetched=articles_fetched,
        articles_new=articles_new,
        articles_relevant=articles_relevant,
        duration_seconds=duration_seconds,
        status=status,
        error_message=error_message,
    ))


# ─────────────────────────────────────────────────────────────────────────────
#  Track A pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_track_a(profile: CompanyProfile, deduplicator: Deduplicator) -> dict:
    """
    Run the full Track A (targeted) ingestion pipeline.

    1. NewsAPI keyword search
    2. GNews keyword search (top 2 keywords per entity)
    3. RSS pharma/supply chain feeds
    4. GDELT keyword filter

    Returns stats dict.
    """
    start = time.time()
    all_articles = []
    keywords = profile.get_all_keywords()

    logger.info(f"═══ Track A: Targeted Supply Chain News ═══")
    logger.info(f"  Keywords: {len(keywords)} total")

    # ── NewsAPI ──────────────────────────────────────────────────────────
    try:
        newsapi = NewsAPIFetcher(fetch_type="targeted")
        newsapi_articles = newsapi.fetch_by_keywords(keywords)
        all_articles.extend(newsapi_articles)
        logger.info(f"  NewsAPI Track A: {len(newsapi_articles)} articles")
    except Exception as e:
        logger.error(f"  NewsAPI Track A error: {e}")

    # ── GNews (top 2 keywords per entity to conserve quota) ──────────────
    try:
        # Flatten: take only first 2 keywords from each keyword_registry entry
        gnews_keywords = []
        for entry in profile.keyword_registry:
            gnews_keywords.extend(entry.keywords[:2])
        gnews_keywords = list(dict.fromkeys(gnews_keywords))  # deduplicate, preserve order

        gnews = GNewsFetcher(fetch_type="targeted")
        gnews_articles = gnews.fetch_by_keywords(gnews_keywords, max_per_keyword=2)
        all_articles.extend(gnews_articles)
        logger.info(f"  GNews Track A: {len(gnews_articles)} articles")
    except Exception as e:
        logger.error(f"  GNews Track A error: {e}")

    # ── RSS feeds ─────────────────────────────────────────────────────────
    try:
        rss = RSSFetcher.from_profile_track_a(profile)
        rss_articles = rss.fetch_all()
        all_articles.extend(rss_articles)
        logger.info(f"  RSS Track A: {len(rss_articles)} articles")
    except Exception as e:
        logger.error(f"  RSS Track A error: {e}")

    # ── GDELT keyword filter ──────────────────────────────────────────────
    try:
        gdelt = GDELTFetcher()
        gdelt_articles = gdelt.fetch_targeted(keywords)
        all_articles.extend(gdelt_articles)
        logger.info(f"  GDELT Track A: {len(gdelt_articles)} articles")
    except Exception as e:
        logger.error(f"  GDELT Track A error: {e}")

    logger.info(f"  Track A total fetched: {len(all_articles)} articles")

    # ── Keyword pre-filter ────────────────────────────────────────────────
    pre_filtered = []
    for article in all_articles:
        relevant = keyword_pre_filter(article, keywords)
        article_copy = dict(article)
        article_copy["is_relevant_prefilter"] = relevant
        # For Track A, we keep all articles (RSS and GDELT may not have full body yet)
        # but tag relevance for Module 2 to use
        pre_filtered.append(article_copy)

    n_relevant = sum(1 for a in pre_filtered if a.get("is_relevant_prefilter"))
    logger.info(f"  Pre-filter: {n_relevant}/{len(pre_filtered)} relevant")

    # ── Dedup + Save ──────────────────────────────────────────────────────
    with get_session() as session:
        unique, embeddings = deduplicator.batch_deduplicate(pre_filtered, session)
        saved = _save_articles(unique, embeddings, session)
        _write_fetch_log(
            session,
            source="track_a_combined",
            fetch_type="targeted",
            articles_fetched=len(all_articles),
            articles_new=saved,
            articles_relevant=n_relevant,
            duration_seconds=time.time() - start,
        )

    return {
        "fetched": len(all_articles),
        "relevant": n_relevant,
        "saved": saved,
        "duration": time.time() - start,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Track B pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_track_b(profile: CompanyProfile, deduplicator: Deduplicator) -> dict:
    """
    Run the full Track B (hot_news) ingestion pipeline.

    1. NewsAPI top-headlines (all categories)
    2. GNews top-news (world, business, nation, technology)
    3. RSS geopolitics + commodities + regional business feeds
    4. GDELT trending events

    Track B articles are NOT pre-filtered — they go to Stage 0 (Gemini) in Module 2.
    They are tagged: gemini_screened=False, fetch_type='hot_news'.

    Returns stats dict.
    """
    start = time.time()
    all_articles = []

    logger.info(f"═══ Track B: Broad World News (Hot News Intelligence) ═══")

    # ── NewsAPI top-headlines ─────────────────────────────────────────────
    try:
        newsapi = NewsAPIFetcher(fetch_type="hot_news")
        newsapi_articles = newsapi.fetch_top_headlines(
            categories=["business", "science", "technology", "general", "health"],
            max_articles=50,
        )
        all_articles.extend(newsapi_articles)
        logger.info(f"  NewsAPI Track B: {len(newsapi_articles)} articles")
    except Exception as e:
        logger.error(f"  NewsAPI Track B error: {e}")

    # ── GNews top-news ────────────────────────────────────────────────────
    try:
        gnews = GNewsFetcher(fetch_type="hot_news")
        gnews_articles = gnews.fetch_top_news(
            topics=["world", "business", "nation", "technology", "science"],
        )
        all_articles.extend(gnews_articles)
        logger.info(f"  GNews Track B: {len(gnews_articles)} articles")
    except Exception as e:
        logger.error(f"  GNews Track B error: {e}")

    # ── RSS: geopolitics + commodities + regional ─────────────────────────
    try:
        rss = RSSFetcher.from_profile_track_b(profile)
        rss_articles = rss.fetch_all()
        all_articles.extend(rss_articles)
        logger.info(f"  RSS Track B: {len(rss_articles)} articles")
    except Exception as e:
        logger.error(f"  RSS Track B error: {e}")

    # ── GDELT trending events ─────────────────────────────────────────────
    try:
        gdelt = GDELTFetcher()
        gdelt_articles = gdelt.fetch_trending(top_n=30)
        all_articles.extend(gdelt_articles)
        logger.info(f"  GDELT Track B: {len(gdelt_articles)} articles")
    except Exception as e:
        logger.error(f"  GDELT Track B error: {e}")

    logger.info(f"  Track B total fetched: {len(all_articles)} articles (no pre-filter)")

    # ── Dedup + Save ──────────────────────────────────────────────────────
    with get_session() as session:
        unique, embeddings = deduplicator.batch_deduplicate(all_articles, session)
        saved = _save_articles(unique, embeddings, session)
        _write_fetch_log(
            session,
            source="track_b_combined",
            fetch_type="hot_news",
            articles_fetched=len(all_articles),
            articles_new=saved,
            articles_relevant=0,  # Track B relevance determined by Stage 0
            duration_seconds=time.time() - start,
        )

    return {
        "fetched": len(all_articles),
        "relevant": 0,  # N/A for Track B
        "saved": saved,
        "duration": time.time() - start,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Full pipeline run (both tracks)
# ─────────────────────────────────────────────────────────────────────────────

def run_ingestion(profile: CompanyProfile):
    """
    Run one complete ingestion cycle: both Track A and Track B in parallel.
    Called by the scheduler and by --once CLI flag.
    """
    logger.info(f"{'='*60}")
    logger.info(f"Module 1 Ingestion Run — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Company: {profile.company.name}")
    logger.info(f"{'='*60}")

    start = time.time()
    deduplicator = Deduplicator()
    results = {}

    # Run both tracks in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run_track_a, profile, deduplicator)
        future_b = executor.submit(run_track_b, profile, deduplicator)

        for future, name in [(future_a, "track_a"), (future_b, "track_b")]:
            try:
                results[name] = future.result()
            except Exception as e:
                logger.error(f"  {name} pipeline failed: {e}")
                results[name] = {"fetched": 0, "saved": 0, "error": str(e)}

    total_time = time.time() - start
    total_fetched = sum(r.get("fetched", 0) for r in results.values())
    total_saved = sum(r.get("saved", 0) for r in results.values())

    logger.info(f"{'='*60}")
    logger.info(f"Ingestion complete in {total_time:.1f}s")
    logger.info(f"  Track A: {results['track_a'].get('fetched', 0)} fetched, "
                f"{results['track_a'].get('saved', 0)} new, "
                f"{results['track_a'].get('relevant', 0)} relevant")
    logger.info(f"  Track B: {results['track_b'].get('fetched', 0)} fetched, "
                f"{results['track_b'].get('saved', 0)} new")
    logger.info(f"  Total:   {total_fetched} fetched, {total_saved} new articles saved")
    logger.info(f"{'='*60}")

    return results
