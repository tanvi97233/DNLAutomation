"""
Generic PR / company website scraper.

Strategy (anchor-driven, much more tolerant than a fixed container search):
  1. Fetch the page with requests; parse with BeautifulSoup (lxml).
  2. Collect every <a> tag whose text looks like a real headline
     (15..500 chars, not navigation / boilerplate).
  3. For each anchor, walk up the ancestor chain (up to 4 levels) AND scan
     siblings looking for a publication date using a cascading strategy:
       a) HTML date attributes (datetime, data-date, data-published, content)
       b) <time> tags
       c) Children with date-like class names ("date", "published", ...)
       d) Regex patterns on raw text (ISO, US, EU, numeric)
  4. Articles whose extracted date is inside the user range are kept.
  5. If `include_undated=True` and a page yields anchor candidates but NO
     parseable dates, the top N candidates are still included (date set
     to today, flagged date_estimated=True). This is the practical
     fallback for SPA / JS-rendered news pages with no machine-readable
     date metadata.

Per the MVP requirements: no Playwright / Selenium — JS-only sites whose
body has no headlines in raw HTML will still return zero results.
"""
import re
import time
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from config import HEADERS, REQUEST_TIMEOUT
from logger import logger


# --- Date patterns (cascading regex fallback) -------------------------------
_DATE_PATTERNS = [
    # ISO 2024-03-15
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    # US: March 15, 2024  /  Mar 15, 2024
    re.compile(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    ),
    # EU: 15 March 2024
    re.compile(
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})\b",
        re.IGNORECASE,
    ),
    # Numeric 15/03/2024
    re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b"),
]

_DATE_CLASS_HINTS = (
    "date", "published", "pub-date", "pubdate", "timestamp", "time", "posted",
)

# Anchor-text noise we never want to treat as headlines
_NOISE_RE = re.compile(
    r"^(home|news|press|releases?|menu|search|login|sign in|sign up|subscribe|"
    r"contact|cookie|privacy|terms|imprint|read more|learn more|more|back|next|"
    r"previous|all|view all|see all|share|download|english|deutsch|français|"
    r"about|careers|investors|products|solutions|support|events)$",
    re.IGNORECASE,
)


def _try_parse(raw: str) -> Optional[date]:
    """Best-effort string → date. Returns None on failure or implausible date."""
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) < 6 or len(raw) > 60:
        return None
    try:
        d = dateparser.parse(raw, fuzzy=True).date()
    except Exception:
        return None
    if d.year < 2000 or d.year > date.today().year + 1:
        return None
    return d


def _date_from_attrs(el) -> Optional[date]:
    """Check element's own date-ish attributes."""
    if not hasattr(el, "get"):
        return None
    for attr in ("datetime", "data-date", "data-published", "data-time", "content"):
        v = el.get(attr)
        if v:
            d = _try_parse(v)
            if d:
                return d
    return None


def _date_from_text(text: str) -> Optional[date]:
    """Run regex patterns over raw text and parse the first hit."""
    if not text:
        return None
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            d = _try_parse(m.group(1))
            if d:
                return d
    return None


def _date_from_element(el, max_text: int = 1500) -> Optional[date]:
    """Cascading date extraction inside one element (no ancestor walk)."""
    if el is None or not hasattr(el, "find_all"):
        return None

    # 1) Direct attributes
    d = _date_from_attrs(el)
    if d:
        return d

    # 2) <time> descendants
    for t in el.find_all("time", limit=6):
        d = _date_from_attrs(t)
        if d:
            return d
        d = _try_parse(t.get_text(" ", strip=True))
        if d:
            return d

    # 3) Date-class descendants
    for cand in el.find_all(True, limit=40):
        cls = " ".join(cand.get("class") or []).lower()
        if not any(hint in cls for hint in _DATE_CLASS_HINTS):
            continue
        d = _date_from_attrs(cand)
        if d:
            return d
        d = _try_parse(cand.get_text(" ", strip=True))
        if d:
            return d

    # 4) Regex over text
    return _date_from_text(el.get_text(" ", strip=True)[:max_text])


