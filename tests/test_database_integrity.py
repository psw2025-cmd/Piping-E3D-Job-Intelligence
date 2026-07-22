from pathlib import Path

from job_intelligence.database import connect, fetch_jobs, init_database, upsert_job
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


def test_identical_fields_with_distinct_urls_stay_separate(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    first = JobRecord(
        title="Piping Engineer",
        company="Example EPC",
        description="Same public description",
        apply_url="https://example.com/jobs/one",
    )
    second = JobRecord(
        title=first.title,
        company=first.company,
        description=first.description,
        apply_url="https://example.com/jobs/two",
    )

    assert upsert_job(db_path, first) is True
    assert upsert_job(db_path, second) is True
    assert len(fetch_jobs(db_path)) == 2


def test_existing_phase1_database_is_migrated(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE jobs (
                job_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                apply_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                found_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                job_type TEXT NOT NULL DEFAULT '',
                salary_text TEXT NOT NULL DEFAULT '',
                experience_text TEXT NOT NULL DEFAULT '',
                skills_text TEXT NOT NULL DEFAULT '',
                recruiter_name TEXT NOT NULL DEFAULT '',
                recruiter_email TEXT NOT NULL DEFAULT '',
                contact_confidence TEXT NOT NULL DEFAULT '',
                match_score INTEGER NOT NULL DEFAULT 0,
                match_reasons TEXT NOT NULL DEFAULT '',
                gaps TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'normal',
                application_status TEXT NOT NULL DEFAULT 'new'
            );
            """
        )
        connection.execute(
            """
            INSERT INTO jobs (
                job_key, title, company, location, description, apply_url,
                found_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-key",
                "Senior Piping Engineer",
                "Example EPC",
                "Mumbai",
                "E3D refinery role",
                "https://example.com/jobs/123?utm_source=mail",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    init_database(db_path)
    row = fetch_jobs(db_path)[0]
    assert row["identity_fingerprint"]
    assert row["canonical_url"] == "https://example.com/jobs/123"
    assert row["job_key"] == "legacy-key"


def test_url_less_reimport_matches_historical_fingerprint(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    original = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        description="Original E3D vacancy text",
        apply_url="https://example.com/jobs/123",
    )
    assert upsert_job(db_path, original) is True

    changed = JobRecord(
        title="Lead Piping Engineer",
        company="Example EPC",
        description="Revised E3D vacancy text",
        apply_url="https://example.com/jobs/123",
    )
    assert upsert_job(db_path, changed) is False

    old_text_without_url = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        description="Original E3D vacancy text",
    )
    assert upsert_job(db_path, old_text_without_url) is False
    assert len(fetch_jobs(db_path)) == 1
