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
