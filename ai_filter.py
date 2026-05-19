"""
AI relevancy filter — powered by Groq (OpenAI-compatible API).

Endpoint: https://api.groq.com/openai/v1/chat/completions
No SDK needed — just `requests`.

Env:
  GROQ_API_KEY  — required to enable AI filtering
  GROQ_MODEL    — optional override (default: llama-3.3-70b-versatile)

Behaviour:
  * If GROQ_API_KEY is not set → AI filter is SKIPPED (records pass through,
    flagged with ai_reason="AI filter skipped (no API key)").
  * On any API or JSON error → FAIL OPEN (records in that batch are kept
    so we never silently drop data).
  * Returns `(filtered_records, info)` so the UI can show a clear alert
    indicating whether AI actually ran or fell back to keyword-only.
"""
import json
import os
import re
from typing import Dict, List, Tuple

import requests

from logger import logger


GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
REQUEST_TIMEOUT_SEC = 90

SYSTEM_PROMPT = """You are an intelligence analyst preparing a Daily Newsletter (DNL) for a specialty diagnostics business unit focused on immunodiagnostics, allergy, and autoimmune testing.

Your job is to classify headlines as RELEVANT or NOT RELEVANT for the Daily Newsletter (DNL).

IN SCOPE (relevant):
- Immunodiagnostics, allergy diagnostics, autoimmune diagnostics
- Immunoassays (ELISA, lateral flow, multiplex, serology)
- Diagnostic platforms / analyzers / reagents / test kits
- Infectious disease diagnostics, point-of-care (POC) diagnostics, IVD
- Laboratory solutions
- Allergen immunotherapy / allergy therapeutics (these companies are INTENTIONALLY in scope: ALK, Stallergenes Greer, Aimmune, DBV, Allergy Therapeutics)
- Strategic events on monitored companies: M&A, partnerships, regulatory approvals (FDA, CE, 510k), product launches, conference participation (EAACI, AAAAI, ACAAI), leadership changes, strategic financial results

OUT OF SCOPE (not relevant):
- Generic pharma news (cardiovascular, oncology, diabetes, obesity)
- Biosimilars or unrelated drug approvals
- General hospital / healthcare system news
- Unrelated clinical trials for drugs
- Mental health / psychiatry / neurology / orthopedic / dermatology / ophthalmology drugs
- Generic medical news with no link to diagnostics or allergy

Return ONLY a JSON array, no prose, no markdown fences. Each element:
{"headline": "<exact headline you were given>", "relevant": true|false, "reason": "<one short sentence>"}
"""


