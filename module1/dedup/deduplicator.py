"""
module1/dedup/deduplicator.py
──────────────────────────────
Two-stage deduplication pipeline.

Stage A — URL hash: SHA-256 of normalized URL. O(1) exact check against DB index.
Stage B — Semantic similarity: cosine similarity on sentence-BERT embeddings.
           Compares new article against the last DEDUP_WINDOW_SIZE articles.
           Falls back to URL-only dedup if sentence-transformers not installed.

Threshold (from .env): DEDUP_SIMILARITY_THRESHOLD (default 0.92)
Window (from .env): DEDUP_WINDOW_SIZE (default 300)

Model: all-MiniLM-L6-v2 (~80MB download on first run, ~50ms per article on CPU)
Output: 384-dimensional embedding stored as JSON in articles.embedding_json
"""

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from module1.db.models import Article
from module1.ingestion.normalizer import NormalizedArticle

load_dotenv()
logger = logging.getLogger(__name__)

DEDUP_SIMILARITY_THRESHOLD = float(os.getenv("DEDUP_SIMILARITY_THRESHOLD", "0.92"))
DEDUP_WINDOW_SIZE = int(os.getenv("DEDUP_WINDOW_SIZE", "300"))

# ─────────────────────────────────────────────────────────────────────────────
#  Optional import: sentence-transformers
# ─────────────────────────────────────────────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    _MODEL_INSTANCE: Optional[SentenceTransformer] = None

    def _get_model() -> SentenceTransformer:
        """Lazy-load the embedding model (first call downloads ~80MB)."""
        global _MODEL_INSTANCE
        if _MODEL_INSTANCE is None:
            logger.info("Loading sentence-transformer model all-MiniLM-L6-v2...")
            _MODEL_INSTANCE = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded ✓")
        return _MODEL_INSTANCE

    SEMANTIC_DEDUP_AVAILABLE = True

except ImportError:
    logger.warning(
        "sentence-transformers not installed — falling back to URL-only deduplication. "
        "Run: pip install sentence-transformers"
    )
    SEMANTIC_DEDUP_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
#  Cosine similarity
# ─────────────────────────────────────────────────────────────────────────────

def _cosine_similarity(a: list, b: list) -> float:
    """Cosine similarity between two vectors."""
    import numpy as np
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _embed_text(text: str) -> Optional[list]:
    """Embed a text string into a 384-dimensional vector."""
    if not SEMANTIC_DEDUP_AVAILABLE:
        return None
    try:
        model = _get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Deduplicator class
# ─────────────────────────────────────────────────────────────────────────────

class Deduplicator:
    """
    Stateless deduplicator: checks a NormalizedArticle against the DB.

    Usage:
        dedup = Deduplicator()
        with get_session() as session:
            is_dup, embedding = dedup.is_duplicate(article, session)
            if not is_dup:
                # save article, store embedding
    """

    def __init__(
        self,
        threshold: float = DEDUP_SIMILARITY_THRESHOLD,
        window_size: int = DEDUP_WINDOW_SIZE,
    ):
        self.threshold = threshold
        self.window_size = window_size
        self._window_embeddings: Optional[list] = None  # lazy cache
        self._window_loaded_at = None

    # ── Stage A: URL hash check ────────────────────────────────────────────

    def _url_exists(self, url_hash: str, session: Session) -> bool:
        """Check if URL hash already exists in DB."""
        return session.query(
            session.query(Article).filter_by(url_hash=url_hash).exists()
        ).scalar()

    # ── Stage B: Semantic similarity check ────────────────────────────────

    def _load_window(self, session: Session) -> list:
        """
        Load the last WINDOW_SIZE article embeddings from DB.
        Returns list of (article_id, embedding_vector) tuples.
        Cached per Deduplicator instance to avoid redundant DB reads.
        """
        import time
        now = time.time()

        # Refresh window if >30 seconds old (prevents stale cache in long runs)
        if self._window_embeddings is not None and self._window_loaded_at:
            if now - self._window_loaded_at < 30:
                return self._window_embeddings

        rows = (
            session.query(Article.id, Article.embedding_json)
            .filter(Article.embedding_json.isnot(None))
            .order_by(Article.id.desc())
            .limit(self.window_size)
            .all()
        )

        self._window_embeddings = [
            (row.id, json.loads(row.embedding_json))
            for row in rows
        ]
        self._window_loaded_at = now
        return self._window_embeddings

    def _is_semantically_duplicate(self, embedding: list, session: Session) -> bool:
        """
        Compare embedding against recent articles.
        Returns True if any article exceeds the similarity threshold.
        """
        window = self._load_window(session)
        for article_id, stored_embedding in window:
            sim = _cosine_similarity(embedding, stored_embedding)
            if sim >= self.threshold:
                logger.debug(f"  Semantic dup: similarity={sim:.3f} vs article_id={article_id}")
                return True
        return False

    # ── Public API ─────────────────────────────────────────────────────────

    def is_duplicate(self, article: NormalizedArticle, session: Session) -> tuple:
        """
        Check if an article is a duplicate.

        Returns:
            (is_duplicate: bool, embedding: Optional[list])
            embedding is the computed vector (or None if unavailable)
            — caller should store this in the DB if is_duplicate=False
        """
        # Stage A: URL hash
        if self._url_exists(article["url_hash"], session):
            logger.debug(f"  URL dup: {article['url'][:80]}")
            return True, None

        # Stage B: semantic similarity
        embedding = None
        if SEMANTIC_DEDUP_AVAILABLE:
            # Embed headline + first 200 chars of body for speed
            text = article["headline"]
            if article.get("body"):
                text += " " + article["body"][:200]

            embedding = _embed_text(text)
            if embedding and self._is_semantically_duplicate(embedding, session):
                return True, embedding

        return False, embedding

    def batch_deduplicate(
        self, articles: list, session: Session
    ) -> tuple:
        """
        Deduplicate a batch of articles.

        Returns:
            (unique_articles: list, embeddings: dict[url_hash -> embedding])
        """
        unique = []
        embeddings = {}
        seen_hashes = set()  # within-batch dedup (two sources, same story)

        for article in articles:
            url_hash = article["url_hash"]

            if url_hash in seen_hashes:
                continue

            is_dup, embedding = self.is_duplicate(article, session)
            if not is_dup:
                unique.append(article)
                if embedding:
                    embeddings[url_hash] = embedding
                seen_hashes.add(url_hash)

        logger.info(
            f"Dedup: {len(articles)} → {len(unique)} unique "
            f"({len(articles) - len(unique)} duplicates removed)"
        )
        return unique, embeddings
