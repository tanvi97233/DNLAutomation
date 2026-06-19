"""
Streamlit UI for the DNL Automation Tool.

Run with:
    streamlit run app.py
"""
import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from pipeline import run_pipeline
from exporter import export_to_excel
from config import (
    COMPANIES,
    PR_WEBSITES,
    RELEVANT_KEYWORDS,
    EXCLUDE_KEYWORDS,
    HOT_KEYWORDS,
    NEWS_TYPE_RULES,
)

load_dotenv()

st.set_page_config(
    page_title="DNL Automation Tool",
    page_icon="📰",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Simple login gate (hardcoded credentials for MVP)
# ---------------------------------------------------------------------------
# NOTE: Hardcoded creds are NOT secure for production. Move to env vars or a
# real identity provider before any non-internal release.
_AUTH_EMAIL = os.getenv("DNL_LOGIN_EMAIL", "dnladmin@automation.in")
_AUTH_PASSWORD = os.getenv("DNL_LOGIN_PASSWORD", "123456789")

if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False


def _render_login():
    st.markdown(
        """
        <div style='max-width:420px;margin:80px auto 24px auto;padding:32px;
        border-radius:12px;
        background:linear-gradient(135deg,#1B3A5C 0%,#2A5A8C 100%);
        color:#fff;text-align:center'>
        <h2 style='margin:0 0 8px 0;color:#fff'>📰 DNL Automation</h2>
        <div style='font-size:13px;opacity:0.9'>Sign in to continue</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="you@company.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "🔓 Sign in", use_container_width=True, type="primary"
            )
        if submitted:
            if (
                email.strip().lower() == _AUTH_EMAIL.lower()
                and password == _AUTH_PASSWORD
            ):
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("Invalid email or password.")


if not st.session_state.auth_ok:
    _render_login()
    st.stop()


# ---------------------------------------------------------------------------
# Theme polish
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
      .dnl-hero {
        background: linear-gradient(135deg, #1B3A5C 0%, #2A5A8C 100%);
        padding: 22px 28px;
        border-radius: 10px;
        color: #fff;
        margin-bottom: 18px;
      }
      .dnl-hero h1 { margin: 0; font-size: 28px; }
      .hot-metric div[data-testid="stMetricValue"] { color: #C62828; }
      .stage-row {
        padding: 10px 14px; border-radius: 8px; margin: 4px 0;
        border: 1px solid #E1E6ED; background: #FAFBFC;
        display:flex; justify-content:space-between; align-items:center;
        font-size: 14px;
        color: #1B1B1B !important;
      }
      .stage-row *    { color: #1B1B1B !important; }
      .stage-running  { background:#FFF3C4 !important; border-color:#E0A800 !important; }
      .stage-complete { background:#CDEBD3 !important; border-color:#2E7D32 !important; }
      .stage-skipped  { background:#E6E6E6 !important; border-color:#9E9E9E !important; }
      .stage-error    { background:#F8C9C9 !important; border-color:#B71C1C !important; }
      .stage-label    { font-weight:700; color:#1B1B1B !important; }
      .stage-detail   { font-size:12px; color:#3D3D3D !important; margin-top:2px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="dnl-hero">
      <h1>DNL Automation Tool</h1>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.caption(f"👤 Signed in as `{_AUTH_EMAIL}`")
    if st.button("🚪 Sign out", use_container_width=True):
        st.session_state.auth_ok = False
        st.rerun()
    st.divider()

    st.subheader("Date Range")
    default_start = date.today() - timedelta(days=3)
    default_end = date.today()
    start_date = st.date_input("Start date", value=default_start)
    end_date = st.date_input("End date", value=default_end)

    st.subheader("Sources")
    use_google = st.checkbox("Google News RSS", value=True)
    use_pr = st.checkbox("PR / Company Websites", value=True)
    include_undated = st.checkbox(
        "Include PR articles without a detectable date",
        value=True,
        help=(
            "Many press release pages don't expose machine-readable dates. "
            "With this on, the scraper still returns the top headlines from "
            "such pages (date will show today, flagged as estimated)."
        ),
    )

    st.subheader("AI Filtering")
    use_ai = st.checkbox("Enable AI Relevancy Filter (Groq)", value=True)
    has_key = bool(os.getenv("GROQ_API_KEY"))
    if use_ai and not has_key:
        st.warning(
            "⚠️ `GROQ_API_KEY` not detected in `.env`. AI filter will be "
            "skipped — keyword filter only."
        )
    elif use_ai and has_key:
        st.caption(f"✓ Groq key detected. Model: `{os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')}`")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
st.session_state.setdefault("records", None)
st.session_state.setdefault("failures", [])
st.session_state.setdefault("excel_path", None)
st.session_state.setdefault("pipeline_info", None)


# ---------------------------------------------------------------------------
# Stage definitions — these drive the live status board
# ---------------------------------------------------------------------------
STAGES = [
    ("google_fetch",   "📥  Google News fetch"),
    ("pr_scrape",      "🌐  PR website scrape"),
    ("date_filter",    "📅  Date range filter"),
    ("keyword_filter", "🔑  Keyword filter"),
    ("ai_filter",      "🤖  AI relevancy filter (Groq)"),
    ("dedupe",         "🧹  Deduplicate"),
    ("classify",       "🏷️  Classify (HOT + News Type)"),
]

STATE_ICON = {
    "pending":  "⏳",
    "running":  "⏱️",
    "complete": "✅",
    "skipped":  "⏭️",
    "error":    "❌",
}


def render_stage_board(stage_state: dict, placeholder):
    """Render the full stage list into a placeholder."""
    rows = []
    for stage_id, default_label in STAGES:
        info = stage_state.get(stage_id, {"state": "pending", "label": default_label, "detail": None})
        state = info.get("state", "pending")
        label = info.get("label") or default_label
        detail = info.get("detail") or ""
        icon = STATE_ICON.get(state, "•")
        css_class = f"stage-{state}" if state in ("running", "complete", "skipped", "error") else ""
        rows.append(
            f'<div class="stage-row {css_class}">'
            f'<div><span style="font-size:18px;margin-right:8px">{icon}</span>'
            f'<span class="stage-label">{label}</span>'
            f'{("<div class=stage-detail>" + detail + "</div>") if detail else ""}'
            f'</div></div>'
        )
    placeholder.markdown("\n".join(rows), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
run_clicked = st.button("🚀 Run Newsletter Scan", use_container_width=True, type="primary")
tab_scan, tab_hub = st.tabs(["📊 Scan & Results", "📚 Knowledge Hub"])


with tab_scan:
    if run_clicked:
        if start_date > end_date:
            st.error("Start date must be on or before end date.")
        elif not (use_google or use_pr):
            st.error("Select at least one source (Google News or PR Websites).")
        else:
            # ---- Per-phase live progress bars (top) -------------------
            gcol, pcol = st.columns(2)
            with gcol:
                st.markdown("**🟦 Google News progress**")
                g_bar = st.progress(
                    0.0, text="Idle" if not use_google else "Waiting..."
                )
            with pcol:
                st.markdown("**🟩 PR Websites progress**")
                p_bar = st.progress(
                    0.0, text="Idle" if not use_pr else "Waiting..."
                )
                # Live PR failure feed (updates as sites fail)
                pr_fail_placeholder = st.empty()
                pr_failures_live: list = []

                def _render_pr_failures():
                    if not pr_failures_live:
                        pr_fail_placeholder.empty()
                        return
                    import pandas as _pd
                    df_fail = _pd.DataFrame(
                        [
                            {
                                "Company": f.get("company", ""),
                                "Issue": f.get("category", "error"),
                                "URL": f.get("url", ""),
                                "Detail": (f.get("error", "") or "")[:200],
                            }
                            for f in pr_failures_live
                        ]
                    )
                    with pr_fail_placeholder.container():
                        st.markdown(
                            f"**⚠️ Live failures — {len(pr_failures_live)} sites failed**"
                        )
                        st.dataframe(
                            df_fail,
                            use_container_width=True,
                            hide_index=True,
                            height=min(300, 45 + 35 * len(df_fail)),
                            column_config={
                                "URL": st.column_config.LinkColumn(
                                    "URL", width="medium"
                                ),
                                "Company": st.column_config.TextColumn(
                                    "Company", width="small"
                                ),
                                "Issue": st.column_config.TextColumn(
                                    "Issue", width="medium"
                                ),
                                "Detail": st.column_config.TextColumn(
                                    "Detail", width="large"
                                ),
                            },
                        )

            # ---- Stage board (live pipeline timeline) -----------------
            st.markdown("### Pipeline stages")
            stage_placeholder = st.empty()
            stage_state: dict = {}
            render_stage_board(stage_state, stage_placeholder)

            # ---- AI batch progress (appears below the stage board) ----
            st.markdown("**🤖 AI filter progress (Groq batches)**")
            ai_bar = st.progress(0.0, text="Idle — waiting for previous stages...")

            def google_cb(company, idx, total):
                frac = idx / max(total, 1)
                g_bar.progress(min(frac, 1.0), text=f"{idx}/{total} — {company}")

            def pr_cb(company, idx, total):
                frac = idx / max(total, 1)
                p_bar.progress(min(frac, 1.0), text=f"{idx}/{total} — {company}")

            def pr_fail_cb(failure: dict):
                pr_failures_live.append(failure)
                _render_pr_failures()

            def ai_cb(batch_idx, total, status):
                # status: "running" | "done" | "error"
                if status == "running":
                    frac = (batch_idx - 1) / max(total, 1)
                    ai_bar.progress(
                        min(frac, 1.0),
                        text=f"🤖 Batch {batch_idx}/{total} — calling Groq...",
                    )
                else:
                    frac = batch_idx / max(total, 1)
                    icon = "✅" if status == "done" else "⚠️"
                    ai_bar.progress(
                        min(frac, 1.0),
                        text=f"{icon} Batch {batch_idx}/{total} {status}",
                    )

            def stage_cb(stage_id, state, label, detail):
                stage_state[stage_id] = {
                    "state": state, "label": label, "detail": detail
                }
                render_stage_board(stage_state, stage_placeholder)

            try:
                records, failures, info = run_pipeline(
                    start_date=start_date,
                    end_date=end_date,
                    use_ai_filter=use_ai,
                    use_google=use_google,
                    use_pr=use_pr,
                    include_undated=include_undated,
                    google_progress_cb=google_cb,
                    pr_progress_cb=pr_cb,
                    pr_failure_cb=pr_fail_cb,
                    ai_progress_cb=ai_cb,
                    stage_cb=stage_cb,
                )

                # Mark phase bars complete
                if use_google:
                    g_bar.progress(1.0, text="✅ Google News done")
                if use_pr:
                    p_bar.progress(1.0, text="✅ PR Websites done")
                ai_info_final = info.get("ai", {})
                if ai_info_final.get("attempted"):
                    ai_bar.progress(
                        1.0,
                        text=(
                            f"✅ AI done — {ai_info_final.get('batches', 0)} batches, "
                            f"{ai_info_final.get('errors', 0)} errors, "
                            f"kept {ai_info_final.get('kept', 0)}/{ai_info_final.get('input', 0)}"
                        ),
                    )
                else:
                    ai_bar.progress(1.0, text="⏭️ AI skipped")

                st.session_state.records = records
                st.session_state.failures = failures
                st.session_state.pipeline_info = info

                # ---- AI filter alert banner --------------------------
                ai_info = info.get("ai", {})
                if ai_info.get("used"):
                    st.success(f"🤖 {ai_info.get('reason','AI filter ran')}")
                elif ai_info.get("attempted"):
                    st.error(
                        f"⚠️ AI didn't work — switching to keywords. "
                        f"{ai_info.get('reason','')}"
                    )
                else:
                    st.info(f"ℹ️ {ai_info.get('reason','AI filter not run')}")

                # ---- AI prompt dropdown (full prompt sent to Groq) ----
                if ai_info.get("system_prompt"):
                    with st.expander(
                        f"🔍 View AI prompt sent to Groq  "
                        f"(model: {ai_info.get('model','—')}, "
                        f"unreachable sites included: {ai_info.get('unreachable_count',0)}, "
                        f"AI-synthesized records: {ai_info.get('synthesized_count',0)})",
                        expanded=False,
                    ):
                        st.markdown(
                            "**System prompt** (sent on every batch). "
                            "This includes the base scope rules plus the date range "
                            "and any unreachable PR sites discovered during scraping."
                        )
                        st.code(ai_info["system_prompt"], language="markdown")
                        if ai_info.get("unreachable_addendum"):
                            st.markdown(
                                "**Note:** Groq's training data has a cutoff — "
                                "synthesized entries reflect the model's prior knowledge, "
                                "not real-time scraping. Always verify before publishing."
                            )

                if records:
                    excel_path = export_to_excel(records, start_date, end_date)
                    st.session_state.excel_path = excel_path
                    st.success(f"Scan complete: {len(records)} records exported.")
                else:
                    st.session_state.excel_path = None
                    st.warning("No relevant records found for the selected range.")
            except Exception as e:
                st.error(f"Pipeline failed: {e}")
                st.exception(e)

    # =======================================================================
    # Results panel — shown whenever we have records in session
    # =======================================================================
    records = st.session_state.records
    failures = st.session_state.failures
    excel_path = st.session_state.excel_path

    if records is not None:
        total = len(records)
        hot = sum(1 for r in records if r.get("hot") == "HOT")
        g_count = sum(1 for r in records if r.get("source_type") == "Google News")
        p_count = sum(1 for r in records if r.get("source_type") == "PR Website")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Records", total)
        with c2:
            st.markdown('<div class="hot-metric">', unsafe_allow_html=True)
            st.metric("HOT Items", hot)
            st.markdown("</div>", unsafe_allow_html=True)
        c3.metric("Google News", g_count)
        c4.metric("PR Websites", p_count)

        if excel_path and os.path.exists(excel_path):
            with open(excel_path, "rb") as f:
                st.download_button(
                    "⬇️ Download Excel Report",
                    data=f.read(),
                    file_name=os.path.basename(excel_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        if total > 0:
            st.subheader("Preview")
            fc1, fc2, fc3 = st.columns(3)
            hot_filter = fc1.selectbox("Hot filter", ["All", "HOT only", "Non-Hot only"])
            type_opts = ["All"] + sorted({r.get("news_type", "Other") for r in records})
            type_filter = fc2.selectbox("News Type", type_opts)
            source_opts = ["All"] + sorted({r.get("source_type", "") for r in records})
            source_filter = fc3.selectbox("Source Type", source_opts)

            filtered = records
            if hot_filter == "HOT only":
                filtered = [r for r in filtered if r.get("hot") == "HOT"]
            elif hot_filter == "Non-Hot only":
                filtered = [r for r in filtered if r.get("hot") != "HOT"]
            if type_filter != "All":
                filtered = [r for r in filtered if r.get("news_type") == type_filter]
            if source_filter != "All":
                filtered = [r for r in filtered if r.get("source_type") == source_filter]

            df = pd.DataFrame([
                {
                    "#": r.get("serial_number"),
                    "Company": r.get("company"),
                    "Date": r.get("date"),
                    "Type": r.get("news_type"),
                    "Headline": (r.get("headline") or "")[:120],
                    "Source": r.get("source_type"),
                    "Hot": r.get("hot"),
                }
                for r in filtered
            ])
            st.dataframe(df, height=500, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(filtered)} of {total} records.")

        if failures:
            with st.expander(f"⚠️ {len(failures)} scraping failures"):
                for f in failures:
                    st.markdown(
                        f"**{f.get('company')}** — "
                        f"`{f.get('category', 'error')}`  \n"
                        f"{f.get('url')}  \n"
                        f"_{f.get('error')}_"
                    )


# ===========================================================================
# Knowledge Hub
# ===========================================================================
with tab_hub:
    st.markdown(
        "Use this view to **audit the relevancy criteria**. Every list below "
        "drives what the scanner picks up. If something important is missing "
        "or wrong, edit `config.py` and restart."
    )

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Companies tracked", len(COMPANIES))
    h2.metric("PR websites", len(PR_WEBSITES))
    h3.metric("Relevant keywords", len(RELEVANT_KEYWORDS))
    h4.metric("HOT triggers", len(HOT_KEYWORDS))

    st.divider()

    with st.expander(f"🏢 Monitored Companies ({len(COMPANIES)})", expanded=False):
        comp_df = pd.DataFrame(
            {"#": list(range(1, len(COMPANIES) + 1)), "Company": COMPANIES}
        )
        st.dataframe(comp_df, hide_index=True, use_container_width=True, height=420)

    with st.expander(f"🌐 PR / Company Websites ({len(PR_WEBSITES)})", expanded=False):
        pr_df = pd.DataFrame(
            [{"Company": s["company"], "URL": s["url"]} for s in PR_WEBSITES]
        )
        st.dataframe(
            pr_df,
            hide_index=True,
            use_container_width=True,
            height=420,
            column_config={
                "URL": st.column_config.LinkColumn("URL", display_text="Open ↗")
            },
        )

    with st.expander(
        f"✅ Relevant Keywords — INCLUDE if any match ({len(RELEVANT_KEYWORDS)})",
        expanded=False,
    ):
        st.caption(
            "A headline must contain at least one of these terms to pass the "
            "Stage-1 keyword filter (case-insensitive substring match)."
        )
        st.markdown(
            " ".join(
                f"<span style='background:#E8EEF7;border:1px solid #C5D2E5;"
                f"border-radius:14px;padding:3px 10px;margin:3px;display:inline-block;"
                f"font-size:12px;color:#1B3A5C'>{kw}</span>"
                for kw in RELEVANT_KEYWORDS
            ),
            unsafe_allow_html=True,
        )

    with st.expander(
        f"❌ Exclude Keywords — hard EXCLUDE if any match ({len(EXCLUDE_KEYWORDS)})",
        expanded=False,
    ):
        st.caption(
            "If a headline contains any of these terms it is dropped immediately, "
            "regardless of other matches."
        )
        st.markdown(
            " ".join(
                f"<span style='background:#FDECEC;border:1px solid #F5B7B1;"
                f"border-radius:14px;padding:3px 10px;margin:3px;display:inline-block;"
                f"font-size:12px;color:#922B21'>{kw}</span>"
                for kw in EXCLUDE_KEYWORDS
            ),
            unsafe_allow_html=True,
        )

    with st.expander(f"🔥 HOT Triggers ({len(HOT_KEYWORDS)})", expanded=False):
        st.caption(
            "Records whose headline contains any HOT keyword are tagged HOT "
            "(yellow highlight in the Excel export)."
        )
        st.markdown(
            " ".join(
                f"<span style='background:#FFF2CC;border:1px solid #E8C547;"
                f"border-radius:14px;padding:3px 10px;margin:3px;display:inline-block;"
                f"font-size:12px;color:#7E5A00'>{kw}</span>"
                for kw in HOT_KEYWORDS
            ),
            unsafe_allow_html=True,
        )

    with st.expander(
        f"🏷️ News Type Classification Rules ({len(NEWS_TYPE_RULES)} categories)",
        expanded=False,
    ):
        st.caption(
            "First category whose triggers match the headline wins. "
            "If nothing matches, the record is tagged 'Other'."
        )
        for category, triggers in NEWS_TYPE_RULES.items():
            st.markdown(f"**{category}**")
            st.markdown(
                " ".join(
                    f"<span style='background:#F0F4F8;border:1px solid #C5D2E5;"
                    f"border-radius:12px;padding:2px 8px;margin:2px;display:inline-block;"
                    f"font-size:11px;color:#1B3A5C'>{t}</span>"
                    for t in triggers
                ),
                unsafe_allow_html=True,
            )
            st.markdown("")

    with st.expander("🤖 AI Filter Scope (what Groq is told)", expanded=False):
        st.markdown(
            """
**Model**: configurable via `GROQ_MODEL` env var (default `llama-3.3-70b-versatile`).
**Endpoint**: `https://api.x.ai/v1/chat/completions`

**IN SCOPE (relevant):**
- Immunodiagnostics, allergy diagnostics, autoimmune diagnostics
- Immunoassays (ELISA, lateral flow, multiplex, serology)
- Diagnostic platforms / analyzers / reagents / test kits
- Infectious disease diagnostics, point-of-care (POC), IVD
- Laboratory solutions
- **Allergen immunotherapy / allergy therapeutics** — ALK, Stallergenes Greer, Aimmune, DBV, Allergy Therapeutics are intentionally in scope
- Strategic events on monitored companies: M&A, partnerships, regulatory approvals (FDA, CE, 510k), product launches, conference participation (EAACI, AAAAI, ACAAI), leadership changes, strategic financial results

**OUT OF SCOPE:**
- Generic pharma news (cardiovascular, oncology, diabetes, obesity)
- Biosimilars or unrelated drug approvals
- General hospital / healthcare system news
- Unrelated clinical trials for drugs
- Mental health / psychiatry / neurology / orthopedic / dermatology / ophthalmology drugs
- Generic medical news with no link to diagnostics or allergy
"""
        )
