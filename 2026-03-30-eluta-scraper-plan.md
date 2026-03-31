# Eluta Job Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-file Python scraper for eluta.ca that filters, classifies, and exports software engineering job postings to XLSX, learning from human feedback over time.

**Architecture:** `scraper.py` contains all logic organized in sections. `config.yaml` drives all behavior. `feedback.json` stores human decisions used as few-shot examples for Claude. The pipeline flows: scrape → hard filter → fetch full JD → classify (feedback → keyword → Claude) → extract YOE → export.

**Tech Stack:** Python 3.11+, `requests`, `beautifulsoup4`, `openpyxl`, `anthropic`, `pyyaml`, `pytest`, `urllib.robotparser` (stdlib)

---

## File Map

| File | Responsibility |
|---|---|
| `scraper.py` | All logic: config loading, filtering, classification, scraping, export, CLI |
| `config.yaml` | User-facing settings: queries, categories, blocklists, thresholds |
| `feedback.json` | Persisted human decisions and ambiguous title list |
| `requirements.txt` | Pinned dependencies |
| `output/` | Generated XLSX and JSON files per run |
| `tests/test_scraper.py` | All unit tests |

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `feedback.json`
- Create: `tests/__init__.py`
- Create: `tests/test_scraper.py` (skeleton)

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.31.0
beautifulsoup4==4.12.3
openpyxl==3.1.2
anthropic==0.34.0
PyYAML==6.0.1
pytest==8.1.1
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install without errors.

- [ ] **Step 3: Create `config.yaml`**

```yaml
sites:
  eluta:
    enabled: true
    query: "software engineer"
    max_pages: 100

categories:
  backend:
    - backend developer
    - server-side engineer
    - api engineer
    - software engineer backend
  frontend:
    - frontend developer
    - ui engineer
    - web developer
    - react developer
    - angular developer
  fullstack:
    - full stack developer
    - fullstack developer
    - full-stack engineer
  ai_ml:
    - ai engineer
    - ml engineer
    - machine learning engineer
    - nlp engineer
    - computer vision engineer
    - data scientist
  firmware:
    - firmware engineer
    - embedded software engineer
    - embedded systems engineer
    - rtos engineer
  cloud_devops:
    - cloud engineer
    - devops engineer
    - site reliability engineer
    - sre
    - infrastructure engineer
    - platform engineer
  mobile:
    - ios developer
    - android developer
    - mobile developer
    - react native developer
  data:
    - data engineer
    - analytics engineer
    - etl developer
  analyst:
    - business analyst
    - systems analyst
    - technical analyst
  general_swe: []

filters:
  seniority_blocklist:
    - " lead"
    - " staff"
    - "team lead"
    - "principal engineer"
    - "engineering manager"
  non_technical_blocklist:
    - millwright
    - electrician
    - civil engineer
    - plumber
    - hvac
    - welder
    - machinist
    - pipefitter
    - ironworker
    - carpenter
    - sheet metal

classifier:
  confidence_threshold: 0.60
  claude_model: claude-haiku-4-5-20251001
  max_few_shot_examples: 15

scraper:
  delay_min: 2
  delay_max: 5
  respect_robots_txt: true
```

- [ ] **Step 4: Create `feedback.json`**

```json
{
  "decisions": [],
  "ambiguous_titles": []
}
```

- [ ] **Step 5: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 6: Create `tests/test_scraper.py` skeleton**

```python
# tests/test_scraper.py
import pytest
```

- [ ] **Step 7: Verify test suite runs**

Run: `pytest tests/ -v`
Expected: `no tests ran` — zero failures.

- [ ] **Step 8: Commit**

```bash
git init
git add requirements.txt config.yaml feedback.json tests/__init__.py tests/test_scraper.py
git commit -m "chore: project setup — config, dependencies, test skeleton"
```

---

## Task 2: Config and Feedback Loaders

**Files:**
- Create: `scraper.py` (initial)
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scraper.py
import json
import os
import pytest
import yaml
from unittest.mock import mock_open, patch


def test_load_config_returns_dict(tmp_path):
    cfg = {
        "sites": {"eluta": {"enabled": True, "query": "software engineer", "max_pages": 5}},
        "categories": {"backend": ["backend developer"], "general_swe": []},
        "filters": {"seniority_blocklist": [" lead"], "non_technical_blocklist": ["millwright"]},
        "classifier": {"confidence_threshold": 0.60, "claude_model": "claude-haiku-4-5-20251001", "max_few_shot_examples": 15},
        "scraper": {"delay_min": 1, "delay_max": 2, "respect_robots_txt": False},
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(cfg))
    from scraper import load_config
    result = load_config(str(config_file))
    assert result["classifier"]["confidence_threshold"] == 0.60
    assert result["sites"]["eluta"]["query"] == "software engineer"


def test_load_feedback_returns_structure(tmp_path):
    fb = {"decisions": [], "ambiguous_titles": []}
    fb_file = tmp_path / "feedback.json"
    fb_file.write_text(json.dumps(fb))
    from scraper import load_feedback
    result = load_feedback(str(fb_file))
    assert "decisions" in result
    assert "ambiguous_titles" in result


def test_load_feedback_missing_file_returns_empty():
    from scraper import load_feedback
    result = load_feedback("/nonexistent/feedback.json")
    assert result == {"decisions": [], "ambiguous_titles": []}


def test_save_feedback_writes_json(tmp_path):
    fb = {"decisions": [{"title": "Backend Dev", "relevant": True}], "ambiguous_titles": []}
    fb_file = tmp_path / "feedback.json"
    from scraper import save_feedback
    save_feedback(fb, str(fb_file))
    written = json.loads(fb_file.read_text())
    assert written["decisions"][0]["title"] == "Backend Dev"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -v`
Expected: `ImportError: No module named 'scraper'`

- [ ] **Step 3: Create `scraper.py` with config/feedback functions**

```python
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
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_feedback(path: str = "feedback.json") -> dict:
    if not os.path.exists(path):
        return {"decisions": [], "ambiguous_titles": []}
    with open(path, "r") as f:
        return json.load(f)


def save_feedback(feedback: dict, path: str = "feedback.json") -> None:
    with open(path, "w") as f:
        json.dump(feedback, f, indent=2)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py::test_load_config_returns_dict tests/test_scraper.py::test_load_feedback_returns_structure tests/test_scraper.py::test_load_feedback_missing_file_returns_empty tests/test_scraper.py::test_save_feedback_writes_json -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: config and feedback loaders"
