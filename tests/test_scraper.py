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


# ---------------------------------------------------------------------------
# TASK 4: YOE Extractor Tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TASK 5: Keyword Classifier Tests
# ---------------------------------------------------------------------------

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
