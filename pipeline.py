"""
Main orchestration.

Pulls together Google News fetch, PR scraping, keyword filter, AI filter,
deduplication and classification into a single callable. Emits granular
**stage events** so the UI can show what's happening in real time:

    stage_cb(stage_id, state, label, detail=None)

    stage_id  : "google_fetch" | "pr_scrape" | "date_filter" |
                "keyword_filter" | "ai_filter" | "dedupe" | "classify"
    state     : "running" | "complete" | "skipped" | "error"

Return value: (records, failures, info)
    info["ai"]    = AI filter info dict from ai_filter_batch()
    info["stages"] = list of {id, state, label, detail}
"""
import os
from datetime import date, datetime
from typing import Callable, List, Dict, Optional, Tuple

from dotenv import load_dotenv

from config import COMPANIES, PR_WEBSITES
from google_news import fetch_google_news
from pr_scraper import scrape_pr_websites
from filters import keyword_is_relevant, classify_news_type, classify_hot, deduplicate
from ai_filter import ai_filter_batch
from logger import logger

load_dotenv()


def run_pipeline(
    start_date: date,
    end_date: date,
    use_ai_filter: bool = True,
    use_google: bool = True,
    use_pr: bool = True,
    include_undated: bool = True,
    google_progress_cb: Optional[Callable[[str, int, int], None]] = None,
    pr_progress_cb: Optional[Callable[[str, int, int], None]] = None,
    pr_failure_cb: Optional[Callable[[Dict], None]] = None,
    ai_progress_cb: Optional[Callable[[int, int, str], None]] = None,
    stage_cb: Optional[Callable[[str, str, str, Optional[str]], None]] = None,
) -> Tuple[List[Dict], List[Dict], Dict]:
    """Run the full DNL pipeline. Returns (final_records, failures, info)."""

    info: Dict = {"ai": {}, "stages": []}

    def _stage(stage_id: str, state: str, label: str, detail: Optional[str] = None):
        """Emit a stage event AND record it for later reference."""
        info["stages"].append(
            {"id": stage_id, "state": state, "label": label, "detail": detail}
        )
        logger.info(f"[STAGE] {stage_id} → {state} :: {label} {detail or ''}")
        if stage_cb:
            try:
                stage_cb(stage_id, state, label, detail)
            except Exception:
                pass

    logger.info(f"Pipeline started: {start_date} → {end_date}")

    # =====================================================================
    # 1) Google News fetch (date filtering happens inside, per-entry)
    # =====================================================================
    raw_google: List[Dict] = []
    if use_google:
        _stage("google_fetch", "running", "Fetching Google News RSS feeds")
        raw_google = fetch_google_news(
            COMPANIES, start_date, end_date, progress_callback=google_progress_cb
        )
        _stage(
            "google_fetch", "complete",
            f"Google News: {len(raw_google)} headlines in date range",
            detail=f"{len(COMPANIES)} companies scanned",
        )
    else:
        _stage("google_fetch", "skipped", "Google News disabled")

    # =====================================================================
    # 2) PR / Company website scrape
    # =====================================================================
    raw_pr: List[Dict] = []
    failures: List[Dict] = []
    if use_pr:
        _stage("pr_scrape", "running", "Scraping PR / Company websites")
        raw_pr, failures = scrape_pr_websites(
            PR_WEBSITES, start_date, end_date,
            progress_callback=pr_progress_cb,
            failure_callback=pr_failure_cb,
            include_undated=include_undated,
        )
        _stage(
            "pr_scrape", "complete",
            f"PR Websites: {len(raw_pr)} headlines",
            detail=f"{len(PR_WEBSITES)} sites scanned, {len(failures)} failures",
        )
    else:
        _stage("pr_scrape", "skipped", "PR scraping disabled")

    all_records = raw_google + raw_pr

    # =====================================================================
    # 3) Date range filter (already applied inside fetchers — emit a clean
    #    confirmation stage so the UI shows it explicitly)
    # =====================================================================
    _stage(
        "date_filter", "complete",
        f"Date range applied: {start_date} → {end_date}",
        detail=f"{len(all_records)} records in range",
    )

    # =====================================================================
    # 4) Keyword filter (Stage 1)
    # =====================================================================
    _stage("keyword_filter", "running", "Applying keyword relevancy filter")
    keyword_filtered = [
        r for r in all_records if keyword_is_relevant(r.get("headline", ""))
    ]
    _stage(
        "keyword_filter", "complete",
        f"Keyword filter: {len(keyword_filtered)} of {len(all_records)} kept",
    )

    # =====================================================================
    # 5) AI filter (Stage 2, optional, fail-open)
    # =====================================================================
    api_key_present = bool(os.getenv("GROQ_API_KEY"))
    if use_ai_filter and api_key_present:
        _stage("ai_filter", "running", "Running AI relevancy filter (Groq)")
        # Build list of unreachable companies (any site that failed) so AI
        # can be informed and asked to deep-scan its own knowledge.
        unreachable = [
            {"company": f["company"], "url": f["url"], "reason": f.get("category", "unknown")}
            for f in failures
        ]
        ai_filtered, ai_info = ai_filter_batch(
            keyword_filtered,
            unreachable_sites=unreachable,
            date_range=(start_date, end_date),
            progress_callback=ai_progress_cb,
        )
        info["ai"] = ai_info
        if ai_info.get("used"):
            ai_state = "complete"
            ai_label = (
                f"AI filter: kept {ai_info['kept']} of {ai_info['input']} "
                f"({ai_info.get('model','groq')})"
            )
        else:
            ai_state = "error"
            ai_label = "AI filter failed — fell back to keyword results"
        _stage("ai_filter", ai_state, ai_label, detail=ai_info.get("reason"))
    else:
        ai_filtered = keyword_filtered
        for r in ai_filtered:
            r.setdefault("ai_relevant", True)
            r.setdefault("ai_reason", "AI filter not run")
        if not use_ai_filter:
            reason = "AI filter disabled in UI"
        else:
            reason = "GROQ_API_KEY not set — switched to keyword-only filtering"
        info["ai"] = {
            "used": False, "attempted": False, "reason": reason,
            "model": "", "batches": 0, "errors": 0,
            "input": len(keyword_filtered), "kept": len(keyword_filtered),
        }
        _stage("ai_filter", "skipped", reason)

    # =====================================================================
    # 6) Deduplicate
    # =====================================================================
    _stage("dedupe", "running", "Removing duplicate headlines")
    deduped = deduplicate(ai_filtered)
    _stage(
        "dedupe", "complete",
        f"Dedupe: {len(deduped)} unique records "
        f"({len(ai_filtered) - len(deduped)} duplicates removed)",
    )

    # =====================================================================
    # 7) Classify (HOT + News Type) and enrich
    # =====================================================================
    _stage("classify", "running", "Classifying news types & HOT tags")
    today_str = datetime.now().strftime("%Y-%m-%d")
    hot_count = 0
    for idx, r in enumerate(deduped, start=1):
        head = r.get("headline", "")
        r["news_type"] = classify_news_type(head)
        r["hot"] = classify_hot(head)
        if r["hot"] == "HOT":
            hot_count += 1
        r["serial_number"] = idx
        r["date_collected"] = today_str
    _stage(
        "classify", "complete",
        f"Classified {len(deduped)} records ({hot_count} HOT)",
    )

    logger.info(f"Pipeline complete: {len(deduped)} final records")
    return deduped, failures, info
