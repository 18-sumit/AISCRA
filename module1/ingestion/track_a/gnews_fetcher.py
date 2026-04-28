"""
module1/ingestion/track_a/gnews_fetcher.py
───────────────────────────────────────────
Track A: GNews.io keyword search fetcher.

GNews free tier limits:
  - 100 requests/day
  - Strategy: top 2 keywords per supplier/raw_material entry only
  - 10 articles per request max on free tier

API endpoint: GET https://gnews.io/api/v4/search
  Params: q={keyword}, lang=en, token={key}, max=10

Track B: /top-news endpoint for trending articles globally.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from dotenv import load_dotenv

from module1.ingestion.normalizer import NormalizedArticle, normalize_gnews, validate_article

load_dotenv()
logger = logging.getLogger(__name__)

GNEWS_SEARCH = "https://gnews.io/api/v4/search"
GNEWS_TOP = "https://gnews.io/api/v4/top-headlines"
REQUEST_DELAY = 0.8     # GNews is stricter on rate limits


class GNewsFetcher:
    """
    Fetches news from GNews.io using keyword search (Track A)
    and top-news for Track B.

    Free tier: 100 req/day, 10 articles/request.
    Strategy: limit to top 2 keywords per entity to conserve quota.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        fetch_type: str = "targeted",
        max_articles: int = 20,
    ):
        self.api_key = api_key or os.getenv("GNEWS_KEY")
        self.fetch_type = fetch_type
        self.max_articles = int(os.getenv("MAX_ARTICLES_PER_SOURCE", max_articles))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def fetch_by_keywords(self, keywords: list, max_per_keyword: int = 2) -> list:
        """
        Fetch articles for each keyword (one request per keyword).
        Conserves the free tier quota by limiting to max_per_keyword articles per search.

        To preserve quota, pass only the top 2 most specific keywords per entity
        (the pipeline handles this batching).

        Returns: list of NormalizedArticle dicts
        """
        if not self.is_available():
            logger.warning("GNews key not set — skipping Track A GNews fetch")
            return []

        all_articles = []
        since = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info(f"GNews Track A: {len(keywords)} keywords (1 req each)")

        for keyword in keywords:
            if len(all_articles) >= self.max_articles:
                break

            params = {
                "q": f'"{keyword}"',
                "lang": "en",
                "token": self.api_key,
                "max": min(max_per_keyword, 10),
                "from": since,
                "sortby": "publishedAt",
            }

            try:
                resp = requests.get(GNEWS_SEARCH, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                for raw in data.get("articles", []):
                    normalized = normalize_gnews(raw, self.fetch_type)
                    if normalized and validate_article(normalized):
                        all_articles.append(normalized)

                logger.debug(f"  GNews '{keyword}': {len(data.get('articles', []))} articles")

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else None
                if status == 403:
                    logger.error("GNews: API key invalid or quota exceeded")
                    break
                elif status == 429:
                    logger.warning("GNews rate limit — pausing 60 seconds")
                    time.sleep(60)
                else:
                    logger.error(f"GNews HTTP error: {e}")
            except requests.exceptions.Timeout:
                logger.error(f"GNews timeout for keyword: {keyword}")
            except Exception as e:
                logger.error(f"GNews unexpected error: {e}")
            finally:
                time.sleep(REQUEST_DELAY)

        logger.info(f"GNews Track A: collected {len(all_articles)} articles")
        return all_articles

    def fetch_top_news(self, topics: list = None, max_articles: int = None) -> list:
        """
        Fetch top/trending news globally for Track B.

        GNews topics: breaking-news, world, nation, business, technology,
                      entertainment, sports, science, health
        """
        if not self.is_available():
            logger.warning("GNews key not set — skipping Track B top-news fetch")
            return []

        limit = max_articles or self.max_articles
        topics = topics or ["world", "business", "nation", "technology", "science"]
        all_articles = []

        for topic in topics:
            if len(all_articles) >= limit:
                break

            params = {
                "topic": topic,
                "lang": "en",
                "token": self.api_key,
                "max": min(10, limit - len(all_articles)),
                "sortby": "relevance",
            }

            try:
                resp = requests.get(GNEWS_TOP, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                for raw in data.get("articles", []):
                    normalized = normalize_gnews(raw, "hot_news")
                    if normalized and validate_article(normalized):
                        all_articles.append(normalized)

                logger.debug(f"  GNews top-news topic={topic}: {len(data.get('articles', []))} articles")

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else None
                if status == 403:
                    logger.error("GNews: Invalid key / quota exceeded")
                    break
                else:
                    logger.error(f"GNews HTTP error (topic={topic}): {e}")
            except Exception as e:
                logger.error(f"GNews top-news error (topic={topic}): {e}")

            time.sleep(REQUEST_DELAY)

        logger.info(f"GNews Track B: collected {len(all_articles)} top-news articles")
        return all_articles
