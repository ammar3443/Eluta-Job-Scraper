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


# ---------------------------------------------------------------------------
# YOE Extractor
# ---------------------------------------------------------------------------

def _categorize_yoe(years: int) -> str:
    if years <= 1:
        return "0-1"
    elif years <= 3:
        return "2-3"
    elif years < 5:
        return "4-5"
    else:
        return "5+"


def extract_yoe(text: str) -> str:
    """Extract years-of-experience requirement from job description text."""
    text_lower = text.lower()

    # New grad / intern / entry level first
    entry_patterns = ["new grad", "new graduate", "entry level", "entry-level",
                      "internship", "co-op", "coop", "no experience"]
    if any(p in text_lower for p in entry_patterns):
        return "0-1"

    # "3-5 years" or "3 to 5 years"
    range_match = re.search(
        r"(\d+)\s*(?:-|to)\s*(\d+)\s*\+?\s*years?", text_lower
    )
    if range_match:
        return _categorize_yoe(int(range_match.group(1)))

    # "5+ years experience" or "5 years of experience"
    single_match = re.search(
        r"(\d+)\s*\+?\s*years?\s*(?:of\s+)?(?:experience|exp)", text_lower
    )
    if single_match:
        return _categorize_yoe(int(single_match.group(1)))

    # "experience: 3 years" style
    exp_colon = re.search(r"experience[:\s]+(\d+)\s*\+?\s*years?", text_lower)
    if exp_colon:
        return _categorize_yoe(int(exp_colon.group(1)))

    return "unknown"


# ---------------------------------------------------------------------------
# Keyword Classifier
# ---------------------------------------------------------------------------

def keyword_classify(title: str, categories: dict) -> str | None:
    """
    Match job title against category keyword lists.
    Returns category name or None if no match (→ Claude).
    general_swe has no keywords intentionally — never keyword-matched.
    """
    title_lower = title.lower()
    for category, keywords in categories.items():
        if not keywords:
            continue
        for kw in keywords:
            if kw.lower() in title_lower:
                return category
    return None


# ---------------------------------------------------------------------------
# Feedback Lookup
# ---------------------------------------------------------------------------

_FUZZY_THRESHOLD = 0.85


