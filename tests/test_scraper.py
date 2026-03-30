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


# ---------------------------------------------------------------------------
# TASK 6: Feedback Lookup Tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TASK 7: Claude Prompt Builder and Response Parser Tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TASK 8: Claude Classifier Tests
# ---------------------------------------------------------------------------

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
