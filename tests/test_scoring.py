from datetime import UTC, datetime

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