```

---

## Task 3: Hard Filter

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

The hard filter returns one of three actions: `"pass"`, `"filter"`, or `"ambiguous"`.
- `"filter"` → job discarded (goes to filtered JSON)
- `"ambiguous"` → title is in the ambiguous list (past dispute) → skip straight to Claude
- `"pass"` → proceed normally through keyword → Claude pipeline

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def test_hard_filter_blocks_seniority():
    from scraper import hard_filter
    config = {
        "filters": {
            "seniority_blocklist": [" lead", "team lead", "engineering manager"],
            "non_technical_blocklist": ["millwright"],
        }
    }
    action, reason = hard_filter("Engineering Lead", config, [])
    assert action == "filter"
    assert "seniority" in reason.lower()


def test_hard_filter_blocks_non_technical():
    from scraper import hard_filter
    config = {
        "filters": {
            "seniority_blocklist": [" lead"],
            "non_technical_blocklist": ["millwright", "electrician"],
        }
    }
    action, reason = hard_filter("Millwright Technician", config, [])
    assert action == "filter"
    assert "non-technical" in reason.lower()


def test_hard_filter_passes_clean_title():
    from scraper import hard_filter
    config = {
        "filters": {
            "seniority_blocklist": [" lead"],
            "non_technical_blocklist": ["millwright"],
        }
    }
    action, reason = hard_filter("Backend Developer", config, [])
    assert action == "pass"
    assert reason is None


def test_hard_filter_ambiguous_list_overrides_blocklist():
    from scraper import hard_filter
    config = {
        "filters": {
            "seniority_blocklist": [" lead"],
            "non_technical_blocklist": ["civil engineer"],
        }
    }
    # "controls engineer" was disputed, now in ambiguous list
    action, reason = hard_filter("Controls Engineer", config, ["controls engineer"])
    assert action == "ambiguous"


def test_hard_filter_case_insensitive():
    from scraper import hard_filter
    config = {
        "filters": {
            "seniority_blocklist": [" lead"],
            "non_technical_blocklist": ["millwright"],
        }
    }
    action, _ = hard_filter("MILLWRIGHT OPERATOR", config, [])
    assert action == "filter"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "hard_filter" -v`
Expected: `ImportError` or `AttributeError` — `hard_filter` not defined.

- [ ] **Step 3: Implement `hard_filter` in `scraper.py`**

Add after `save_feedback`:

```python
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
    if title_lower in [t.lower() for t in ambiguous_titles]:
        return ("ambiguous", None)

    filters = config["filters"]

    # Seniority blocklist
    for term in filters["seniority_blocklist"]:
        if term.lower() in title_lower:
            return ("filter", f"seniority blocklist match: '{term}'")

    # Non-technical blocklist
    for term in filters["non_technical_blocklist"]:
        if term.lower() in title_lower:
            return ("filter", f"non-technical blocklist match: '{term}'")

    return ("pass", None)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "hard_filter" -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: hard filter — seniority + non-technical blocklists"
```

---

## Task 4: YOE Extractor

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def test_extract_yoe_range():
    from scraper import extract_yoe
    # Lower bound (3) passed to _categorize_yoe → "2-3"
    assert extract_yoe("We require 3-5 years of experience in Python.") == "2-3"


def test_extract_yoe_single():
    from scraper import extract_yoe
    assert extract_yoe("Minimum 2 years of experience required.") == "2-3"


def test_extract_yoe_plus():
    from scraper import extract_yoe
    assert extract_yoe("7+ years experience with distributed systems.") == "5+"


def test_extract_yoe_new_grad():
    from scraper import extract_yoe
    assert extract_yoe("This is a new grad position, no experience needed.") == "0-1"


def test_extract_yoe_internship():
    from scraper import extract_yoe
    assert extract_yoe("Summer internship for computer science students.") == "0-1"


def test_extract_yoe_entry_level():
    from scraper import extract_yoe
    assert extract_yoe("Entry-level software engineer role.") == "0-1"


def test_extract_yoe_unknown():
    from scraper import extract_yoe
    assert extract_yoe("Join our team and work on exciting projects.") == "unknown"


def test_extract_yoe_one_year():
    from scraper import extract_yoe
    assert extract_yoe("1 year of experience with React.") == "0-1"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "extract_yoe" -v`
Expected: `ImportError` — `extract_yoe` not defined.

- [ ] **Step 3: Implement `extract_yoe` in `scraper.py`**

Add after `hard_filter`:

```python
# ---------------------------------------------------------------------------
# YOE Extractor
# ---------------------------------------------------------------------------

def _categorize_yoe(years: int) -> str:
    if years <= 1:
        return "0-1"
    elif years <= 3:
        return "2-3"
    elif years <= 5:
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "extract_yoe" -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: YOE extractor with regex patterns"
```

---

## Task 5: Keyword Classifier

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Returns the matched category string or `None` if no keyword matches (falls through to Claude).

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def _make_categories():
    return {
        "backend": ["backend developer", "api engineer"],
        "frontend": ["frontend developer", "ui engineer"],
        "ai_ml": ["ml engineer", "machine learning engineer"],
        "firmware": ["firmware engineer", "embedded software engineer"],
        "cloud_devops": ["cloud engineer", "devops engineer"],
        "general_swe": [],
    }


def test_keyword_classify_exact_match():
    from scraper import keyword_classify
    assert keyword_classify("Backend Developer", _make_categories()) == "backend"


def test_keyword_classify_case_insensitive():
    from scraper import keyword_classify
    assert keyword_classify("FRONTEND DEVELOPER", _make_categories()) == "frontend"


def test_keyword_classify_partial_match():
    from scraper import keyword_classify
    # "Senior ML Engineer" contains "ml engineer"
    assert keyword_classify("Senior ML Engineer", _make_categories()) == "ai_ml"


def test_keyword_classify_no_match_returns_none():
    from scraper import keyword_classify
    assert keyword_classify("Technical Specialist", _make_categories()) is None


def test_keyword_classify_general_swe_never_matches():
    # general_swe has empty keywords — always falls through to Claude
    from scraper import keyword_classify
    assert keyword_classify("Software Engineer", _make_categories()) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "keyword_classify" -v`
Expected: `ImportError` — `keyword_classify` not defined.

- [ ] **Step 3: Implement `keyword_classify` in `scraper.py`**

