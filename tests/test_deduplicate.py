from job_intelligence.deduplicate import build_job_key, canonicalize_url
from job_intelligence.models import JobRecord


def test_canonical_url_removes_tracking_and_fragment() -> None:
    left = canonicalize_url("https://EXAMPLE.com/jobs/123/?utm_source=x&ref=mail#apply")
    right = canonicalize_url("https://example.com/jobs/123")
    assert left == right


def test_same_canonical_apply_url_has_same_key() -> None:
    first = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        apply_url="https://example.com/jobs/123?utm_campaign=test",
    )
    second = JobRecord(
        title="Different display title",
        company="Example EPC",
        apply_url="https://example.com/jobs/123/",
    )
    assert build_job_key(first) == build_job_key(second)


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
