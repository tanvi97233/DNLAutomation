"""
Google News RSS fetcher.

Builds a Google News RSS URL per company, parses it with feedparser,
filters entries by user-selected publication date range.
"""
from datetime import date, datetime
from typing import Callable, List, Dict, Optional
from urllib.parse import quote_plus

import feedparser
from dateutil import parser as dateparser

from logger import logger


GNEWS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}"
    "&hl=en-US&gl=US&ceid=US:en"
)


def _build_query(company: str) -> str:
    """Build the Google News RSS URL for a single company."""
    # Quote the company name and add diagnostic-flavoured keywords
    raw = f'"{company}" diagnostics OR allergy OR immunology'
    return GNEWS_TEMPLATE.format(query=quote_plus(raw))


def _parse_date(entry) -> Optional[date]:
    """Try to parse publication date from a feedparser entry."""
    # Prefer the structured time tuple if present
    for field in ("published_parsed", "updated_parsed"):
        tup = entry.get(field)
        if tup:
            try:
                return datetime(*tup[:6]).date()
            except Exception:
                pass
    # Fall back to text parsing
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return dateparser.parse(raw).date()
            except Exception:
                pass
    return None


def fetch_google_news(
    companies: List[str],
    start_date: date,
    end_date: date,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> List[Dict]:
    """Fetch + date-filter Google News RSS results for every company."""
    records: List[Dict] = []
    total = len(companies)

    for idx, company in enumerate(companies, start=1):
        if progress_callback:
            try:
                progress_callback(company, idx, total)
            except Exception:
                pass

        url = _build_query(company)
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.warning(f"[GNews] {company}: feed parse failed: {e}")
            continue

        if getattr(feed, "bozo", False) and not feed.entries:
            logger.warning(f"[GNews] {company}: feed empty or malformed")
            continue

        matched = 0
        for entry in feed.entries:
            pub = _parse_date(entry)
            if pub is None:
                continue
            if pub < start_date or pub > end_date:
                continue

            headline = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not headline or not link:
                continue

            records.append({
                "company": company,
                "headline": headline,
                "date": pub.strftime("%Y-%m-%d"),
                "url": link,
                "source_type": "Google News",
            })
            matched += 1

        logger.info(
            f"[GNews] {company}: {matched}/{len(feed.entries)} entries in range"
        )

    return records