Add after `extract_yoe`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "keyword_classify" -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: keyword classifier against config category lists"
```

---

## Task 6: Feedback Lookup (Fuzzy Match)

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Checks `feedback.json` decisions for a matching title (exact first, then fuzzy ≥ 0.85 similarity). Returns the stored decision dict or `None`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def _make_feedback():
    return {
        "decisions": [
            {"title": "Platform Engineer", "relevant": True, "category": "cloud_devops", "reason": "confirmed"},
            {"title": "Process Control Engineer", "relevant": False, "category": None, "reason": "industrial"},
        ],
        "ambiguous_titles": ["controls engineer"]
    }


def test_feedback_lookup_exact_match():
    from scraper import feedback_lookup
    result = feedback_lookup("Platform Engineer", _make_feedback())
    assert result["relevant"] is True
    assert result["category"] == "cloud_devops"


def test_feedback_lookup_case_insensitive():
    from scraper import feedback_lookup
    result = feedback_lookup("platform engineer", _make_feedback())
    assert result is not None
    assert result["relevant"] is True


def test_feedback_lookup_fuzzy_match():
    from scraper import feedback_lookup
    # "Platform Engineer II" is close enough to "Platform Engineer"
    result = feedback_lookup("Platform Engineer II", _make_feedback())
    assert result is not None
    assert result["category"] == "cloud_devops"


def test_feedback_lookup_no_match_returns_none():
    from scraper import feedback_lookup
    result = feedback_lookup("iOS Developer", _make_feedback())
    assert result is None


def test_feedback_lookup_fuzzy_below_threshold_returns_none():
    from scraper import feedback_lookup
    # "Mechanical Engineer" is not similar enough to any stored title
    result = feedback_lookup("Mechanical Engineer", _make_feedback())
    assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "feedback_lookup" -v`
Expected: `ImportError` — `feedback_lookup` not defined.

- [ ] **Step 3: Implement `feedback_lookup` in `scraper.py`**

Add after `keyword_classify`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "feedback_lookup" -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: feedback lookup with fuzzy title matching"
```

---

## Task 7: Claude Prompt Builder and Response Parser

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Separating prompt building and response parsing from the API call makes both testable without mocking the Anthropic client.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def test_build_claude_prompt_includes_title_and_jd():
    from scraper import build_claude_prompt
    feedback = {"decisions": [], "ambiguous_titles": []}
    config = {"classifier": {"max_few_shot_examples": 15}}
    prompt = build_claude_prompt("Platform Engineer", "We use AWS and Terraform.", feedback, config)
    assert "Platform Engineer" in prompt
    assert "AWS" in prompt
    assert "Terraform" in prompt


def test_build_claude_prompt_includes_few_shot_examples():
    from scraper import build_claude_prompt
    feedback = {
        "decisions": [
            {"title": "Embedded C Developer", "relevant": True, "category": "firmware", "reason": "PLC work"},
            {"title": "Civil Engineer", "relevant": False, "category": None, "reason": "not software"},
        ],
        "ambiguous_titles": []
    }
    config = {"classifier": {"max_few_shot_examples": 15}}
    prompt = build_claude_prompt("Some Job", "Some description.", feedback, config)
    assert "Embedded C Developer" in prompt
    assert "Civil Engineer" in prompt


def test_build_claude_prompt_caps_few_shot_examples():
    from scraper import build_claude_prompt
    decisions = [{"title": f"Job {i}", "relevant": True, "category": "backend", "reason": ""} for i in range(20)]
    feedback = {"decisions": decisions, "ambiguous_titles": []}
    config = {"classifier": {"max_few_shot_examples": 5}}
    prompt = build_claude_prompt("New Job", "Description.", feedback, config)
    # Only last 5 decisions should appear
    assert "Job 19" in prompt
    assert "Job 0" not in prompt


def test_parse_claude_response_valid_json():
    from scraper import parse_claude_response
    raw = '{"relevant": true, "category": "backend", "confidence": 0.92, "yoe": "2-3"}'
    result = parse_claude_response(raw)
    assert result["relevant"] is True
    assert result["category"] == "backend"
    assert result["confidence"] == 0.92
    assert result["yoe"] == "2-3"


def test_parse_claude_response_json_in_text():
    from scraper import parse_claude_response
    raw = 'Here is my answer: {"relevant": false, "category": null, "confidence": 0.95, "yoe": "unknown"} done.'
    result = parse_claude_response(raw)
    assert result["relevant"] is False


def test_parse_claude_response_malformed_returns_low_confidence():
    from scraper import parse_claude_response
    result = parse_claude_response("Sorry I cannot classify this.")
    assert result["confidence"] < 0.60
    assert result["relevant"] is False
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "claude_prompt or parse_claude" -v`
Expected: `ImportError` — functions not defined.

- [ ] **Step 3: Implement prompt builder and response parser in `scraper.py`**

Add after `feedback_lookup`:

```python
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
            pass

    # Fallback: unparseable response → flag for review
    return {"relevant": False, "category": None, "confidence": 0.0, "yoe": "unknown"}
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "claude_prompt or parse_claude" -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: Claude prompt builder and response parser"
```

---

## Task 8: Claude Classifier

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Calls the Anthropic API. Uses `ANTHROPIC_API_KEY` from environment. Tests mock the client.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
from unittest.mock import MagicMock, patch


