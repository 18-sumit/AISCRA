"""
module1/ingestion/track_a/newsapi_fetcher.py
─────────────────────────────────────────────
Track A: NewsAPI keyword search fetcher.

Searches for articles that explicitly mention the company's suppliers,
raw materials, and supply chain keywords. Articles are tagged fetch_type='targeted'.

Free tier limits:
  - 100 requests/day
  - Keywords are batched in groups of 5 (one API call per batch)
  - Results limited to max MAX_ARTICLES_PER_SOURCE per run

API endpoint: GET https://newsapi.org/v2/everything
  Params: q={keywords}, language=en, sortBy=publishedAt, pageSize=20
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import requests
from dotenv import load_dotenv

from module1.ingestion.normalizer import NormalizedArticle, normalize_newsapi, validate_article

load_dotenv()
logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
NEWSAPI_HEADLINES = "https://newsapi.org/v2/top-headlines"
BATCH_SIZE = 5          # keywords per API call
REQUEST_DELAY = 0.5     # seconds between calls to avoid rate limits


class NewsAPIFetcher:
    """
    Fetches news from NewsAPI.org using keyword search (Track A).

    Args:
        api_key:    NewsAPI key (defaults to NEWSAPI_KEY env var)
        fetch_type: 'targeted' for Track A, 'hot_news' for Track B
        max_articles: maximum articles to return per run
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        fetch_type: str = "targeted",
        max_articles: int = 20,
    ):
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self.fetch_type = fetch_type
        self.max_articles = int(os.getenv("MAX_ARTICLES_PER_SOURCE", max_articles))
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": self.api_key or ""})

    def is_available(self) -> bool:
        return bool(self.api_key)

    def fetch_by_keywords(self, keywords: list) -> list:
        """
        Fetch articles matching a list of keywords.
        Keywords are batched in groups of BATCH_SIZE to stay within rate limits.

        Returns: list of NormalizedArticle dicts
        """
        if not self.is_available():
            logger.warning("NewsAPI key not set — skipping Track A keyword fetch")
            return []

        all_articles = []
        batches = [keywords[i:i + BATCH_SIZE] for i in range(0, len(keywords), BATCH_SIZE)]
        articles_remaining = self.max_articles
        since = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info(f"NewsAPI Track A: {len(keywords)} keywords → {len(batches)} batches")

        for batch_idx, batch in enumerate(batches):
            if articles_remaining <= 0:
                break

            query = " OR ".join(f'"{kw}"' for kw in batch)
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": min(20, articles_remaining),
                "from": since,
            }

            try:
                resp = self.session.get(NEWSAPI_BASE, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "ok":
                    logger.warning(f"NewsAPI returned status={data.get('status')}: {data.get('message')}")
                    continue

                raw_articles = data.get("articles", [])
                for raw in raw_articles:
                    normalized = normalize_newsapi(raw, self.fetch_type)
                    if normalized and validate_article(normalized):
                        all_articles.append(normalized)
                        articles_remaining -= 1

                logger.debug(f"  Batch {batch_idx + 1}/{len(batches)}: got {len(raw_articles)} articles")

            except requests.exceptions.Timeout:
                logger.error(f"NewsAPI timeout on batch {batch_idx + 1}")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning("NewsAPI rate limit hit — pausing 60 seconds")
                    time.sleep(60)
                elif e.response.status_code == 401:
                    logger.error("NewsAPI: Invalid API key")
                    break
                else:
                    logger.error(f"NewsAPI HTTP error: {e}")
            except Exception as e:
                logger.error(f"NewsAPI unexpected error: {e}")
            finally:
                time.sleep(REQUEST_DELAY)

        logger.info(f"NewsAPI Track A: collected {len(all_articles)} articles")
        return all_articles

    def fetch_top_headlines(self, categories: list = None, max_articles: int = None) -> list:
        """
        Fetch top headlines from NewsAPI /top-headlines endpoint.
        Used for Track B (hot_news).

        Args:
            categories: list of NewsAPI categories (business, science, technology, etc.)
            max_articles: override instance max
        """
        if not self.is_available():
            logger.warning("NewsAPI key not set — skipping Track B top-headlines fetch")
            return []

        limit = max_articles or self.max_articles
        categories = categories or ["business", "science", "technology", "general", "health"]
        all_articles = []

        for category in categories:
            if len(all_articles) >= limit:
                break

            params = {
                "category": category,
                "language": "en",
                "pageSize": min(20, limit - len(all_articles)),
            }

            try:
                resp = self.session.get(NEWSAPI_HEADLINES, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "ok":
                    continue

                for raw in data.get("articles", []):
                    normalized = normalize_newsapi(raw, "hot_news")
                    if normalized and validate_article(normalized):
                        all_articles.append(normalized)

                logger.debug(f"  Top headlines category={category}: {len(data.get('articles', []))} articles")

            except Exception as e:
                logger.error(f"NewsAPI top-headlines error (category={category}): {e}")

            time.sleep(REQUEST_DELAY)

        logger.info(f"NewsAPI Track B: collected {len(all_articles)} top-headline articles")
        return all_articles
