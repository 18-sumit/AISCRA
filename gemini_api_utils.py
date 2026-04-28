"""
gemini_api_utils.py
──────────────────
Utilities for managing Gemini API keys with fallback logic.

When GOOGLE_API_KEY quota is exhausted, automatically falls back to GOOGLE_API_KEY2.
Cycles back to GOOGLE_API_KEY once it's available again.

Loads all keys from .env file (uses python-dotenv).
"""

import os
import logging
from typing import Tuple, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file at module import time
load_dotenv()

# Track which key is currently active (for cycling)
_current_key_index = 0


def get_all_api_keys() -> list:
    """
    Get all configured Gemini API keys in priority order.
    
    Returns:
        List of available API keys
    
    Keys checked (in order):
        1. GOOGLE_API_KEY
        2. GOOGLE_API_KEY2
        3. GOOGLE_API_KEY3
        4. GOOGLE_API_KEY4
        5. GOOGLE_API_KEY5
        6. GEMINI_KEY
    """
    keys = []
    
    for i in range(1, 6):  # Check GOOGLE_API_KEY through GOOGLE_API_KEY5
        key = os.getenv(f"GOOGLE_API_KEY{i if i > 1 else ''}")
        if key:
            keys.append(key)
    
    # Also check GEMINI_KEY
    gemini_key = os.getenv("GEMINI_KEY")
    if gemini_key:
        keys.append(gemini_key)
    
    return keys


def get_gemini_api_key() -> str:
    """
    Get Gemini API key with fallback logic from .env file.
    
    Returns:
        Active API key (first available from configured keys)
    
    Priority:
        1. GOOGLE_API_KEY (primary)
        2. GOOGLE_API_KEY2 (backup)
        3. GOOGLE_API_KEY3 (tertiary)
        4. GOOGLE_API_KEY4 (quaternary)
        5. GOOGLE_API_KEY5 (quinary)
        6. GEMINI_KEY (fallback)
    """
    keys = get_all_api_keys()
    
    if not keys:
        raise ValueError(
            "No Gemini API keys found in .env file. Set one of: "
            "GOOGLE_API_KEY, GOOGLE_API_KEY2, GOOGLE_API_KEY3, GOOGLE_API_KEY4, GOOGLE_API_KEY5, or GEMINI_KEY"
        )
    
    return keys[0]


def get_gemini_api_keys_with_fallback() -> Tuple[str, Optional[str]]:
    """
    Get primary and fallback Gemini API keys from .env file.
    
    Returns:
        Tuple of (primary_key, fallback_key)
        fallback_key could be None if only one key is configured.
    """
    keys = get_all_api_keys()
    
    if len(keys) == 0:
        raise ValueError(
            "No Gemini API keys found. Set one of: "
            "GOOGLE_API_KEY, GOOGLE_API_KEY2, GOOGLE_API_KEY3, GOOGLE_API_KEY4, GOOGLE_API_KEY5, or GEMINI_KEY"
        )
    elif len(keys) == 1:
        return keys[0], None
    else:
        return keys[0], keys[1]


def is_quota_error(error: Exception) -> bool:
    """
    Check if error is due to API quota/token exhaustion.
    
    Returns True for quota-related errors like:
      - Daily quota exhausted
      - Rate limit exceeded
      - Token limit exceeded
    """
    error_str = str(error).lower()
    
    quota_indicators = [
        "quota",
        "limit",
        "exhausted",
        "rate limit",
        "token limit",
        "403",  # Forbidden
        "429",  # Too Many Requests
        "per_day",
        "perday",
        "regenerating tokens",
        "resource_exhausted",
    ]
    
    return any(indicator in error_str for indicator in quota_indicators)


def rotate_api_key(current_key: str) -> str:
    """
    Rotate to the next available API key when current one is exhausted.
    
    Args:
        current_key: The key that just failed
    
    Returns:
        The next key to try
    
    Cycles through all available keys:
        GOOGLE_API_KEY → GOOGLE_API_KEY2 → GOOGLE_API_KEY3 → 
        GOOGLE_API_KEY4 → GOOGLE_API_KEY5 → GEMINI_KEY → GOOGLE_API_KEY (repeat)
    """
    keys = get_all_api_keys()
    
    if not keys:
        raise ValueError("No API keys available to rotate to")
    
    # Find current key index and rotate to next
    try:
        current_index = keys.index(current_key)
        next_index = (current_index + 1) % len(keys)
        next_key = keys[next_index]
        logger.warning(f"Rotating API key (attempt {next_index + 1}/{len(keys)})")
        return next_key
    except ValueError:
        # Current key not found, start from beginning
        logger.warning("Current key not found in rotation list, starting from beginning")
        return keys[0]