def test_claude_classify_returns_classification(tmp_path):
    from scraper import claude_classify
    feedback = {"decisions": [], "ambiguous_titles": []}
    config = {
        "classifier": {
            "confidence_threshold": 0.60,
            "claude_model": "claude-haiku-4-5-20251001",
            "max_few_shot_examples": 15,
        }
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"relevant": true, "category": "backend", "confidence": 0.93, "yoe": "2-3"}')]

    with patch("scraper.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        result = claude_classify("Backend Developer", "Python, Django, REST APIs.", feedback, config)

    assert result["relevant"] is True
    assert result["category"] == "backend"
    assert result["confidence"] == 0.93


def test_claude_classify_flags_low_confidence(tmp_path):
    from scraper import claude_classify
    feedback = {"decisions": [], "ambiguous_titles": []}
    config = {
        "classifier": {
            "confidence_threshold": 0.60,
            "claude_model": "claude-haiku-4-5-20251001",
            "max_few_shot_examples": 15,
        }
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"relevant": true, "category": "general_swe", "confidence": 0.45, "yoe": "unknown"}')]

    with patch("scraper.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        result = claude_classify("Technical Specialist", "Some job.", feedback, config)

    assert result["flagged_for_review"] is True
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "claude_classify" -v`
Expected: `ImportError` — `claude_classify` not defined.

- [ ] **Step 3: Implement `claude_classify` in `scraper.py`**

Add after `parse_claude_response`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "claude_classify" -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: Claude Haiku classifier with review flagging"
```

---

## Task 9: Scraper — Results Page + Full JD

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
SAMPLE_RESULTS_HTML = """
<html><body>
<div class="organic-job odd" data-url="spl/backend-developer-abc123def456?imo=1">
  <h2 class="title">
    <a class="lk-job-title" href="#!">Backend Developer</a>
  </h2>
  <a class="employer lk-employer" href="#!">Acme Corp</a>
  <span class="description">We build APIs with Python and Django.</span>
  <a class="lk lastseen" href="#!">2 days ago</a>
</div>
<div class="organic-job even" data-url="spl/civil-engineer-xyz789?imo=2">
  <h2 class="title">
    <a class="lk-job-title" href="#!">Civil Engineer</a>
  </h2>
  <a class="employer lk-employer" href="#!">Build Co</a>
  <span class="description">Bridge construction and design.</span>
  <a class="lk lastseen" href="#!">1 day ago</a>
</div>
</body></html>
"""

SAMPLE_SPL_HTML = """
<html><body>
<main class="container-fluid">
<div class="col-xl-7 col-sm-7 col-12 description">
<div class="short-text">
<p>We are looking for a Backend Developer with 3-5 years of Python experience.</p>
<p>You will work with Django, PostgreSQL, and AWS.</p>
</div>
</div>
</main>
</body></html>
"""


def test_fetch_results_page_returns_jobs():
    from scraper import fetch_results_page
    config = {"scraper": {"delay_min": 0, "delay_max": 0, "respect_robots_txt": False}}
    with patch("scraper.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_RESULTS_HTML
        mock_get.return_value = mock_resp
        jobs = fetch_results_page(1, "software engineer", config)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Backend Developer"
    assert jobs[0]["company"] == "Acme Corp"
    assert jobs[0]["job_id"] == "abc123def456"
    assert jobs[0]["slug"] == "spl/backend-developer-abc123def456?imo=1"


def test_fetch_results_page_empty_returns_empty_list():
    from scraper import fetch_results_page
    config = {"scraper": {"delay_min": 0, "delay_max": 0, "respect_robots_txt": False}}
    with patch("scraper.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_get.return_value = mock_resp
        jobs = fetch_results_page(1, "software engineer", config)
    assert jobs == []


def test_fetch_full_jd_returns_text():
    from scraper import fetch_full_jd
    config = {"scraper": {"delay_min": 0, "delay_max": 0}}
    with patch("scraper.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SPL_HTML
        mock_get.return_value = mock_resp
        text = fetch_full_jd("spl/backend-developer-abc123def456?imo=1", config)
    assert "Python" in text
    assert "Django" in text
    assert "3-5 years" in text


def test_fetch_full_jd_returns_empty_on_parse_failure():
    from scraper import fetch_full_jd
    config = {"scraper": {"delay_min": 0, "delay_max": 0}}
    with patch("scraper.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><p>No description here.</p></body></html>"
        mock_get.return_value = mock_resp
        text = fetch_full_jd("spl/some-job?imo=1", config)
    assert text == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "fetch_results or fetch_full" -v`
Expected: `ImportError` — functions not defined.

- [ ] **Step 3: Implement scraper functions in `scraper.py`**

Add after `claude_classify`:

```python
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
    """Extract the hash ID from a slug like 'spl/backend-dev-abc123def456?imo=1'."""
    # Hash is the last hex segment before the query string
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "fetch_results or fetch_full" -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: Eluta results page scraper and full JD fetcher"
```

---

## Task 10: Main Pipeline

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Orchestrates all previous pieces. Deduplicates by job ID within a run.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def _make_full_config():
    return {
        "sites": {"eluta": {"enabled": True, "query": "software engineer", "max_pages": 2}},
        "categories": {
            "backend": ["backend developer"],
            "general_swe": [],
        },
        "filters": {
            "seniority_blocklist": [" lead"],
            "non_technical_blocklist": ["millwright", "civil engineer"],
        },
        "classifier": {
            "confidence_threshold": 0.60,
            "claude_model": "claude-haiku-4-5-20251001",
            "max_few_shot_examples": 15,
        },
        "scraper": {"delay_min": 0, "delay_max": 0, "respect_robots_txt": False},
    }


def test_pipeline_accepts_relevant_job():
    from scraper import run_scrape

    config = _make_full_config()
    feedback = {"decisions": [], "ambiguous_titles": []}

    page1_jobs = [
        {"title": "Backend Developer", "company": "Acme", "snippet": "Python APIs",
         "date_posted": "1 day ago", "job_id": "aaa111", "slug": "spl/backend-aaa111?imo=1",
         "url": "https://www.eluta.ca/spl/aaa111"},
    ]

    with patch("scraper.fetch_results_page") as mock_page, \
         patch("scraper.fetch_full_jd") as mock_jd, \
         patch("scraper._check_robots"):
        # Page 1 has 1 job, page 2 is empty → stops
        mock_page.side_effect = [page1_jobs, []]
        mock_jd.return_value = "3-5 years Python experience with Django and AWS."

        accepted, review, filtered, _, _ = run_scrape(config, feedback)

    assert len(accepted) == 1
    assert accepted[0]["title"] == "Backend Developer"
    assert accepted[0]["category"] == "backend"
    assert accepted[0]["yoe_required"] == "2-3"  # lower bound of "3-5 years" → _categorize_yoe(3) → "2-3"


def test_pipeline_filters_non_technical():
    from scraper import run_scrape

    config = _make_full_config()
    feedback = {"decisions": [], "ambiguous_titles": []}

    page1_jobs = [
        {"title": "Civil Engineer", "company": "Build Co", "snippet": "Bridges",
         "date_posted": "1 day ago", "job_id": "bbb222", "slug": "spl/civil-bbb222?imo=1",
         "url": "https://www.eluta.ca/spl/bbb222"},
    ]

    with patch("scraper.fetch_results_page") as mock_page, \
         patch("scraper.fetch_full_jd") as mock_jd, \
         patch("scraper._check_robots"):
        mock_page.side_effect = [page1_jobs, []]
        mock_jd.return_value = ""

        accepted, review, filtered, _, _ = run_scrape(config, feedback)

    assert len(accepted) == 0
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Civil Engineer"


def test_pipeline_deduplicates_within_run():
    from scraper import run_scrape

    config = _make_full_config()
    feedback = {"decisions": [], "ambiguous_titles": []}

    same_job = {"title": "Backend Developer", "company": "Acme", "snippet": "Python",
                "date_posted": "1 day ago", "job_id": "aaa111", "slug": "spl/backend-aaa111?imo=1",
                "url": "https://www.eluta.ca/spl/aaa111"}

    with patch("scraper.fetch_results_page") as mock_page, \
         patch("scraper.fetch_full_jd") as mock_jd, \
         patch("scraper._check_robots"):
        # Same job appears on page 1 and page 2
        mock_page.side_effect = [[same_job], [same_job]]
        mock_jd.return_value = "2 years Python experience."

        accepted, review, filtered, _, _ = run_scrape(config, feedback)

    assert len(accepted) == 1  # deduplicated


def test_pipeline_stops_at_max_pages():
    from scraper import run_scrape

    config = _make_full_config()
    config["sites"]["eluta"]["max_pages"] = 2
    feedback = {"decisions": [], "ambiguous_titles": []}

    infinite_page = [
        {"title": "Backend Developer", "company": "Acme", "snippet": "Python",
         "date_posted": "1 day ago", "job_id": f"id{i}", "slug": f"spl/backend-id{i}?imo=1",
         "url": f"https://www.eluta.ca/spl/id{i}"}
        for i in range(10)
    ]

    with patch("scraper.fetch_results_page") as mock_page, \
         patch("scraper.fetch_full_jd") as mock_jd, \
         patch("scraper._check_robots"):
        mock_page.return_value = infinite_page  # always returns results
        mock_jd.return_value = "2 years Python experience."

        accepted, review, filtered, _, pages = run_scrape(config, feedback)

    assert pages == 2  # stopped at max_pages, not from empty page


def test_pipeline_filters_feedback_rejected_title():
    from scraper import run_scrape

    config = _make_full_config()
    feedback = {
        "decisions": [
            {"title": "Backend Developer", "relevant": False, "category": None,
             "reason": "Not actually a dev role", "source": "review"}
        ],
        "ambiguous_titles": []
    }

    page1 = [
        {"title": "Backend Developer", "company": "Acme", "snippet": "Python",
         "date_posted": "1 day ago", "job_id": "aaa111", "slug": "spl/backend-aaa111?imo=1",
         "url": "https://www.eluta.ca/spl/aaa111"},
    ]

    with patch("scraper.fetch_results_page") as mock_page, \
         patch("scraper.fetch_full_jd") as mock_jd, \
         patch("scraper._check_robots"):
        mock_page.side_effect = [page1, []]
        mock_jd.return_value = "Some description."

        accepted, review, filtered, _, _ = run_scrape(config, feedback)

    assert len(accepted) == 0
    assert any(j["title"] == "Backend Developer" for j in filtered)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "pipeline" -v`
Expected: `ImportError` — `run_scrape` not defined.

- [ ] **Step 3: Implement `run_scrape` in `scraper.py`**

Add after `fetch_full_jd`:

```python
# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def classify_job(job: dict, jd_text: str, feedback: dict, config: dict, is_ambiguous: bool = False) -> dict:
    """
    Run the Flow D classifier on a single job.
    is_ambiguous: True when the title came from the ambiguous list — skip straight to Claude.
    Returns job dict enriched with: category, confidence, flagged_for_review, yoe_required.
    """
    title = job["title"]

    if not is_ambiguous:
        # Step 1: feedback lookup
        fb_decision = feedback_lookup(title, feedback)
        if fb_decision:
            if not fb_decision["relevant"]:
                # Previously confirmed as not relevant — filter it
                return {**job, "relevant": False, "category": None,
                        "confidence": 1.0, "flagged_for_review": False, "yoe_required": "unknown"}
            return {
                **job,
                "category": fb_decision["category"] or "general_swe",
                "confidence": 1.0,
                "flagged_for_review": False,
                "yoe_required": extract_yoe(jd_text),
            }

        # Step 2: keyword match
        kw_category = keyword_classify(title, config["categories"])
        if kw_category:
            return {
                **job,
                "category": kw_category,
                "confidence": None,
                "flagged_for_review": False,
                "yoe_required": extract_yoe(jd_text),
            }

    # Step 3: Claude
    claude_result = claude_classify(title, jd_text, feedback, config)
    yoe = extract_yoe(jd_text)  # compute once; fall back to Claude's yoe if regex found nothing
    return {
        **job,
        "category": claude_result["category"] or "general_swe",
        "confidence": claude_result["confidence"],
        "flagged_for_review": claude_result["flagged_for_review"],
        "relevant": claude_result["relevant"],
        "yoe_required": yoe if yoe != "unknown" else claude_result.get("yoe", "unknown"),
    }


def run_scrape(config: dict, feedback: dict) -> tuple[list, list, list, int, int]:
    """
    Main scrape loop. Returns (accepted, review, filtered, duplicate_count, pages_scraped).
    - accepted: classified jobs above confidence threshold
    - review: borderline jobs flagged for human review
    - filtered: hard-filtered jobs (non-technical / seniority)
    - duplicate_count: jobs skipped due to duplicate job_id in this run
    - pages_scraped: number of result pages fetched
    """
    _check_robots(config)

    eluta_cfg = config["sites"]["eluta"]
    query = eluta_cfg["query"]
    max_pages = eluta_cfg["max_pages"]

    seen_ids: set[str] = set()
    accepted: list[dict] = []
    review: list[dict] = []
    filtered: list[dict] = []
    duplicate_count = 0

    for page in range(1, max_pages + 1):
        page_jobs = fetch_results_page(page, query, config)

        if not page_jobs:
            break  # No more results

        page_new = 0
        for job in page_jobs:
            jid = job["job_id"]
            if jid in seen_ids:
                duplicate_count += 1
                continue
            seen_ids.add(jid)
            page_new += 1

            ambiguous = [t.lower() for t in feedback.get("ambiguous_titles", [])]
            action, reason = hard_filter(job["title"], config, ambiguous)

            if action == "filter":
                filtered.append({**job, "filter_reason": reason})
                continue

            # Fetch full JD for all non-filtered jobs
            jd_text = fetch_full_jd(job["slug"], config)

            classified = classify_job(job, jd_text, feedback, config, is_ambiguous=(action == "ambiguous"))

            # For Claude-classified jobs: check relevance flag
            if "relevant" in classified and not classified["relevant"]:
                filtered.append({**job, "filter_reason": "Claude: not relevant"})
                continue

            if classified.get("flagged_for_review"):
                review.append(classified)
            else:
                accepted.append(classified)

        # Stop if entire page was duplicates
        if page_new == 0 and page > 1:
            break

    return accepted, review, filtered, duplicate_count, page
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "pipeline" -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: main pipeline orchestrating scrape, filter, classify, deduplicate"
```

---

## Task 11: XLSX Exporter

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
from openpyxl import load_workbook


def _make_accepted_jobs():
    return [
        {
            "job_id": "abc123", "title": "Backend Developer", "company": "Acme Corp",
            "date_posted": "1 day ago", "category": "backend", "yoe_required": "2-3",
            "url": "https://www.eluta.ca/spl/abc123", "confidence": None,
        },
        {
            "job_id": "def456", "title": "ML Engineer", "company": "AI Co",
            "date_posted": "3 days ago", "category": "ai_ml", "yoe_required": "4-5",
            "url": "https://www.eluta.ca/spl/def456", "confidence": 0.87,
        },
    ]


def test_write_accepted_xlsx_creates_file(tmp_path):
    from scraper import write_accepted_xlsx
    out = tmp_path / "jobs.xlsx"
    write_accepted_xlsx(_make_accepted_jobs(), str(out))
    assert out.exists()


def test_write_accepted_xlsx_has_correct_headers(tmp_path):
    from scraper import write_accepted_xlsx
    out = tmp_path / "jobs.xlsx"
    write_accepted_xlsx(_make_accepted_jobs(), str(out))
    wb = load_workbook(str(out))
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, 9)]
    assert "title" in headers
    assert "category" in headers
    assert "yoe_required" in headers
    assert "url" in headers


def test_write_accepted_xlsx_has_correct_row_count(tmp_path):
    from scraper import write_accepted_xlsx
    out = tmp_path / "jobs.xlsx"
    write_accepted_xlsx(_make_accepted_jobs(), str(out))
    wb = load_workbook(str(out))
    ws = wb.active
    # 1 header row + 2 data rows
    assert ws.max_row == 3


def test_write_review_xlsx_has_confirm_column(tmp_path):
    from scraper import write_review_xlsx
    out = tmp_path / "review.xlsx"
    write_review_xlsx(_make_accepted_jobs(), str(out))
    wb = load_workbook(str(out))
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, 12)]
    assert "confirm" in headers
    assert "reason" in headers


def test_write_accepted_xlsx_url_is_hyperlink(tmp_path):
    from scraper import write_accepted_xlsx, _ACCEPTED_COLUMNS
    out = tmp_path / "jobs.xlsx"
    write_accepted_xlsx(_make_accepted_jobs(), str(out))
    wb = load_workbook(str(out))
    ws = wb.active
    url_col = _ACCEPTED_COLUMNS.index("url") + 1  # 1-based
    assert ws.cell(2, url_col).hyperlink is not None
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "xlsx" -v`
Expected: `ImportError` — functions not defined.

- [ ] **Step 3: Implement XLSX exporters in `scraper.py`**

Add after `run_scrape`:

```python
# ---------------------------------------------------------------------------
# XLSX Export
# ---------------------------------------------------------------------------

_ACCEPTED_COLUMNS = ["job_id", "title", "company", "date_posted", "category",
                     "yoe_required", "url", "confidence"]

_REVIEW_COLUMNS = _ACCEPTED_COLUMNS + ["confirm", "reason"]

_HEADER_FILL = PatternFill("solid", fgColor="2F4F4F")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def _apply_xlsx_formatting(ws, columns: list[str]) -> None:
    """Apply header formatting, auto-filter, and freeze top row."""
    # Header row
    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(1, col_idx)
        cell.value = col_name
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    # Auto-filter on all columns
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}1"

    # Freeze top row
    ws.freeze_panes = "A2"

    # Column widths
    widths = {"title": 40, "company": 25, "url": 50, "category": 15,
              "yoe_required": 12, "date_posted": 15, "confidence": 12,
              "job_id": 34, "confirm": 10, "reason": 40}
    for col_idx, col_name in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = widths.get(col_name, 15)


def _write_job_row(ws, row_idx: int, job: dict, columns: list[str]) -> None:
    """Write a single job row with category color-coding and URL hyperlink."""
    fill_color = CATEGORY_COLORS.get(job.get("category", "general_swe"), "FFFFFF")
    row_fill = PatternFill("solid", fgColor=fill_color)

    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(row_idx, col_idx)
        value = job.get(col_name, "")

        if col_name == "url" and value:
            cell.hyperlink = value
            cell.value = value
            cell.font = Font(color="0563C1", underline="single")
        elif col_name == "confidence" and value is not None:
            cell.value = f"{value:.0%}" if isinstance(value, float) else ""
        else:
            cell.value = value if value is not None else ""

        if col_name != "url":
            cell.fill = row_fill


def write_accepted_xlsx(jobs: list[dict], filepath: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    _apply_xlsx_formatting(ws, _ACCEPTED_COLUMNS)
    for i, job in enumerate(jobs, start=2):
        _write_job_row(ws, i, job, _ACCEPTED_COLUMNS)
    wb.save(filepath)


def write_review_xlsx(jobs: list[dict], filepath: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Review"
    _apply_xlsx_formatting(ws, _REVIEW_COLUMNS)
    for i, job in enumerate(jobs, start=2):
        _write_job_row(ws, i, job, _REVIEW_COLUMNS)
        # Leave confirm and reason blank for user to fill
    wb.save(filepath)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "xlsx" -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: XLSX exporter with color-coding, auto-filters, hyperlinks"
```

---

## Task 12: Filtered JSON Exporter

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def test_write_filtered_json_creates_file(tmp_path):
    from scraper import write_filtered_json
    jobs = [
        {"job_id": "abc123", "title": "Civil Engineer", "company": "Build Co",
         "date_posted": "1 day ago", "snippet": "Bridges and roads.",
         "filter_reason": "non-technical blocklist match: 'civil engineer'",
         "url": "https://www.eluta.ca/spl/abc123"},
    ]
    out = tmp_path / "filtered.json"
    write_filtered_json(jobs, str(out))
    assert out.exists()


def test_write_filtered_json_correct_structure(tmp_path):
    from scraper import write_filtered_json
    jobs = [
        {"job_id": "abc123", "title": "Civil Engineer", "company": "Build Co",
         "date_posted": "1 day ago", "snippet": "Bridges.",
         "filter_reason": "non-technical blocklist match: 'civil engineer'",
         "url": "https://www.eluta.ca/spl/abc123"},
    ]
    out = tmp_path / "filtered.json"
    write_filtered_json(jobs, str(out))
    data = json.loads(out.read_text())
    assert isinstance(data, list)
    assert data[0]["title"] == "Civil Engineer"
    assert "filter_reason" in data[0]
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "filtered_json" -v`
Expected: `ImportError` — `write_filtered_json` not defined.

- [ ] **Step 3: Implement `write_filtered_json` in `scraper.py`**

Add after `write_review_xlsx`:

```python
# ---------------------------------------------------------------------------
# Filtered JSON Export
# ---------------------------------------------------------------------------

_FILTERED_FIELDS = ["job_id", "title", "company", "date_posted", "snippet",
                    "filter_reason", "url"]


def write_filtered_json(jobs: list[dict], filepath: str) -> None:
    records = [{k: job.get(k, "") for k in _FILTERED_FIELDS} for job in jobs]
    with open(filepath, "w") as f:
        json.dump(records, f, indent=2)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "filtered_json" -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: filtered JSON exporter"
```

---

## Task 13: Feedback Ingester

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Handles both `.xlsx` (review file) and `.json` (filtered disputes). Auto-detects by extension.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scraper.py`:

```python
def test_ingest_feedback_from_review_xlsx(tmp_path):
    from scraper import write_review_xlsx, ingest_feedback
    # Create a review file with user decisions filled in
    jobs = [
        {"job_id": "abc123", "title": "Platform Engineer", "company": "Acme",
         "date_posted": "1 day ago", "category": "cloud_devops", "yoe_required": "2-3",
         "url": "https://www.eluta.ca/spl/abc123", "confidence": 0.55,
         "confirm": "yes", "reason": "Uses AWS and Kubernetes"},
        {"job_id": "def456", "title": "Project Coordinator", "company": "Corp",
         "date_posted": "2 days ago", "category": "general_swe", "yoe_required": "unknown",
         "url": "https://www.eluta.ca/spl/def456", "confidence": 0.50,
         "confirm": "no", "reason": "Not a technical role"},
    ]
    review_path = tmp_path / "review.xlsx"
    write_review_xlsx(jobs, str(review_path))

    feedback = {"decisions": [], "ambiguous_titles": []}
    updated = ingest_feedback(str(review_path), feedback)

    assert len(updated["decisions"]) == 2
    confirmed = next(d for d in updated["decisions"] if d["title"] == "Platform Engineer")
    assert confirmed["relevant"] is True
    assert confirmed["category"] == "cloud_devops"

    rejected = next(d for d in updated["decisions"] if d["title"] == "Project Coordinator")
    assert rejected["relevant"] is False


def test_ingest_feedback_from_dispute_json(tmp_path):
    from scraper import ingest_feedback
    disputed = [
        {
            "job_id": "abc123",
            "title": "Controls Engineer",
            "company": "Acme",
            "date_posted": "1 day ago",
            "snippet": "Python and PLC experience required.",
            "filter_reason": "non-technical blocklist match: 'engineer'",
            "url": "https://www.eluta.ca/spl/abc123",
            "dispute": True,
            "reason": "Software controls role — Python and PLC",
        }
    ]
    json_path = tmp_path / "filtered.json"
    json_path.write_text(json.dumps(disputed))

    feedback = {"decisions": [], "ambiguous_titles": []}
    updated = ingest_feedback(str(json_path), feedback)

    # Title added to ambiguous list (goes to Claude next run)
    assert "controls engineer" in [t.lower() for t in updated["ambiguous_titles"]]
    # Also added as positive few-shot example
    assert any(d["title"] == "Controls Engineer" and d["relevant"] is True
               for d in updated["decisions"])


def test_ingest_feedback_skips_json_without_dispute_flag(tmp_path):
    from scraper import ingest_feedback
    jobs = [
        {"job_id": "abc123", "title": "Civil Engineer", "filter_reason": "non-technical",
         "snippet": "", "company": "", "date_posted": "", "url": ""}
        # No "dispute" key
    ]
    json_path = tmp_path / "filtered.json"
    json_path.write_text(json.dumps(jobs))

    feedback = {"decisions": [], "ambiguous_titles": []}
    updated = ingest_feedback(str(json_path), feedback)
    assert len(updated["decisions"]) == 0
    assert len(updated["ambiguous_titles"]) == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_scraper.py -k "ingest_feedback" -v`
Expected: `ImportError` — `ingest_feedback` not defined.

- [ ] **Step 3: Implement `ingest_feedback` in `scraper.py`**

Add after `write_filtered_json`:

```python
# ---------------------------------------------------------------------------
# Feedback Ingester
# ---------------------------------------------------------------------------

def _ingest_from_review_xlsx(filepath: str, feedback: dict) -> dict:
    """Process a review XLSX file. Reads confirm/reason columns filled in by user."""
    from openpyxl import load_workbook
    wb = load_workbook(filepath)
    ws = wb.active

    # Find column indices from header row
    headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
    required = {"title", "category", "confirm", "reason"}
    if not required.issubset(headers.keys()):
        print(f"Warning: review file missing columns {required - set(headers.keys())}")
        return feedback

    for row in range(2, ws.max_row + 1):
        confirm_val = ws.cell(row, headers["confirm"]).value
        if not confirm_val:
            continue  # User left this row blank — skip
        title = ws.cell(row, headers["title"]).value or ""
        category = ws.cell(row, headers["category"]).value or "general_swe"
        reason = ws.cell(row, headers["reason"]).value or ""  # "reason" guaranteed by required-columns guard above
        confirmed = str(confirm_val).strip().lower() in ("yes", "y", "true", "1")

        feedback["decisions"].append({
            "title": title,
            "relevant": confirmed,
            "category": category if confirmed else None,
            "reason": reason,
            "source": "review",
        })

    return feedback


def _ingest_from_dispute_json(filepath: str, feedback: dict) -> dict:
    """Process a filtered JSON file. Only processes entries with dispute: true."""
    with open(filepath) as f:
        jobs = json.load(f)

    for job in jobs:
        if not job.get("dispute"):
            continue
        title = job.get("title", "")
        reason = job.get("reason", "")

        # Add to ambiguous list (bypasses hard filter next run → goes to Claude)
        title_lower = title.lower().strip()
        if title_lower not in [t.lower() for t in feedback["ambiguous_titles"]]:
            feedback["ambiguous_titles"].append(title_lower)

        # Add as positive few-shot example for Claude
        feedback["decisions"].append({
            "title": title,
            "relevant": True,
            "category": "general_swe",  # Claude will re-classify properly next run
            "reason": reason,
            "source": "dispute",
        })

    return feedback


def ingest_feedback(filepath: str, feedback: dict) -> dict:
    """
    Auto-detect file type by extension and ingest feedback.
    .xlsx → review file (confirm/reject borderline jobs)
    .json → dispute file (contest hard-filtered jobs)
    """
    if filepath.endswith(".xlsx"):
        return _ingest_from_review_xlsx(filepath, feedback)
    elif filepath.endswith(".json"):
        return _ingest_from_dispute_json(filepath, feedback)
    else:
        print(f"Unknown file type: {filepath}. Expected .xlsx or .json")
        return feedback
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_scraper.py -k "ingest_feedback" -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: feedback ingester for review XLSX and dispute JSON"
```

---

## Task 14: CLI Entry Point and Terminal Summary

**Files:**
- Modify: `scraper.py`

- [ ] **Step 1: Implement terminal summary and `main()` in `scraper.py`**

Add at the bottom of `scraper.py`:

```python
# ---------------------------------------------------------------------------
# Terminal Summary
# ---------------------------------------------------------------------------

def print_summary(accepted: list, review: list, filtered: list,
                  duplicate_count: int, pages_scraped: int,
                  out_path: str) -> None:
    total = len(accepted) + len(review) + len(filtered) + duplicate_count
    print()
    print(f"Scraped {total} jobs across {pages_scraped} pages")
    print(f"  Accepted:        {len(accepted)}")
    print(f"  Hard filtered:   {len(filtered)}  → check output/filtered_{date.today()}.json")
    print(f"  Flagged review:  {len(review)}  → check output/review_{date.today()}.xlsx")
    print(f"  Duplicate skip:  {duplicate_count}")
    print()
    print(f"Saved → {out_path}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Eluta.ca Job Scraper")
    parser.add_argument(
        "--ingest-feedback", metavar="FILE",
        help="Ingest a completed review.xlsx or disputed filtered.json into feedback.json"
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--feedback", default="feedback.json", help="Path to feedback file")
    args = parser.parse_args()

    config = load_config(args.config)
    feedback = load_feedback(args.feedback)

    # Feedback ingestion mode
    if args.ingest_feedback:
        print(f"Ingesting feedback from {args.ingest_feedback}...")
        before_count = len(feedback.get("decisions", []))  # capture before in-place mutation
        updated = ingest_feedback(args.ingest_feedback, feedback)
        save_feedback(updated, args.feedback)
        new_decisions = len(updated["decisions"]) - before_count
        print(f"Done. {new_decisions} new decision(s) added to {args.feedback}.")
        return

    # Scrape mode
    os.makedirs("output", exist_ok=True)
    today = date.today()

    print(f"Starting Eluta scrape: '{config['sites']['eluta']['query']}'")
    print(f"Max pages: {config['sites']['eluta']['max_pages']}")
    print()

    accepted, review, filtered, dup_count, pages_scraped = run_scrape(config, feedback)

    accepted_path = f"output/eluta_{today}.xlsx"
    review_path = f"output/review_{today}.xlsx"
    filtered_path = f"output/filtered_{today}.json"

    write_accepted_xlsx(accepted, accepted_path)
    if review:
        write_review_xlsx(review, review_path)
    if filtered:
        write_filtered_json(filtered, filtered_path)

    print_summary(accepted, review, filtered, dup_count, pages_scraped, accepted_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full test suite to confirm everything still passes**

Run: `pytest tests/ -v`
Expected: All tests pass, zero failures.

- [ ] **Step 3: Verify the CLI help works**

Run: `python scraper.py --help`
Expected output:
```
usage: scraper.py [-h] [--ingest-feedback FILE] [--config CONFIG] [--feedback FEEDBACK]

Eluta.ca Job Scraper

options:
  -h, --help            show this help message and exit
  --ingest-feedback FILE
                        Ingest a completed review.xlsx or disputed filtered.json
  --config CONFIG       Path to config file
  --feedback FEEDBACK   Path to feedback file
```

- [ ] **Step 4: Commit**

```bash
git add scraper.py
git commit -m "feat: CLI entry point with terminal summary and --ingest-feedback command"
```

---

## Task 15: End-to-End Smoke Test

**Files:**
- Modify: `tests/test_scraper.py`

A single integration test that wires the full pipeline with mocked HTTP and Claude, confirms the output files are created correctly.

- [ ] **Step 1: Write the smoke test**

Add to `tests/test_scraper.py`:

```python
def test_end_to_end_smoke(tmp_path, monkeypatch):
    """
    Full pipeline smoke test with mocked HTTP and Claude.
    Verifies XLSX + JSON files are created and contain expected data.
    """
    from scraper import run_scrape, write_accepted_xlsx, write_review_xlsx, write_filtered_json

    config = _make_full_config()
    feedback = {"decisions": [], "ambiguous_titles": []}

    page1 = [
        {"title": "Backend Developer", "company": "Acme", "snippet": "Python APIs",
         "date_posted": "1 day ago", "job_id": "aaa111", "slug": "spl/backend-aaa111?imo=1",
         "url": "https://www.eluta.ca/spl/aaa111"},
        {"title": "Civil Engineer", "company": "Build Co", "snippet": "Bridges",
         "date_posted": "2 days ago", "job_id": "bbb222", "slug": "spl/civil-bbb222?imo=2",
         "url": "https://www.eluta.ca/spl/bbb222"},
        {"title": "Technical Specialist", "company": "TechCo", "snippet": "Support role",
         "date_posted": "1 day ago", "job_id": "ccc333", "slug": "spl/tech-ccc333?imo=3",
         "url": "https://www.eluta.ca/spl/ccc333"},
    ]

    mock_claude_response = MagicMock()
    mock_claude_response.content = [MagicMock(
        text='{"relevant": true, "category": "general_swe", "confidence": 0.55, "yoe": "2-3"}'
    )]

    with patch("scraper.fetch_results_page") as mock_page, \
         patch("scraper.fetch_full_jd") as mock_jd, \
         patch("scraper._check_robots"), \
         patch("scraper.anthropic.Anthropic") as MockClient:

        mock_page.side_effect = [page1, []]
        mock_jd.return_value = "3-5 years of Python, Django, REST API experience."
        MockClient.return_value.messages.create.return_value = mock_claude_response

        accepted, review, filtered, _, _ = run_scrape(config, feedback)

    # Backend Developer: keyword match → accepted
    assert any(j["title"] == "Backend Developer" for j in accepted)
    # Civil Engineer: hard filter → filtered
    assert any(j["title"] == "Civil Engineer" for j in filtered)
    # Technical Specialist: Claude confidence 0.55 < 0.60 → review
    assert any(j["title"] == "Technical Specialist" for j in review)

    # Write outputs and verify files
    write_accepted_xlsx(accepted, str(tmp_path / "jobs.xlsx"))
    write_review_xlsx(review, str(tmp_path / "review.xlsx"))
    write_filtered_json(filtered, str(tmp_path / "filtered.json"))

    assert (tmp_path / "jobs.xlsx").exists()
    assert (tmp_path / "review.xlsx").exists()
    assert (tmp_path / "filtered.json").exists()
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest tests/test_scraper.py::test_end_to_end_smoke -v`
Expected: PASS.

- [ ] **Step 3: Run the full test suite one final time**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Final commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "test: end-to-end smoke test covering full pipeline"
```

---

## Setup to Run for Real

After all tasks complete, set your API key and run:

```bash
export ANTHROPIC_API_KEY=your_key_here
python scraper.py
```

To ingest feedback after reviewing output files:

```bash
# After filling in confirm/reason in review_YYYY-MM-DD.xlsx:
python scraper.py --ingest-feedback output/review_2026-03-30.xlsx

# After marking disputes in filtered_YYYY-MM-DD.json:
python scraper.py --ingest-feedback output/filtered_2026-03-30.json
```
