"""
module1/ingestion/track_a/gdelt_fetcher.py
───────────────────────────────────────────
GDELT 2.0 Events CSV fetcher — no API key required.

GDELT publishes a new 15-minute events CSV every 15 minutes at:
  http://data.gdeltproject.org/gdeltv2/lastupdate.txt
  → lists the latest 3 CSV files (15-min export)

Track A strategy: download latest CSV → filter rows where SOURCEURL or
Actor fields contain any of our supply chain keywords.

Track B strategy: same CSV → extract top-N most frequent events by
CAMEO event code (trending events by frequency).

Why direct CSV download?
  - No API endpoint, no authentication
  - No timeouts from API limits
  - Raw event data with source URLs we can follow
  - Free, no rate limits

GDELT Events 2.0 columns we use:
  Column 0:  GlobalEventID
  Column 1:  Day (YYYYMMDD)
  Column 26: Actor1Name
  Column 35: Actor2Name
  Column 28: Actor1CountryCode
  Column 53: ActionGeo_CountryCode
  Column 57: SOURCEURL
  Column 26: EventCode (CAMEO code)
"""

import csv
import io
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests

from module1.ingestion.normalizer import NormalizedArticle, normalize_gdelt, validate_article

logger = logging.getLogger(__name__)

GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_TIMEOUT = 60          # Large CSVs, need more time
MAX_CSV_ROWS = 5000         # Don't process the entire 50k-row CSV
REQUEST_DELAY = 1.0


