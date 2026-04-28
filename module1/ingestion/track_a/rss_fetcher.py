"""
module1/ingestion/track_a/rss_fetcher.py
─────────────────────────────────────────
RSS/Atom feed fetcher — works for both Track A and Track B.
No API key required. Pure feedparser.

Track A feeds: pharma industry, supply chain, FDA/regulatory, chemicals
Track B feeds: geopolitics, commodities, regional business

Handles:
  - Connection timeouts gracefully
  - Malformed feeds (feedparser is very lenient)
  - Missing published dates (falls back to fetched_at)
  - Concurrent fetching with ThreadPoolExecutor
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests

from module1.ingestion.normalizer import NormalizedArticle, normalize_rss, validate_article

logger = logging.getLogger(__name__)

# feedparser user agent (some feeds block default Python UA)
FEEDPARSER_UA = "Mozilla/5.0 (supply-chain-monitor/1.0; +https://github.com/supply-chain-risk)"
MAX_WORKERS = 6         # concurrent feed fetches
FEED_TIMEOUT = 20       # seconds per feed fetch


class RSSFetcher:
    """
    Fetches and normalizes articles from a list of RSS/Atom feeds.

    Args:
        feeds:      list of dicts with 'name', 'url', 'category' keys
        fetch_type: 'targeted' or 'hot_news'
        max_per_feed: maximum articles to keep per feed
    """

    def __init__(
        self,
        feeds: list,
        fetch_type: str = "targeted",
        max_per_feed: int = 20,
    ):
        self.feeds = feeds
        self.fetch_type = fetch_type
        self.max_per_feed = max_per_feed

    def _fetch_single_feed(self, feed_config: dict) -> tuple:
        """
        Fetch a single RSS feed. Returns (feed_name, articles_list, error).
        Called by ThreadPoolExecutor workers.
        """
        name = feed_config["name"]
        url = feed_config["url"]
        articles = []

        try:
            # Use requests to fetch the raw content with timeout control
            # feedparser's built-in fetch has no timeout option
            headers = {"User-Agent": FEEDPARSER_UA}
            resp = requests.get(url, timeout=FEED_TIMEOUT, headers=headers)
            resp.raise_for_status()

            # Parse the downloaded content
            parsed = feedparser.parse(resp.content, response_headers={"Content-Location": url})

            if parsed.bozo and not parsed.entries:
                # bozo=True means malformed feed, but may still have entries
                logger.debug(f"  RSS feed '{name}' is malformed: {parsed.bozo_exception}")

            entries = parsed.entries[:self.max_per_feed]
            for entry in entries:
                normalized = normalize_rss(entry, source_name=name, fetch_type=self.fetch_type)
                if normalized and validate_article(normalized):
                    articles.append(normalized)

            logger.debug(f"  RSS '{name}': fetched {len(entries)} entries, kept {len(articles)}")
            return name, articles, None

        except requests.exceptions.Timeout:
            return name, [], f"Timeout after {FEED_TIMEOUT}s"
        except requests.exceptions.ConnectionError as e:
            return name, [], f"Connection error: {e}"
        except requests.exceptions.HTTPError as e:
            return name, [], f"HTTP {e.response.status_code}"
        except Exception as e:
            return name, [], f"Unexpected error: {e}"

    def fetch_all(self) -> list:
        """
        Fetch all configured feeds concurrently.
        Returns: flat list of NormalizedArticle dicts from all feeds.
        """
        if not self.feeds:
            logger.warning("RSSFetcher: no feeds configured")
            return []

        all_articles = []
        failed = []

        logger.info(f"RSS fetcher: {len(self.feeds)} feeds (fetch_type={self.fetch_type})")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._fetch_single_feed, feed): feed
                for feed in self.feeds
            }

            for future in as_completed(futures):
                feed_cfg = futures[future]
                try:
                    name, articles, error = future.result()
                    if error:
                        logger.warning(f"  RSS '{name}' failed: {error}")
                        failed.append(name)
                    else:
                        all_articles.extend(articles)
                except Exception as e:
                    logger.error(f"  RSS fetch executor error for '{feed_cfg['name']}': {e}")
                    failed.append(feed_cfg["name"])

        if failed:
            logger.info(f"RSS: {len(failed)} feeds failed: {failed}")
        logger.info(f"RSS: total {len(all_articles)} articles from {len(self.feeds) - len(failed)} feeds")

        return all_articles

    @classmethod
    def from_profile_track_a(cls, profile, max_per_feed: int = 20) -> "RSSFetcher":
        """Convenience constructor: build Track A fetcher from CompanyProfile."""
        feeds = [
            {"name": f.name, "url": f.url, "category": f.category}
            for f in profile.rss_feeds.track_a
        ]
        return cls(feeds=feeds, fetch_type="targeted", max_per_feed=max_per_feed)

    @classmethod
    def from_profile_track_b(cls, profile, max_per_feed: int = 20) -> "RSSFetcher":
        """Convenience constructor: build Track B fetcher from CompanyProfile."""
        feeds = [
            {"name": f.name, "url": f.url, "category": f.category}
            for f in profile.rss_feeds.track_b
        ]
        return cls(feeds=feeds, fetch_type="hot_news", max_per_feed=max_per_feed)
