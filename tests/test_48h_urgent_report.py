from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "scripts" / "build_48h_urgent_report.py"
    spec = importlib.util.spec_from_file_location("build_48h_urgent_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE jobs (
            job_key TEXT, title TEXT, normalized_role TEXT, company TEXT,
            location TEXT, city TEXT, country TEXT, description TEXT,
            apply_url TEXT, source_url TEXT, source_name TEXT,
            published_at TEXT, found_at TEXT, last_seen_at TEXT,
            experience_text TEXT, skills_text TEXT, software_text TEXT,
            sector TEXT, recruiter_name TEXT, recruiter_email TEXT,
            contact_confidence TEXT, match_score INTEGER, match_reasons TEXT,
            gaps TEXT, priority TEXT, application_status TEXT,
            canonical_url TEXT
        );
        """
    )
    rows = [
        (
            "1", "Urgent Lead Piping Engineer", "Lead Piping Engineer", "Wood",
            "Abu Dhabi", "Abu Dhabi", "United Arab Emirates",
            "Immediate joining for an offshore AVEVA E3D project.", "",
            "https://example.com/1", "Wood official", "2026-07-28T12:00:00+00:00",
            "2026-07-29T00:00:00+00:00", "", "15 years", "", "E3D",
            "Offshore", "", "", "", 88, "", "", "critical", "new",
            "https://example.com/1",
        ),
        (
            "2", "Senior Piping Designer", "Senior Piping Designer", "KBR",
            "Houston, Texas", "Houston", "United States",
            "PDMS piping layout and model review.", "", "https://example.com/2",
            "KBR official", "2026-07-27T12:00:00+00:00",
            "2026-07-29T00:00:00+00:00", "", "12 years", "", "PDMS",
            "Oil and Gas", "", "", "", 76, "", "", "high", "new",
            "https://example.com/2",
        ),
        (
            "3", "Piping Checker", "Piping Checker", "Example EPC", "Mumbai",
            "Mumbai", "India", "Urgent SP3D requirement.", "",
            "https://example.com/3", "Recruiter alert", "",
            "2026-07-29T00:00:00+00:00", "", "20 years", "", "SP3D",
            "Refinery", "", "", "", 71, "", "", "high", "new",
            "https://example.com/3",
        ),
    ]
    connection.executemany(
        "INSERT INTO jobs VALUES (" + ",".join("?" for _ in range(27)) + ")",
        rows,
    )
    connection.commit()
    connection.close()


def test_report_separates_proven_recent_and_unknown_dates(tmp_path: Path) -> None:
    module = _module()
    db_path = tmp_path / "jobs.db"
    md_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    _database(db_path)

    module.write_report(
        module.load_rows(db_path),
        md_path,
        json_path,
        now_utc=datetime(2026, 7, 29, tzinfo=UTC),
        hours=48,
        timezone_name="Asia/Kolkata",
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metrics"]["confirmed_recent"] == 2
    assert payload["metrics"]["confirmed_urgent"] == 1
    assert payload["metrics"]["urgent_date_unknown"] == 1
    report = md_path.read_text(encoding="utf-8")
    assert "Urgent Lead Piping Engineer" in report
    assert "Piping Checker" in report
    assert "not claimed as today/yesterday" in report


def test_parse_datetime_rejects_unproven_text() -> None:
    module = _module()
    assert module.parse_datetime("recently") is None
    assert module.parse_datetime("2026-07-28") is not None
