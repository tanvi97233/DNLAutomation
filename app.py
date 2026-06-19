"""
Competitive Intelligence Engine — single Streamlit app.

Run with:
    streamlit run app.py

ONE process, ONE deploy. Routing is done with a URL query param:

  /                       -> dashboard shell (index.html)
  /?page=research-setup   -> the original DNL pipeline app (app_legacy.py)

`app_legacy.py` is executed in-place via runpy so it remains byte-for-byte
unchanged. Backend modules (pipeline.py, pr_scraper.py, google_news.py,
ai_filter.py, exporter.py, config.py, filters.py, logger.py) are not
imported or modified here.
"""
from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


HERE = Path(__file__).parent
LEGACY_SCRIPT = HERE / "app_legacy.py"

# st.query_params behaves like a dict. The shell sets ?page=research-setup
# on its top window when the user clicks "Research Setup" in the sidebar.
_page = st.query_params.get("page", "")


# ---------------------------------------------------------------------------
# Route 1: legacy DNL pipeline app
# ---------------------------------------------------------------------------
if _page == "research-setup":
    if not LEGACY_SCRIPT.exists():
        st.error(f"Pipeline app not found: {LEGACY_SCRIPT}")
        st.stop()

    # Delegate to app_legacy.py exactly as if it were run directly.
    # IMPORTANT: do NOT call st.set_page_config here — app_legacy.py calls it
    # and Streamlit only allows one such call per run.
    runpy.run_path(str(LEGACY_SCRIPT), run_name="__main__")

    # Floating "Back to Dashboard" link. Fixed-position so it never disturbs
    # the legacy app's layout.
    st.markdown(
        """
        <a href="./" target="_self"
           style="position:fixed;top:12px;right:16px;z-index:9999;
                  background:#6D4FF6;color:#fff;padding:8px 14px;
                  border-radius:8px;font-size:13px;font-weight:600;
                  text-decoration:none;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                  box-shadow:0 4px 14px rgba(0,0,0,0.35)">
          ← Back to Dashboard
        </a>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------------------------------------------------------------------
# Route 2 (default): dashboard shell
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Competitive Intelligence Engine",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit's chrome so the embedded dashboard fills the viewport.
st.markdown(
    """
    <style>
      #MainMenu, header, footer { visibility: hidden; height: 0; }
      [data-testid="stSidebar"], [data-testid="stSidebarNav"],
      [data-testid="collapsedControl"] { display: none !important; }
      .block-container {
        padding: 0 !important;
        max-width: 100% !important;
      }
      html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background: #0F0A2E !important;
        margin: 0 !important;
        padding: 0 !important;
      }
      iframe { border: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

_HTML_PATH = HERE / "index.html"

try:
    _html = _HTML_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    st.error(f"Dashboard file not found: {_HTML_PATH}")
    st.stop()

components.html(_html, height=1400, scrolling=True)
