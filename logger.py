"""Centralised logger for the DNL tool. Writes daily log files + console."""
import logging
import os
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_log_path = os.path.join(LOG_DIR, f"dnl_{datetime.now().strftime('%Y%m%d')}.log")

logger = logging.getLogger("dnl")
logger.setLevel(logging.INFO)

# Avoid duplicate handlers when Streamlit reruns the script
if not logger.handlers:
    _formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _file_h = logging.FileHandler(_log_path, encoding="utf-8")
    _file_h.setFormatter(_formatter)
    _file_h.setLevel(logging.INFO)
    logger.addHandler(_file_h)

    _console_h = logging.StreamHandler()
    _console_h.setFormatter(_formatter)
    _console_h.setLevel(logging.INFO)
    logger.addHandler(_console_h)

    logger.propagate = False
