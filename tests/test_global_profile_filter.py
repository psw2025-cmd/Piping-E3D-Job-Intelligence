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
        options={
            "url": "https://example.com/jobs.rss",
            "profile_filter": profile_filter,
            "include_terms": [
                "piping",
                "pipe layout",
                "plant layout",
                "e3d",
                "pdms",
                "sp3d",
                "3d model",
            ],
        },
    )


def test_profile_filter_uses_actual_title_discipline() -> None:
    jobs = [
        JobRecord(title="Senior Piping Engineer", company="Example EPC"),
        JobRecord(
            title="Mechanical Designer",
            company="Example EPC",
            description="Plant designer using AVEVA E3D and PDMS for piping layout.",
        ),
        JobRecord(
            title="Construction Superintendent (Piping) - Fabrication Yard",
            company="Example EPC",
        ),
        JobRecord(
            title="Lead Commissioning Engineer - Telecom – "
            "(WHT's Subsea Cable & Piping)",
            company="Example EPC",
            description="Telecommunications commissioning role.",
        ),
        JobRecord(
            title="Lead Commissioning Engineer - Telecom – "
            "(WHT's Subsea Cable & Piping",
            company="Example EPC",
            description="Telecommunications commissioning role.",
        ),
        JobRecord(
            title="Specialist Planning & Cost Engineer - "
            "(WHT's Subsea Cable & Piping)",
            company="Example EPC",
        ),
        JobRecord(title="Payroll Specialist", company="Example EPC"),
    ]
    filtered = _filter_profile_jobs(_spec(), jobs)
    assert [job.title for job in filtered] == [
        "Senior Piping Engineer",
        "Mechanical Designer",
        "Construction Superintendent (Piping) - Fabrication Yard",
    ]


def test_profile_filter_can_be_disabled() -> None:
    jobs = [JobRecord(title="Accountant", company="Example EPC")]
    assert _filter_profile_jobs(_spec(profile_filter=False), jobs) == jobs