def _find_date_for_anchor(a) -> Optional[date]:
    """Walk up ancestors + scan siblings to locate a date near the anchor."""
    d = _date_from_element(a, max_text=400)
    if d:
        return d

    # Ancestors (up to 4 levels)
    parent = a.parent
    for _ in range(4):
        if parent is None or parent.name in ("body", "html"):
            break
        d = _date_from_element(parent, max_text=1500)
        if d:
            return d
        parent = parent.parent

    # Siblings (often a date sits right beside the link)
    sib = a.find_previous_sibling()
    for _ in range(3):
        if sib is None:
            break
        d = _date_from_element(sib, max_text=400)
        if d:
            return d
        sib = sib.find_previous_sibling()

    sib = a.find_next_sibling()
    for _ in range(3):
        if sib is None:
            break
        d = _date_from_element(sib, max_text=400)
        if d:
            return d
        sib = sib.find_next_sibling()

    return None


def _is_internal_link(href: str, base_netloc: str) -> bool:
    """Keep only links plausibly leading to an article on the same site."""
    if not href:
        return False
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return False
    if href.startswith("/"):
        return True
    parsed = urlparse(href)
    if not parsed.netloc:
        return True  # relative
    # Allow same registrable domain
    return base_netloc.split(".")[-2:] == parsed.netloc.split(".")[-2:]


def _collect_anchor_candidates(soup, base_url: str) -> List:
    """Return list of (anchor_tag, headline_text, absolute_url) tuples."""
    base_netloc = urlparse(base_url).netloc
    out = []
    seen_texts = set()

    for a in soup.find_all("a", href=True, limit=2000):
        href = a["href"].strip()
        if not _is_internal_link(href, base_netloc):
            continue

        # Prefer header tags inside the anchor for the headline
        headline = None
        for tag in ("h1", "h2", "h3", "h4", "h5"):
            h = a.find(tag)
            if h:
                txt = h.get_text(" ", strip=True)
                if 15 <= len(txt) <= 500:
                    headline = txt
                    break
        if not headline:
            txt = a.get_text(" ", strip=True)
            if 15 <= len(txt) <= 500 and not _NOISE_RE.match(txt):
                headline = txt

        if not headline:
            continue

        # Local dedupe — many sites wrap headlines in multiple anchors
        key = headline.lower()[:80]
        if key in seen_texts:
            continue
        seen_texts.add(key)

        abs_url = urljoin(base_url, href)
        out.append((a, headline, abs_url))

    return out


def _classify_failure(exc: Exception) -> Tuple[str, str]:
    """Classify a request exception into (short_category, human_detail)."""
    # HTTPError has a response with status_code
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code == 404:
            return ("HTTP 404 — Page not found", "The URL returned 404 (page missing or moved).")
        if code == 403:
            return ("HTTP 403 — Forbidden", "Site blocked the request (anti-bot or auth required).")
        if code == 410:
            return ("HTTP 410 — Gone", "URL has been permanently removed.")
        if 500 <= code < 600:
            return (f"HTTP {code} — Server error", "Remote server returned an error.")
        return (f"HTTP {code}", f"Unexpected HTTP status {code}.")
    if isinstance(exc, requests.ConnectionError):
        s = str(exc).lower()
        if "nodename nor servname" in s or "name or service not known" in s or "getaddrinfo failed" in s:
            return ("Domain unreachable (DNS)", "DNS lookup failed — likely a transient network/DNS issue (check your internet/VPN).")
        if "ssl" in s or "certificate" in s:
            return ("SSL / certificate error", "Site has an invalid or expired SSL certificate.")
        if "refused" in s:
            return ("Connection refused", "Server actively refused the connection.")
        return ("Connection error", str(exc)[:160])
    if isinstance(exc, requests.Timeout):
        return ("Timeout", f"No response within {REQUEST_TIMEOUT}s.")
    if isinstance(exc, requests.TooManyRedirects):
        return ("Too many redirects", "Site redirected in a loop.")
    return (type(exc).__name__, str(exc)[:160])


