from job_intelligence.collection_runner import _filter_profile_jobs
from job_intelligence.models import JobRecord
from job_intelligence.source_config import SourceSpec


def _spec(profile_filter: bool = True) -> SourceSpec:
    return SourceSpec(
        source_id="profile_test",
        name="Profile test",
        source_type="rss",
        enabled=True,
        company="Example EPC",
        options={"url": "https://example.com/jobs.rss", "profile_filter": profile_filter},
    )


def test_profile_filter_keeps_normalized_or_scored_jobs() -> None:
    jobs = [
        JobRecord(
            title="Senior Piping Engineer",
            company="Example EPC",
            normalized_role="Senior Piping Engineer",
            match_score=70,
        ),
        JobRecord(title="Mechanical Designer", company="Example EPC", match_score=20),
        JobRecord(title="Payroll Specialist", company="Example EPC", match_score=0),
    ]
    filtered = _filter_profile_jobs(_spec(), jobs)
    assert [job.title for job in filtered] == [
        "Senior Piping Engineer",
        "Mechanical Designer",
    ]


def test_profile_filter_can_be_disabled() -> None:
    jobs = [JobRecord(title="Accountant", company="Example EPC")]
    assert _filter_profile_jobs(_spec(profile_filter=False), jobs) == jobs
