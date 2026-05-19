"""
Keyword pre-filter, news type classifier, HOT tagger, deduplicator.

All matching is case-insensitive. These are deterministic, no-network
functions intended to run before (and sometimes instead of) the AI filter.
"""
from typing import List, Dict

from config import (
    RELEVANT_KEYWORDS,
    EXCLUDE_KEYWORDS,
    HOT_KEYWORDS,
    NEWS_TYPE_RULES,
)


def _contains_any(text: str, vocab) -> bool:
    """Case-insensitive substring match against a list of phrases."""
    t = (text or "").lower()
    return any(k.lower() in t for k in vocab)


def keyword_is_relevant(text: str) -> bool:
    """Stage-1 relevancy gate: True if text is in-scope based on keywords."""
    if not text:
        return False
    # Hard exclusions win
    if _contains_any(text, EXCLUDE_KEYWORDS):
        return False
    return _contains_any(text, RELEVANT_KEYWORDS)


def classify_news_type(text: str) -> str:
    """Return the first matching news category, or 'Other'."""
    t = (text or "").lower()
    for category, triggers in NEWS_TYPE_RULES.items():
        if any(trig.lower() in t for trig in triggers):
            return category
    return "Other"


def classify_hot(text: str) -> str:
    """Return 'HOT' if a HOT keyword is present, else 'Non-Hot'."""
    return "HOT" if _contains_any(text, HOT_KEYWORDS) else "Non-Hot"


def deduplicate(records: List[Dict]) -> List[Dict]:
    """Drop duplicates based on (company, first 80 chars of headline)."""
    seen = set()
    out = []
    for r in records:
        company = (r.get("company") or "").lower().strip()
        headline = (r.get("headline") or "").lower().strip()[:80]
        key = (company, headline)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
