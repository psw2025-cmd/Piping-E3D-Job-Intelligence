from pathlib import Path

from job_intelligence.collection_runner import _filter_profile_jobs
from job_intelligence.models import JobRecord
from job_intelligence.source_config import SourceSpec


def _spec(profile_filter: bool = True) -> SourceSpec:
    return SourceSpec(
        source_id="global_profile_test",
        name="Global profile test",
        source_type="rss",
        enabled=True,
        company="Example EPC",
        options={"url": "https://example.com/jobs.rss", "profile_filter": profile_filter},
    )


def test_profile_filter_keeps_only_relevant_piping_jobs(tmp_path: Path) -> None:
    jobs = [
        JobRecord(
            title="Senior Piping Engineer",
            company="Example EPC",
            description="AVEVA E3D refinery layout role",
        ),
        JobRecord(
            title="Payroll Specialist",
            company="Example EPC",
            description="Payroll and benefits administration",
        ),
    ]

    filtered = _filter_profile_jobs(_spec(), jobs, tmp_path)

    assert [job.title for job in filtered] == ["Senior Piping Engineer"]


def test_profile_filter_can_be_disabled_for_diagnostic_sources(tmp_path: Path) -> None:
    jobs = [
        JobRecord(title="Accountant", company="Example EPC"),
        JobRecord(title="Piping Engineer", company="Example EPC"),
    ]

    filtered = _filter_profile_jobs(_spec(profile_filter=False), jobs, tmp_path)

    assert filtered == jobs