class GDELTFetcher:
    """
    Downloads and filters the latest GDELT 2.0 Events CSV.

    Track A: keyword filter on SOURCEURL + Actor fields
    Track B: top-N events by frequency (most common CAMEO event codes)
    """

    def __init__(self, max_articles: int = 30):
        self.max_articles = int(os.getenv("MAX_ARTICLES_PER_SOURCE", max_articles))

    def _get_latest_csv_url(self) -> Optional[str]:
        """
        Fetch the GDELT lastupdate.txt to get the latest events CSV URL.
        Returns the URL of the most recent events export file.
        """
        try:
            resp = requests.get(GDELT_LASTUPDATE_URL, timeout=15)
            resp.raise_for_status()
            # lastupdate.txt format: each line is "<size> <md5> <url>"
            for line in resp.text.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3:
                    url = parts[2]
                    if "export" in url and url.endswith(".zip"):
                        return url
            return None
        except Exception as e:
            logger.error(f"GDELT: Failed to fetch lastupdate.txt: {e}")
            return None

    def _download_and_parse_csv(self, csv_url: str) -> list:
        """
        Download the GDELT CSV zip and parse it into row dicts.
        Returns list of row dicts (up to MAX_CSV_ROWS).
        """
        try:
            logger.debug(f"GDELT: downloading {csv_url}")
            resp = requests.get(csv_url, timeout=GDELT_TIMEOUT, stream=True)
            resp.raise_for_status()

            content = b""
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                content += chunk
                if len(content) > 50 * 1024 * 1024:  # 50MB safety cap
                    logger.warning("GDELT: CSV file exceeds 50MB — truncating")
                    break

            # GDELT exports are zipped CSVs
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                csv_filename = [n for n in zf.namelist() if n.endswith(".CSV")][0]
                with zf.open(csv_filename) as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="latin-1"), delimiter="\t")
                    rows = []
                    for i, row in enumerate(reader):
                        if i >= MAX_CSV_ROWS:
                            break
                        rows.append(row)
            return rows

        except zipfile.BadZipFile:
            logger.error("GDELT: downloaded file is not a valid zip")
            return []
        except Exception as e:
            logger.error(f"GDELT: CSV download/parse error: {e}")
            return []

    def _row_to_dict(self, row: list) -> dict:
        """
        Map GDELT CSV row (tab-delimited) to a dict using known column positions.
        GDELT 2.0 Events schema has 61 columns.
        """
        if len(row) < 58:
            return {}
        return {
            "GlobalEventID": row[0],
            "Day": row[1],
            "EventCode": row[26] if len(row) > 26 else "",
            "Actor1Name": row[5] if len(row) > 5 else "",
            "Actor1CountryCode": row[7] if len(row) > 7 else "",
            "Actor2Name": row[15] if len(row) > 15 else "",
            "Actor2CountryCode": row[17] if len(row) > 17 else "",
            "GoldsteinScale": row[30] if len(row) > 30 else "0",
            "NumMentions": row[31] if len(row) > 31 else "0",
            "ActionGeo_CountryCode": row[51] if len(row) > 51 else "",
            "SOURCEURL": row[57] if len(row) > 57 else "",
        }

    def fetch_targeted(self, keywords: list) -> list:
        """
        Track A: Download latest GDELT CSV and filter rows by keyword
        match in SOURCEURL or Actor name fields.

        Returns: list of NormalizedArticle dicts
        """
        csv_url = self._get_latest_csv_url()
        if not csv_url:
            logger.warning("GDELT Track A: Could not fetch lastupdate.txt")
            return []

        rows = self._download_and_parse_csv(csv_url)
        if not rows:
            return []

        logger.info(f"GDELT Track A: filtering {len(rows)} rows by {len(keywords)} keywords")

        keywords_lower = [kw.lower() for kw in keywords]
        articles = []
        seen_urls = set()

        for raw_row in rows:
            row = self._row_to_dict(raw_row)
            if not row:
                continue

            url = row.get("SOURCEURL", "").strip()
            if not url or url in seen_urls:
                continue

            actor1 = row.get("Actor1Name", "").lower()
            actor2 = row.get("Actor2Name", "").lower()
            url_lower = url.lower()

            # Check if any keyword appears in URL or Actor fields
            matched = any(
                kw in url_lower or kw in actor1 or kw in actor2
                for kw in keywords_lower
            )

            if matched:
                normalized = normalize_gdelt(row, fetch_type="targeted")
                if normalized and validate_article(normalized):
                    articles.append(normalized)
                    seen_urls.add(url)

            if len(articles) >= self.max_articles:
                break

        logger.info(f"GDELT Track A: {len(articles)} matching articles from {len(rows)} rows")
        return articles

    def fetch_trending(self, top_n: int = None) -> list:
        """
        Track B: Fetch the most frequently mentioned events from GDELT.
        Ranks by NumMentions field to surface the biggest global events.

        Returns: list of NormalizedArticle dicts
        """
        csv_url = self._get_latest_csv_url()
        if not csv_url:
            logger.warning("GDELT Track B: Could not fetch lastupdate.txt")
            return []

        rows = self._download_and_parse_csv(csv_url)
        if not rows:
            return []

        limit = top_n or self.max_articles
        logger.info(f"GDELT Track B: ranking {len(rows)} rows by mention frequency")

        # Parse and rank rows by NumMentions
        scored_rows = []
        for raw_row in rows:
            row = self._row_to_dict(raw_row)
            if not row or not row.get("SOURCEURL"):
                continue
            try:
                mentions = int(row.get("NumMentions", 0))
            except (ValueError, TypeError):
                mentions = 0
            scored_rows.append((mentions, row))

        # Sort descending by mentions — most-covered events first
        scored_rows.sort(key=lambda x: x[0], reverse=True)

        articles = []
        seen_urls = set()

        for _, row in scored_rows:
            url = row.get("SOURCEURL", "").strip()
            if not url or url in seen_urls:
                continue

            normalized = normalize_gdelt(row, fetch_type="hot_news")
            if normalized and validate_article(normalized):
                articles.append(normalized)
                seen_urls.add(url)

            if len(articles) >= limit:
                break

        logger.info(f"GDELT Track B: {len(articles)} trending articles")
        return articles
