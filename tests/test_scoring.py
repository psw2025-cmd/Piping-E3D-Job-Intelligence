from datetime import UTC, datetime
from pathlib import Path

import yaml

from job_intelligence.models import JobRecord
from job_intelligence.scoring import score_job


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
