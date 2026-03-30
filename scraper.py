# scraper.py
import json
import os
import re
import sys
import time
import random
import argparse
from datetime import date
from difflib import SequenceMatcher
from urllib.robotparser import RobotFileParser

import yaml
import requests
from bs4 import BeautifulSoup
import anthropic
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELUTA_BASE = "https://www.eluta.ca"
ELUTA_SEARCH = f"{ELUTA_BASE}/search"
ELUTA_SPL = f"{ELUTA_BASE}/spl"

CATEGORY_COLORS = {
    "backend":     "B8CCE4",
    "frontend":    "C6EFCE",
    "fullstack":   "DDEBF7",
    "ai_ml":       "E2CFED",
    "firmware":    "FCE4D6",
    "cloud_devops":"DAEEF3",
    "mobile":      "FFF2CC",
    "data":        "EDEDED",
    "analyst":     "F2F2F2",
    "general_swe": "FFFFFF",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# Config + Feedback
# ---------------------------------------------------------------------------

def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(f"Error: config file not found: {path}")
    except yaml.YAMLError as exc:
        sys.exit(f"Error: invalid YAML in {path}: {exc}")


def load_feedback(path: str = "feedback.json") -> dict:
    if not os.path.exists(path):
        return {"decisions": [], "ambiguous_titles": []}
    with open(path, "r") as f:
        return json.load(f)


def save_feedback(feedback: dict, path: str = "feedback.json") -> None:
    with open(path, "w") as f:
        json.dump(feedback, f, indent=2)


# ---------------------------------------------------------------------------
# Hard Filter
# ---------------------------------------------------------------------------

def hard_filter(title: str, config: dict, ambiguous_titles: list) -> tuple[str, str | None]:
    """
    Returns (action, reason).
    action: "pass" | "filter" | "ambiguous"
    reason: description string if filtered, None if passed/ambiguous
    """
    title_lower = title.lower().strip()

    # Ambiguous list overrides all blocklists — goes straight to Claude
    if title_lower in {t.lower() for t in ambiguous_titles}:
        return ("ambiguous", None)

    filters = config["filters"]

    # Seniority blocklist
    for term in filters["seniority_blocklist"]:
        if term.lower() in title_lower:
            return ("filter", f"seniority blocklist match: '{term.strip()}'")

    # Non-technical blocklist
    for term in filters["non_technical_blocklist"]:
        if term.lower() in title_lower:
            return ("filter", f"non-technical blocklist match: '{term.strip()}'")

    return ("pass", None)