def scrape_pr_websites(
    pr_websites: List[Dict],
    start_date: date,
    end_date: date,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    failure_callback: Optional[Callable[[Dict], None]] = None,
    include_undated: bool = True,
    undated_cap: int = 15,
) -> Tuple[List[Dict], List[Dict]]:
    """Scrape every PR site. Returns (records, failures).

    Parameters
    ----------
    progress_callback : (company, idx, total) -> None
        Called BEFORE each site is attempted.
    failure_callback : (failure_dict) -> None
        Called IMMEDIATELY when a site fails so the UI can show it live.
        The dict has keys: company, url, category, error.
    include_undated : bool
        When True, if a page yields anchor candidates but ZERO of them
        carry a parseable date, the top `undated_cap` candidates are still
        included (date set to today, date_estimated=True).
    """
    records: List[Dict] = []
    failures: List[Dict] = []
    total = len(pr_websites)
    today_str = date.today().strftime("%Y-%m-%d")

    def _record_failure(company: str, url: str, category: str, detail: str):
        """Append a failure and fire the live callback."""
        f = {"company": company, "url": url, "category": category, "error": detail}
        failures.append(f)
        logger.warning(f"[PR FAIL] {company} ({url}): {category} — {detail}")
        if failure_callback:
            try:
                failure_callback(f)
            except Exception:
                pass

    for idx, site in enumerate(pr_websites, start=1):
        company = site["company"]
        url = site["url"]

        if progress_callback:
            try:
                progress_callback(company, idx, total)
            except Exception:
                pass

        # Skip LinkedIn / sites that block scraping by design
        host = urlparse(url).netloc.lower()
        if "linkedin.com" in host:
            _record_failure(
                company, url,
                "Non-compliant source (blocked)",
                "LinkedIn pages block scraping — skipped.",
            )
            continue

        # Retry transient network errors once (DNS/connection/timeout).
        resp = None
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                last_exc = None
                break
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt == 0:
                    time.sleep(1.5)
                    continue
            except Exception as e:
                last_exc = e
                break
        if last_exc is not None or resp is None:
            category, detail = _classify_failure(last_exc or Exception("Unknown error"))
            _record_failure(company, url, category, detail)
            continue

        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            _record_failure(company, url, "HTML parse error", str(e)[:160])
            continue

        candidates = _collect_anchor_candidates(soup, url)

        in_range = 0
        dated_count = 0
        undated_pool = []

        for a, headline, link in candidates:
            d = _find_date_for_anchor(a)
            if d is None:
                undated_pool.append((headline, link))
                continue
            dated_count += 1
            if d < start_date or d > end_date:
                continue
            records.append({
                "company": company,
                "headline": headline,
                "date": d.strftime("%Y-%m-%d"),
                "url": link,
                "source_type": "PR Website",
                "date_estimated": False,
            })
            in_range += 1

        # Fallback: page produced candidates but no dates anywhere.
        # Include the top N so the page isn't silently empty.
        used_undated = 0
        if include_undated and dated_count == 0 and undated_pool:
            for headline, link in undated_pool[:undated_cap]:
                records.append({
                    "company": company,
                    "headline": headline,
                    "date": today_str,
                    "url": link,
                    "source_type": "PR Website",
                    "date_estimated": True,
                })
            used_undated = min(len(undated_pool), undated_cap)

        logger.info(
            f"[PR] {company}: candidates={len(candidates)} "
            f"dated={dated_count} in_range={in_range} undated_used={used_undated}"
        )

    return records, failures
