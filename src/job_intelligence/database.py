from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .deduplicate import build_job_key
from .models import JobRecord, utc_now_iso

JOB_COLUMNS = (
    "job_key",
    "title",
    "company",
    "location",
    "description",
    "apply_url",
    "source_url",
    "source_name",
    "published_at",
    "found_at",
    "last_seen_at",
    "job_type",
    "salary_text",
    "experience_text",
    "skills_text",
    "recruiter_name",
    "recruiter_email",
    "contact_confidence",
    "match_score",
    "match_reasons",
    "gaps",
    "priority",
    "application_status",
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_database(db_path: str | Path) -> None:
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
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

            CREATE TABLE IF NOT EXISTS source_health (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                last_attempt_at TEXT NOT NULL,
                last_success_at TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                records_found INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                sources_attempted INTEGER NOT NULL DEFAULT 0,
                sources_passed INTEGER NOT NULL DEFAULT 0,
                sources_failed INTEGER NOT NULL DEFAULT 0,
                jobs_collected INTEGER NOT NULL DEFAULT 0,
                new_jobs INTEGER NOT NULL DEFAULT 0,
                export_status TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT ''
            );
            """
        )


def upsert_job(db_path: str | Path, job: JobRecord) -> bool:
    init_database(db_path)
    if not job.title.strip() or not job.company.strip():
        raise ValueError("title and company are required")

    job.job_key = job.job_key or build_job_key(job)
    values = job.to_dict()
    columns = ", ".join(JOB_COLUMNS)
    placeholders = ", ".join(f":{column}" for column in JOB_COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in JOB_COLUMNS
        if column not in {"job_key", "found_at"}
    )

    with connect(db_path) as connection:
        existed = connection.execute(
            "SELECT 1 FROM jobs WHERE job_key = ?", (job.job_key,)
        ).fetchone()
        connection.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(job_key) DO UPDATE SET {updates}",
            values,
        )
    return existed is None


def upsert_jobs(db_path: str | Path, jobs: Iterable[JobRecord]) -> tuple[int, int]:
    new_count = 0
    updated_count = 0
    for job in jobs:
        if upsert_job(db_path, job):
            new_count += 1
        else:
            updated_count += 1
    return new_count, updated_count


def fetch_jobs(db_path: str | Path) -> list[dict[str, object]]:
    init_database(db_path)
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM jobs ORDER BY found_at DESC, company, title"
        ).fetchall()
    return [dict(row) for row in rows]


def record_source_health(
    db_path: str | Path,
    source_id: str,
    source_name: str,
    status: str,
    records_found: int = 0,
    error_message: str = "",
) -> None:
    init_database(db_path)
    now = utc_now_iso()
    success_at = now if status == "pass" else ""
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO source_health (
                source_id, source_name, last_attempt_at, last_success_at,
                status, records_found, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_name=excluded.source_name,
                last_attempt_at=excluded.last_attempt_at,
                last_success_at=CASE
                    WHEN excluded.status='pass' THEN excluded.last_success_at
                    ELSE source_health.last_success_at
                END,
                status=excluded.status,
                records_found=excluded.records_found,
                error_message=excluded.error_message
            """,
            (
                source_id,
                source_name,
                now,
                success_at,
                status,
                records_found,
                error_message[:1000],
            ),
        )
