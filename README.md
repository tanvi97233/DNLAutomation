# DNL Automation Tool

hey

It replaces two manual processes:

1. **PR / Company Website screening** — automated HTML scraping of ~49 press
   release pages with date-range filtering.
2. **Google News screening** — automated fetching via Google News RSS for
   ~44 monitored companies.

Records are then keyword-filtered, optionally AI-filtered by Claude, deduped,
classified (news type + HOT vs Non-Hot) and exported to a formatted Excel
file with a Summary sheet.

---

## Prerequisites

- Python **3.11+**
- Internet connection
- (Optional) Anthropic API key for AI relevancy filtering

---

## Setup

```powershell
# 1) Create a virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Install dependencies
pip install -r requirements.txt

# 3) Configure environment
copy .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

---

## Run

```powershell
streamlit run app.py
```

Streamlit will open the UI in your browser (default: http://localhost:8501).

---

## Usage walkthrough

1. Pick a **start** and **end** date in the sidebar.
2. Toggle which **sources** to use: Google News RSS, PR Websites, or both.
3. Toggle the **AI Relevancy Filter** (Claude). If you have no API key it
   will be skipped automatically and only the keyword filter runs.
4. Click **🚀 Run Newsletter Scan**.
5. Watch the progress bar — Google News covers 0–50%, PR scraping 50–100%.
6. When the scan finishes you get:
   - Summary metrics (Total, HOT, Google count, PR count)
   - A **Download Excel Report** button
   - A filterable preview table
   - An expander listing any sites that failed to scrape

---

## Excel output columns

| # | Column            | Description                                     |
|---|-------------------|-------------------------------------------------|
| 1 | Serial Number     | Sequential ID                                   |
| 2 | Company Name      | Company associated with the article             |
| 3 | Date              | Publication date (YYYY-MM-DD)                   |
| 4 | News Type         | M&A, Regulatory, Product Launch, Partnership, Conference, Organizational, Financial, Other |
| 5 | Headline          | Article headline                                |
| 6 | Source Link       | Clickable hyperlink to the article              |
| 7 | Source Type       | "Google News" or "PR Website"                   |
| 8 | Hot vs Non-Hot    | HOT (yellow row) or Non-Hot                     |
| 9 | Date Collected    | The date the scan was run                       |

A second sheet, **Summary**, lists totals, HOT count, and per-news-type counts.

---

## Adding a new company or PR website

All data lives in [`config.py`](config.py):

- Add the company name to `COMPANIES` (used by Google News search).
- Add a `{"company": "...", "url": "..."}` entry to `PR_WEBSITES` (used by
  the PR scraper).

No code changes needed elsewhere.

---

## Tuning relevancy

`config.py` exposes:

- `RELEVANT_KEYWORDS` — terms that pass an article through the keyword gate
- `EXCLUDE_KEYWORDS` — hard exclusions (e.g. unrelated drug categories)
- `HOT_KEYWORDS` — triggers for the HOT tag
- `NEWS_TYPE_RULES` — category → trigger keywords

The AI filter (`ai_filter.py`) understands business context and corrects
keyword false-positives/negatives. It fails open — on any API or parse
error, records are kept rather than silently dropped.

---

## Known limitations

- **JS-heavy sites**: the MVP uses `requests` + `BeautifulSoup` only.
  Sites that render news content client-side (React/Vue/Angular SPAs with
  no server HTML) will return empty results. Add Playwright in a v2.
- **Date extraction is heuristic**: some sites have unusual date formats
  that the cascading parser may miss; those articles will be silently
  skipped (they appear as zero matches in the log).
- **Google News RSS** sometimes returns aggregator URLs; the final URL
  often redirects to the publisher on click.
- The AI filter requires `ANTHROPIC_API_KEY`. Without it, only keyword
  filtering runs (the tool still works end-to-end).

---

## Project layout

```
dnl_tool/
├── app.py              ← Streamlit UI
├── pipeline.py         ← Orchestration
├── google_news.py      ← Google News RSS fetcher
├── pr_scraper.py       ← PR website scraper
├── filters.py          ← Keyword/news-type/HOT/dedupe
├── ai_filter.py        ← Claude AI relevancy filter
├── exporter.py         ← Excel writer
├── config.py           ← All data (companies, URLs, keywords)
├── logger.py           ← Daily log files in logs/
├── requirements.txt
├── .env.example
├── README.md
├── logs/               ← auto-created
└── output/             ← auto-created — Excel exports land here
```
