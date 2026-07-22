from pathlib import Path

from job_intelligence.database import connect, fetch_jobs, upsert_job
from job_intelligence.models import JobRecord


def test_reimport_preserves_user_tracking_and_contact(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    first = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        description="Refinery E3D role",
        recruiter_email="recruiter@example.com",
        contact_confidence="PUBLIC_UNVERIFIED",
    )
    assert upsert_job(db_path, first) is True
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE jobs SET application_status='applied' WHERE job_key=?",
            (first.job_key,),
        )

    reimport = JobRecord(
        title=first.title,
        company=first.company,
        description=first.description,
    )
    assert upsert_job(db_path, reimport) is False

    row = fetch_jobs(db_path)[0]
    assert row["application_status"] == "applied"
    assert row["recruiter_email"] == "recruiter@example.com"
    assert row["contact_confidence"] == "PUBLIC_UNVERIFIED"


def test_url_enrichment_updates_existing_record(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    initial = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        location="Mumbai",
        description="Refinery E3D role",
    )
    assert upsert_job(db_path, initial) is True
    original_key = initial.job_key

    enriched = JobRecord(
        title=initial.title,
        company=initial.company,
        location=initial.location,
        description=initial.description,
        apply_url="https://example.com/jobs/123?utm_source=mail",
    )
    assert upsert_job(db_path, enriched) is False

    rows = fetch_jobs(db_path)
    assert len(rows) == 1
    assert rows[0]["job_key"] == original_key
    assert rows[0]["canonical_url"] == "https://example.com/jobs/123"


def test_same_canonical_url_matches_existing_record(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    first = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        apply_url="https://example.com/jobs/123?utm_source=one",
    )
    second = JobRecord(
        title="Updated Senior Piping Engineer",
        company="Example EPC",
        apply_url="https://example.com/jobs/123?utm_source=two",
    )

    assert upsert_job(db_path, first) is True
    assert upsert_job(db_path, second) is False
    assert len(fetch_jobs(db_path)) == 1
