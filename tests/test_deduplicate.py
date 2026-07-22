from job_intelligence.deduplicate import build_job_key, canonicalize_url
from job_intelligence.models import JobRecord


def test_canonical_url_removes_only_known_tracking_and_fragment() -> None:
    canonical = canonicalize_url(
        "https://EXAMPLE.com/jobs/123/?reference=ABC&source_id=7"
        "&utm_source=mail&gclid=x#apply"
    )
    assert canonical == "https://example.com/jobs/123?reference=ABC&source_id=7"


def test_adding_apply_url_does_not_change_primary_key() -> None:
    first = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        location="Mumbai",
        description="AVEVA E3D piping layout role",
    )
    enriched = JobRecord(
        title=first.title,
        company=first.company,
        location=first.location,
        description=first.description,
        apply_url="https://example.com/jobs/123",
    )
    assert build_job_key(first) == build_job_key(enriched)


def test_field_fallback_is_stable() -> None:
    first = JobRecord(
        title=" Senior   E3D Designer ",
        company="Example EPC",
        location="Mumbai",
        description="AVEVA E3D piping layout role",
    )
    second = JobRecord(
        title="senior e3d designer",
        company="example-epc",
        location="MUMBAI",
        description="AVEVA E3D piping layout role",
    )
    assert build_job_key(first) == build_job_key(second)


def test_full_description_participates_in_key() -> None:
    shared_prefix = "same " * 150
    first = JobRecord(
        title="Piping Engineer",
        company="Example EPC",
        description=shared_prefix + "alpha",
    )
    second = JobRecord(
        title="Piping Engineer",
        company="Example EPC",
        description=shared_prefix + "beta",
    )
    assert build_job_key(first) != build_job_key(second)
