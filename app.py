"""
Streamlit entry point for the Competitive Intelligence Engine UI shell.

Run with:
    streamlit run app.py

A single command boots everything:
  * This shell serves the dashboard (index.html) on the default Streamlit
    port (typically 8501).
  * On first load, this file auto-spawns the ORIGINAL DNL pipeline app
    (app_legacy.py) on port 8502 in the background. The shell's
    "Research Setup" page iframes that app at http://localhost:8502.

Backend modules (pipeline.py, pr_scraper.py, google_news.py, ai_filter.py,
exporter.py, config.py, filters.py, logger.py) are not imported or modified
here. The legacy app file itself is also left untouched.
"""
from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


# ---------------------------------------------------------------------------
# Legacy DNL pipeline app launcher
# ---------------------------------------------------------------------------
LEGACY_PORT = 8502
LEGACY_HOST = "127.0.0.1"
LEGACY_SCRIPT = Path(__file__).parent / "app_legacy.py"
_PID_FILE = Path(__file__).parent / ".legacy_app.pid"


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """Return True if something is already listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _spawn_legacy_app() -> None:
    """Start app_legacy.py on LEGACY_PORT in the background, once."""
    if not LEGACY_SCRIPT.exists():
        return  # nothing to launch

    if _port_open(LEGACY_HOST, LEGACY_PORT):
        return  # already running (this run, or a previous one)

    # Reuse the same Python interpreter that is hosting THIS Streamlit run,
    # so we know `streamlit` is importable.
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(LEGACY_SCRIPT),
        "--server.port", str(LEGACY_PORT),
        "--server.address", LEGACY_HOST,
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--browser.gatherUsageStats", "false",
    ]

    # Detach: no stdin, pipe stdout/stderr to a log file so the parent process
    # never blocks on them. On Windows we also use CREATE_NEW_PROCESS_GROUP
    # so Ctrl+C in the shell only stops the shell, not the child.
    log_path = Path(__file__).parent / "logs" / "legacy_app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "ab", buffering=0)

    popen_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_fh,
        "stderr": subprocess.STDOUT,
        "cwd": str(LEGACY_SCRIPT.parent),
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    try:
        _PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    except OSError:
        pass

    # Best-effort: wait briefly for the port to come up so the first iframe
    # render doesn't show a connection error.
    for _ in range(40):  # ~10s max
        if _port_open(LEGACY_HOST, LEGACY_PORT):
            break
        time.sleep(0.25)

    def _cleanup() -> None:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            log_fh.close()
        except Exception:
            pass

    atexit.register(_cleanup)


# Cache so we only spawn once per Streamlit server process, even though
# Streamlit re-runs this script on every interaction.
@st.cache_resource(show_spinner=False)
def _ensure_legacy_running() -> bool:
    _spawn_legacy_app()
    return _port_open(LEGACY_HOST, LEGACY_PORT)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Competitive Intelligence Engine",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_ensure_legacy_running()

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

_HTML_PATH = Path(__file__).parent / "index.html"

try:
    _html = _HTML_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    st.error(f"Dashboard file not found: {_HTML_PATH}")
    st.stop()

# Generous height so the nested legacy-app iframe (Research Setup page) has
# room. scrolling=True lets the user scroll on shorter viewports.
components.html(_html, height=1400, scrolling=True)