def _extract_json_array(text: str):
    """Pull the first JSON array out of a model response (tolerant of fences)."""
    text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```$", "", text.strip())
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON array found in response")
    return json.loads(text[start : end + 1])


def _call_groq(api_key: str, model: str, user_msg: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Single HTTP call to the Groq chat-completions endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt + '\n\nReturn the JSON array under a key called "results".'},
            {"role": "user", "content": user_msg},
        ],
    }
    r = requests.post(
        GROQ_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SEC
    )
    if r.status_code >= 400:
        body = (r.text or "")[:500]
        raise requests.HTTPError(
            f"HTTP {r.status_code} from Groq: {body}", response=r
        )
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Unexpected Groq response shape ({e}): {json.dumps(data)[:400]}"
        )


def _parse_verdicts(text: str):
    """Parse Groq output: prefer {"results":[...]} JSON-object form, fall back to bare array."""
    text = text.strip()
    # Try JSON object first (response_format=json_object guarantees an object)
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ("results", "verdicts", "classifications", "data"):
                if key in obj and isinstance(obj[key], list):
                    return obj[key]
            # Some models stash the array under the first list-valued key
            for v in obj.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass
    # Fallback to tolerant array extraction
    return _extract_json_array(text)


def ai_filter_batch(
    records: List[Dict],
    batch_size: int = 20,
    unreachable_sites: List[Dict] = None,
    date_range: Tuple = None,
    progress_callback: callable = None,
) -> Tuple[List[Dict], Dict]:
    """Filter records using Groq. Returns (kept_records, info).

    Parameters
    ----------
    unreachable_sites : list of {company, url, reason}
        PR sites that failed during scraping. The AI is told about them so
        it can flag known announcements from its own training knowledge.
    date_range : (start_date, end_date)
        Used purely to make the AI prompt explicit about the window.
    progress_callback : (batch_idx, total_batches, status) -> None
        Fires before each batch (status="running") and after (status="done"|"error").
    """
    info: Dict = {
        "used": False,
        "attempted": False,
        "reason": "",
        "error_detail": "",
        "model": "",
        "batches": 0,
        "errors": 0,
        "input": len(records),
        "kept": 0,
        "system_prompt": "",
        "unreachable_addendum": "",
        "unreachable_count": 0,
    }

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    # ----- Build augmented system prompt -----
    system_prompt = SYSTEM_PROMPT
    addendum_parts = []
    if date_range:
        addendum_parts.append(
            f"\n\nDATE RANGE OF INTEREST: {date_range[0]} → {date_range[1]}."
        )
    if unreachable_sites:
        info["unreachable_count"] = len(unreachable_sites)
        site_lines = "\n".join(
            f"- {s['company']} ({s.get('reason','unknown')}): {s['url']}"
            for s in unreachable_sites[:60]  # safety cap
        )
        addendum_parts.append(
            "\n\nUNREACHABLE PR SITES (could not be scraped this run):\n"
            + site_lines
            + "\n\nFor these companies, draw on your own knowledge: if you are "
            "aware of any significant announcements (M&A, regulatory approvals, "
            "product launches, partnerships, leadership changes, conference "
            "presentations, financial results) within the date range above, "
            "include a synthetic entry in the JSON output with "
            '"headline" describing what you know, "relevant": true, '
            '"reason": "AI-knowledge (site unreachable)", and an extra key '
            '"ai_synthesized": true. If you are NOT aware of anything, do '
            "not invent results — simply omit those companies. Never fabricate."
        )
    if addendum_parts:
        system_prompt = SYSTEM_PROMPT + "".join(addendum_parts)
    info["system_prompt"] = system_prompt
    info["unreachable_addendum"] = "".join(addendum_parts)

    # ----- No API key → skip cleanly -----
    if not api_key:
        msg = "GROQ_API_KEY not set — AI filter skipped, using keyword filter only."
        logger.info(f"[AI] {msg}")
        info["reason"] = msg
        for r in records:
            r["ai_relevant"] = True
            r["ai_reason"] = "AI filter skipped (no API key)"
        info["kept"] = len(records)
        return records, info

    info["attempted"] = True
    info["model"] = model
    kept: List[Dict] = []
    total_batches = (len(records) + batch_size - 1) // batch_size

    for batch_idx, batch_start in enumerate(range(0, len(records), batch_size), start=1):
        batch = records[batch_start : batch_start + batch_size]
        info["batches"] += 1
        if progress_callback:
            try:
                progress_callback(batch_idx, total_batches, "running")
            except Exception:
                pass
        payload = [
            {"company": r.get("company", ""), "headline": r.get("headline", "")}
            for r in batch
        ]
        user_msg = (
            f"Classify the following {len(payload)} headlines. "
            'Return a JSON object: {"results": [ ... ]} where each element is '
            '{"headline": "...", "relevant": true|false, "reason": "..."}.\n\n'
            + json.dumps(payload, ensure_ascii=False)
        )

        try:
            text = _call_groq(api_key, model, user_msg, system_prompt=system_prompt)
            verdicts = _parse_verdicts(text)
        except Exception as e:
            info["errors"] += 1
            err_str = str(e)[:400]
            if not info["error_detail"]:
                info["error_detail"] = err_str
            logger.warning(
                f"[AI] batch {batch_idx}/{total_batches} failed ({err_str}); "
                "keeping records (fail-open)."
            )
            for r in batch:
                r["ai_relevant"] = True
                r["ai_reason"] = f"AI error: {type(e).__name__}"
                kept.append(r)
            if progress_callback:
                try:
                    progress_callback(batch_idx, total_batches, "error")
                except Exception:
                    pass
            continue

        # Map verdicts back to records by headline
        by_headline = {}
        synthesized = []  # new entries the AI created for unreachable sites
        for v in verdicts:
            if not isinstance(v, dict) or "headline" not in v:
                continue
            if v.get("ai_synthesized") is True:
                synthesized.append(v)
            else:
                by_headline[v["headline"].strip().lower()] = v

        for r in batch:
            v = by_headline.get((r.get("headline") or "").strip().lower())
            if v is None:
                r["ai_relevant"] = True
                r["ai_reason"] = "no verdict returned"
                kept.append(r)
                continue
            relevant = bool(v.get("relevant", True))
            r["ai_relevant"] = relevant
            r["ai_reason"] = str(v.get("reason", ""))[:200]
            if relevant:
                kept.append(r)

        # Append AI-synthesized records (from its own knowledge) for
        # unreachable PR sites.
        from datetime import date as _date
        today_str = _date.today().strftime("%Y-%m-%d")
        for v in synthesized:
            kept.append({
                "company": str(v.get("company", "Unknown"))[:120],
                "headline": str(v.get("headline", ""))[:500],
                "date": today_str,
                "url": "",
                "source_type": "AI Knowledge (site unreachable)",
                "ai_relevant": True,
                "ai_reason": str(v.get("reason", "AI-synthesized"))[:200],
                "ai_synthesized": True,
            })
        if synthesized:
            info["synthesized_count"] = info.get("synthesized_count", 0) + len(synthesized)

        if progress_callback:
            try:
                progress_callback(batch_idx, total_batches, "done")
            except Exception:
                pass

    info["kept"] = len(kept)

    # ----- Decide overall status -----
    if info["errors"] == 0:
        info["used"] = True
        info["reason"] = (
            f"AI filter ({model}) ran on {info['batches']} batch(es). "
            f"Kept {info['kept']} of {info['input']}."
        )
    elif info["errors"] == info["batches"]:
        info["used"] = False
        hint = ""
        d = info.get("error_detail", "").lower()
        if "429" in d or "rate" in d or "quota" in d:
            hint = " Groq rate-limit hit — wait a minute and retry."
        elif "401" in d or "invalid api key" in d or "unauthorized" in d:
            hint = " Groq returned 401 — the API key is invalid or revoked."
        elif "403" in d or "forbidden" in d:
            hint = " Groq returned 403 — check API key permissions."
        elif "model" in d and ("not found" in d or "decommission" in d or "does not exist" in d):
            hint = f" Model '{model}' was rejected — try GROQ_MODEL=llama-3.1-8b-instant in .env."
        info["reason"] = (
            f"AI filter FAILED for all {info['batches']} batches — "
            "falling back to keyword-only results." + hint
        )
    else:
        info["used"] = True
        info["reason"] = (
            f"AI filter ({model}) partially worked: "
            f"{info['errors']}/{info['batches']} batches failed — "
            "failed batches kept as-is."
        )

    logger.info(f"[AI] {info['reason']}")
    return kept, info