def feedback_lookup(title: str, feedback: dict) -> dict | None:
    """
    Check feedback decisions for a matching title.
    Returns the decision dict {title, relevant, category, reason} or None.
    Tries exact match first, then fuzzy match with ratio >= 0.85.
    """
    title_lower = title.lower().strip()
    decisions = feedback.get("decisions", [])

    # Exact match
    for d in decisions:
        if d["title"].lower().strip() == title_lower:
            return d

    # Fuzzy match
    best_ratio = 0.0
    best_decision = None
    for d in decisions:
        ratio = SequenceMatcher(None, title_lower, d["title"].lower().strip()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_decision = d

    if best_ratio >= _FUZZY_THRESHOLD:
        return best_decision

    return None


# ---------------------------------------------------------------------------
# Claude Prompt + Response Parser
# ---------------------------------------------------------------------------

_CATEGORIES_LIST = (
    "backend, frontend, fullstack, ai_ml, firmware, "
    "cloud_devops, mobile, data, analyst, general_swe"
)


def build_claude_prompt(title: str, jd_text: str, feedback: dict, config: dict) -> str:
    max_examples = config["classifier"]["max_few_shot_examples"]
    decisions = feedback.get("decisions", [])[-max_examples:]

    examples_block = ""
    if decisions:
        lines = []
        for d in decisions:
            if d["relevant"]:
                line = f'- "{d["title"]}" → relevant, category: {d["category"]}'
                if d.get("reason"):
                    line += f' [{d["reason"]}]'
            else:
                line = f'- "{d["title"]}" → NOT relevant'
                if d.get("reason"):
                    line += f' [reason: {d["reason"]}]'
            lines.append(line)
        examples_block = "Past decisions (use these as guidance):\n" + "\n".join(lines) + "\n\n"

    return (
        "You are classifying job postings for a software engineering job search.\n\n"
        f"{examples_block}"
        f"Categories: {_CATEGORIES_LIST}\n\n"
        "Rules:\n"
        "- When in doubt about category, use general_swe — do not miss a relevant posting\n"
        "- Non-technical roles (civil, mechanical, industrial, trades) → relevant: false\n"
        "- Read the full job description for technology keywords (AWS, Python, Terraform, etc.)\n"
        "- Return ONLY JSON, no explanation\n\n"
        f"Job title: {title}\n"
        f"Job description: {jd_text}\n\n"
        'Reply with exactly:\n'
        '{"relevant": true/false, "category": "<category>", "confidence": 0.0-1.0, "yoe": "0-1|2-3|4-5|5+|unknown"}'
    )


def parse_claude_response(raw: str) -> dict:
    """
    Extract JSON from Claude's response text.
    Returns a safe fallback dict with low confidence if parsing fails.
    """
    # Try to find a JSON object in the response
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return {
                "relevant": bool(data.get("relevant", False)),
                "category": data.get("category", "general_swe"),
                "confidence": float(data.get("confidence", 0.0)),
                "yoe": data.get("yoe", "unknown"),
            }
        except (json.JSONDecodeError, ValueError):
            print(f"Warning: Claude response matched JSON pattern but failed to parse: {match.group()[:100]}")
    else:
        print(f"Warning: Could not find JSON in Claude response: {raw[:100]}")

    # Fallback: unparseable response → flag for review
    return {"relevant": False, "category": None, "confidence": 0.0, "yoe": "unknown"}


# ---------------------------------------------------------------------------
# Claude Classifier
# ---------------------------------------------------------------------------

def claude_classify(title: str, jd_text: str, feedback: dict, config: dict) -> dict:
    """
    Call Claude Haiku to classify a borderline job.
    Returns dict with keys: relevant, category, confidence, yoe, flagged_for_review.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    prompt = build_claude_prompt(title, jd_text, feedback, config)

    response = client.messages.create(
        model=config["classifier"]["claude_model"],
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    result = parse_claude_response(raw)
    threshold = config["classifier"]["confidence_threshold"]
    result["flagged_for_review"] = result["confidence"] < threshold
    return result


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def _check_robots(config: dict) -> bool:
    """Returns True if scraping is allowed. Exits if robots.txt disallows and respect=True."""
    if not config["scraper"].get("respect_robots_txt", True):
        return True
    rp = RobotFileParser()
    rp.set_url(f"{ELUTA_BASE}/robots.txt")
    rp.read()
    allowed = rp.can_fetch(HEADERS["User-Agent"], ELUTA_SEARCH)
    if not allowed:
        print("robots.txt disallows scraping eluta.ca. Exiting.")
        sys.exit(1)
    return True


def _polite_delay(config: dict) -> None:
    delay = random.uniform(
        config["scraper"]["delay_min"],
        config["scraper"]["delay_max"],
    )
    time.sleep(delay)


def _extract_job_id(slug: str) -> str:
    """Extract the hash ID from a slug like 'spl/backend-dev-<32hexchars>?imo=1'."""
    match = re.search(r"([a-f0-9]{32})", slug)
    return match.group(1) if match else slug


def fetch_results_page(page: int, query: str, config: dict) -> list[dict]:
    """
    Fetch one search results page from Eluta.
    Returns list of job dicts: {title, company, snippet, date_posted, job_id, slug, url}
    """
    params = {"q": query, "page": page}
    _polite_delay(config)
    resp = requests.get(ELUTA_SEARCH, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()  # surface 403/429/5xx immediately instead of silently parsing error HTML
    soup = BeautifulSoup(resp.text, "html.parser")

    jobs = []
    for card in soup.find_all(class_="organic-job"):
        title_tag = card.find("a", class_="lk-job-title")
        company_tag = card.find("a", class_="lk-employer")
        desc_tag = card.find("span", class_="description")
        date_tag = card.find("a", class_="lastseen")
        slug = card.get("data-url", "")

        if not title_tag or not slug:
            continue

        job_id = _extract_job_id(slug)
        jobs.append({
            "title": title_tag.get_text(strip=True),
            "company": company_tag.get_text(strip=True) if company_tag else "",
            "snippet": desc_tag.get_text(strip=True) if desc_tag else "",
            "date_posted": date_tag.get_text(strip=True) if date_tag else "",
            "job_id": job_id,
            "slug": slug,
            "url": f"{ELUTA_BASE}/{slug.split('?')[0]}",  # clean URL without ?imo= param
        })
    return jobs


def fetch_full_jd(slug: str, config: dict) -> str:
    """
    Fetch the full job description from the /spl/ page.
    Returns plain text of the description, or empty string on failure.
    """
    # slug may be "spl/job-title-hash?imo=N" — build full URL
    url = f"{ELUTA_BASE}/{slug}" if not slug.startswith("http") else slug
    _polite_delay(config)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    desc = soup.find(class_="short-text")
    if not desc:
        # Fallback: try description div
        desc = soup.find("div", class_="description")
    if not desc:
        return ""
    return desc.get_text(separator=" ", strip=True)
