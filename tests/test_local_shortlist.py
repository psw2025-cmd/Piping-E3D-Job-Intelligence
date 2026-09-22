import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from job_intelligence.local_shortlist import build_shortlist, write_shortlist

CONFIG = Path(__file__).resolve().parents[1] / "config"
NOW = datetime(2026, 9, 23, tzinfo=UTC)


def job(**overrides):
    return {
        "company": "Example",
        "title": "Senior Piping Designer",
        "location": "Mumbai",
        "apply_url": "https://example.com/jobs/1",
        "match_score": 80,
        **overrides,
    }


@pytest.mark.parametrize(
    "location,city",
    [
        ("New Mumbai", "Navi Mumbai"),
        ("Navi-Mumbai", "Navi Mumbai"),
        ("New Bombay", "Navi Mumbai"),
        ("Airoli", "Navi Mumbai"),
        ("Vikhroli, West Mumbai", "Mumbai"),
        ("Thane / Pune", "Thane"),
        ("Pune / Thane", "Thane"),
        ("Wagle Estate", "Thane"),
    ],
)
def test_local_aliases_and_multilocation(location, city):
    result = build_shortlist([job(location=location)], CONFIG, now=NOW)
    assert result[0]["target_cities"] == [city]
    assert result[0]["location"] == location


@pytest.mark.parametrize(
    "overrides",
    [
        {"location": "Chennai", "city": "Mumbai", "description": "Mumbai head office"},
        {"location": "India", "description": "Mumbai office"},
        {"location": "Maharashtra"},
        {"location": "Methane"},
        {"title": "Electrical Designer E3D"},
        {"title": "Accountant", "description": "piping projects"},
        {"description": "Unfortunately this position has been closed"},
        {"application_status": "closed"},
        {"description": "This vacancy has now expired. Please see similar roles below."},
        {"description": "Apply by 05 Jul 2026. Deadline passed. Apply Now"},
        {"description": "DEADLINE\nPASSED"},
        {"closing_at": "2026-09-22"},
        {"apply_url": "javascript:alert(1)"},
    ],
)
def test_false_matches_are_excluded(overrides):
    assert build_shortlist([job(**overrides)], CONFIG, now=NOW) == []


def test_dates_deduplication_and_partial_report(tmp_path):
    rows = [
        job(published_at="Sep 8, 2026"),
        job(published_at="Sep 8, 2026"),
        job(apply_url="https://example.com/2", published_at=""),
        job(apply_url="https://example.com/3", published_at="2026-10-01"),
    ]
    report = write_shortlist(rows, tmp_path, CONFIG, collection_status="partial", now=NOW)
    data = json.loads((tmp_path / "MUMBAI_THANE_NAVI_MUMBAI.json").read_text())
    assert data["count"] == 3
    assert {j["publication_status"] for j in data["jobs"]} == {
        "last_30_days",
        "unknown",
        "future_date_review",
    }
    assert "partial" in report and "incomplete coverage" in report
