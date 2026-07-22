from datetime import UTC, datetime
from pathlib import Path

import yaml

from job_intelligence.models import JobRecord
from job_intelligence.scoring import load_scoring_profile, score_job


def test_strong_profile_match_is_high_priority() -> None:
    job = JobRecord(
        title="Senior Piping Layout Engineer",
        company="Example EPC",
        location="Mumbai",
        description=(
            "Senior refinery role requiring AVEVA E3D, piping layout, equipment layout, "
            "brownfield site engineering, punch list work, and degree or diploma."
        ),
        published_at=datetime.now(UTC).isoformat(),
    )
    result = score_job(job)
    assert result.score >= 85
    assert result.priority == "critical"
    assert any("E3D" in reason for reason in result.reasons)


def test_unrelated_role_stays_low() -> None:
    job = JobRecord(
        title="Accountant",
        company="Example Company",
        description="General ledger and taxation work.",
    )
    result = score_job(job)
    assert result.score < 50
    assert result.priority == "low"
    assert result.gaps


def test_scoring_reads_yaml_configuration(tmp_path: Path) -> None:
    (tmp_path / "roles.yaml").write_text(
        yaml.safe_dump(
            {
                "target_roles": ["Custom Pipe Role"],
                "sectors": ["Hydrogen"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "locations.yaml").write_text(
        yaml.safe_dump({"locations": {"priority": ["Test City"]}}),
        encoding="utf-8",
    )
    (tmp_path / "scoring.yaml").write_text(
        yaml.safe_dump(
            {
                "weights": {
                    "target_role": 60,
                    "e3d_pdms": 0,
                    "piping_layout": 0,
                    "sector": 0,
                    "experience": 0,
                    "preferred_location": 20,
                    "site_offshore": 0,
                    "diploma_eligible": 0,
                    "recent_posting": 0,
                },
                "thresholds": {
                    "critical": 90,
                    "high": 70,
                    "normal": 50,
                },
                "terms": {},
            }
        ),
        encoding="utf-8",
    )

    job = JobRecord(
        title="Custom Pipe Role",
        company="Example EPC",
        location="Test City",
    )
    result = score_job(job, config_dir=tmp_path)
    assert result.score == 80
    assert result.priority == "high"


def test_scoring_uses_defaults_for_null_yaml_values(tmp_path: Path) -> None:
    (tmp_path / "roles.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_path / "locations.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_path / "scoring.yaml").write_text(
        yaml.safe_dump(
            {
                "weights": None,
                "thresholds": None,
                "terms": None,
                "recent_days": None,
            }
        ),
        encoding="utf-8",
    )

    profile = load_scoring_profile(tmp_path)
    assert profile.weights["target_role"] == 20
    assert profile.thresholds["critical"] == 85
    assert profile.recent_days == 7

    result = score_job(
        JobRecord(
            title="Senior Piping Engineer",
            company="Example EPC",
            description="AVEVA E3D refinery role",
        ),
        profile=profile,
    )
    assert result.score > 0


def test_scoring_uses_defaults_for_invalid_numeric_overrides(tmp_path: Path) -> None:
    (tmp_path / "roles.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_path / "locations.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_path / "scoring.yaml").write_text(
        yaml.safe_dump(
            {
                "weights": {"target_role": None},
                "thresholds": {"critical": "not-a-number"},
                "recent_days": "invalid",
            }
        ),
        encoding="utf-8",
    )

    profile = load_scoring_profile(tmp_path)
    assert profile.weights["target_role"] == 20
    assert profile.thresholds["critical"] == 85
    assert profile.recent_days == 7
