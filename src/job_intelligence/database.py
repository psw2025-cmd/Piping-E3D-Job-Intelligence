from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .deduplicate import build_identity_fingerprint, build_job_key, canonicalize_url
from .models import JobRecord, utc_now_iso

JOB_COLUMNS = (
    "job_key",
    "identity_fingerprint",
    "canonical_url",
    "title",
    "normalized_role",
    "company",
    "location",
    "city",
    "country",
    "description",
    "apply_url",
    "source_url",
    "source_name",
    "published_at",
    "closing_at",
    "found_at",
    "last_seen_at",
    "job_type",
    "employment_type",
    "salary_text",
    "experience_text",
    "skills_text",
    "software_text",
    "sector",
    "agency_name",
    "recruiter_name",
    "recruiter_email",
    "contact_source_url",
    "contact_confidence",
    "match_score",
    "match_reasons",
    "gaps",
    "priority",
    "duplicate_status",
    "application_status",
)

_STRING_REFRESH_COLUMNS = (
    "title",
    "company",
    "location",
    "description",
    "apply_url",
    "source_url",
    "source_name",
    "published_at",
    "job_type",
    "salary_text",
    "experience_text",
    "skills_text",
    "agency_name",
)

_PROFILE_REFRESH_COLUMNS = (
    "normalized_role",
    "city",
    "country",
    "closing_at",
    "employment_type",
    "software_text",
    "sector",
)

_PROFILE_COLUMN_DEFINITIONS = {
    "normalized_role": "TEXT NOT NULL DEFAULT ''",
    "city": "TEXT NOT NULL DEFAULT ''",
    "country": "TEXT NOT NULL DEFAULT ''",
    "closing_at": "TEXT NOT NULL DEFAULT ''",
    "employment_type": "TEXT NOT NULL DEFAULT ''",
    "software_text": "TEXT NOT NULL DEFAULT ''",
    "sector": "TEXT NOT NULL DEFAULT ''",
    "agency_name": "TEXT NOT NULL DEFAULT ''",
    "contact_source_url": "TEXT NOT NULL DEFAULT ''",
    "duplicate_status": "TEXT NOT NULL DEFAULT 'unique'",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _register_identity_aliases(
    connection: sqlite3.Connection,
    job_key: str,
    identity_fingerprint: str,
    canonical_url: str,
    first_seen_at: str | None = None,
) -> None:
    timestamp = first_seen_at or utc_now_iso()
    aliases = (
        ("fingerprint", identity_fingerprint),
        ("canonical_url", canonical_url),
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO job_identity_aliases (
            alias_type, alias_value, job_key, first_seen_at
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (alias_type, alias_value, job_key, timestamp)
            for alias_type, alias_value in aliases
            if alias_value
        ],
    )


def _ensure_job_columns(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "identity_fingerprint" not in columns:
        connection.execute(
            "ALTER TABLE jobs ADD COLUMN identity_fingerprint TEXT NOT NULL DEFAULT ''"
        )
    if "canonical_url" not in columns:
        connection.execute(
            "ALTER TABLE jobs ADD COLUMN canonical_url TEXT NOT NULL DEFAULT ''"
        )
    for column, definition in _PROFILE_COLUMN_DEFINITIONS.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")

    rows = connection.execute(
        "SELECT * FROM jobs WHERE identity_fingerprint = '' OR canonical_url = ''"
    ).fetchall()
    for row in rows:
        job = JobRecord(
            title=row["title"],
            company=row["company"],
            location=row["location"],
            description=row["description"],
            apply_url=row["apply_url"],
            source_url=row["source_url"],
        )
        connection.execute(
            "UPDATE jobs SET identity_fingerprint = ?, canonical_url = ? "
            "WHERE job_key = ?",
            (
                build_identity_fingerprint(job),
                canonicalize_url(job.apply_url or job.source_url),
                row["job_key"],
            ),
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_identity_fingerprint "
        "ON jobs(identity_fingerprint)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_canonical_url ON jobs(canonical_url)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS job_identity_aliases (
            alias_type TEXT NOT NULL,
            alias_value TEXT NOT NULL,
            job_key TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            PRIMARY KEY (alias_type, alias_value, job_key)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_identity_alias_lookup "
        "ON job_identity_aliases(alias_type, alias_value)"
    )
    for row in connection.execute(
        "SELECT job_key, identity_fingerprint, canonical_url, found_at FROM jobs"
    ):
        _register_identity_aliases(
            connection,
            str(row["job_key"]),
            str(row["identity_fingerprint"]),
            str(row["canonical_url"]),
            str(row["found_at"]),
        )


def init_database(db_path: str | Path) -> None:
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_key TEXT PRIMARY KEY,
                identity_fingerprint TEXT NOT NULL DEFAULT '',
                canonical_url TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                normalized_role TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                apply_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                closing_at TEXT NOT NULL DEFAULT '',
                found_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                job_type TEXT NOT NULL DEFAULT '',
                employment_type TEXT NOT NULL DEFAULT '',
                salary_text TEXT NOT NULL DEFAULT '',
                experience_text TEXT NOT NULL DEFAULT '',
                skills_text TEXT NOT NULL DEFAULT '',
                software_text TEXT NOT NULL DEFAULT '',
                sector TEXT NOT NULL DEFAULT '',
                agency_name TEXT NOT NULL DEFAULT '',
                recruiter_name TEXT NOT NULL DEFAULT '',
                recruiter_email TEXT NOT NULL DEFAULT '',
                contact_source_url TEXT NOT NULL DEFAULT '',
                contact_confidence TEXT NOT NULL DEFAULT '',
                match_score INTEGER NOT NULL DEFAULT 0,
                match_reasons TEXT NOT NULL DEFAULT '',
                gaps TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'normal',
                duplicate_status TEXT NOT NULL DEFAULT 'unique',
                application_status TEXT NOT NULL DEFAULT 'new'
            );

            CREATE TABLE IF NOT EXISTS job_identity_aliases (
                alias_type TEXT NOT NULL,
                alias_value TEXT NOT NULL,
                job_key TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                PRIMARY KEY (alias_type, alias_value, job_key)
            );

            CREATE INDEX IF NOT EXISTS idx_identity_alias_lookup
                ON job_identity_aliases(alias_type, alias_value);

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
        _ensure_job_columns(connection)


def _requested_key_urls_compatible(existing_url: str, incoming_url: str) -> bool:
    """Allow an explicit stable key to enrich a record that previously lacked a URL."""
    return not existing_url or not incoming_url or existing_url == incoming_url


def _alias_urls_compatible(existing_url: str, incoming_url: str) -> bool:
    """Do not use a field alias to attach a new URL to a URL-less record."""
    return not incoming_url or existing_url == incoming_url


def _find_alias_candidates(
    connection: sqlite3.Connection,
    alias_type: str,
    alias_value: str,
    incoming_url: str,
) -> list[sqlite3.Row]:
    if not alias_value:
        return []
    rows = connection.execute(
        """
        SELECT jobs.job_key, jobs.canonical_url
        FROM job_identity_aliases AS aliases
        JOIN jobs ON jobs.job_key = aliases.job_key
        WHERE aliases.alias_type = ? AND aliases.alias_value = ?
        ORDER BY jobs.found_at
        """,
        (alias_type, alias_value),
    ).fetchall()
    return [
        row
        for row in rows
        if _alias_urls_compatible(str(row["canonical_url"]), incoming_url)
    ]


def _find_existing_job_key(
    connection: sqlite3.Connection,
    requested_key: str,
    identity_fingerprint: str,
    canonical_url: str,
) -> str | None:
    if requested_key:
        row = connection.execute(
            "SELECT job_key, canonical_url FROM jobs WHERE job_key = ?",
            (requested_key,),
        ).fetchone()
        if row and _requested_key_urls_compatible(str(row["canonical_url"]), canonical_url):
            return str(row["job_key"])

    canonical_matches = _find_alias_candidates(
        connection,
        "canonical_url",
        canonical_url,
        canonical_url,
    )
    if len(canonical_matches) == 1:
        return str(canonical_matches[0]["job_key"])

    fingerprint_matches = _find_alias_candidates(
        connection,
        "fingerprint",
        identity_fingerprint,
        canonical_url,
    )
    if len(fingerprint_matches) == 1:
        return str(fingerprint_matches[0]["job_key"])
    return None


def _allocate_job_key(
    connection: sqlite3.Connection,
    job: JobRecord,
    canonical_url: str,
) -> str:
    base_key = job.job_key or build_job_key(job)
    row = connection.execute(
        "SELECT canonical_url FROM jobs WHERE job_key = ?",
        (base_key,),
    ).fetchone()
    if not row or str(row["canonical_url"]) == canonical_url:
        return base_key

    disambiguator = canonical_url or (
        f"{job.source_name}|{job.apply_url}|{job.source_url}"
    )
    raw = f"{base_key}|variant|{disambiguator}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _job_values(
    job: JobRecord,
    identity_fingerprint: str,
    canonical_url: str,
) -> dict[str, object]:
    values = job.to_dict()
    values["identity_fingerprint"] = identity_fingerprint
    values["canonical_url"] = canonical_url
    return values


def _upsert_job(connection: sqlite3.Connection, job: JobRecord) -> bool:
    if not job.title.strip() or not job.company.strip():
        raise ValueError("title and company are required")

    identity_fingerprint = build_identity_fingerprint(job)
    canonical_url = canonicalize_url(job.apply_url or job.source_url)
    columns = ", ".join(JOB_COLUMNS)
    placeholders = ", ".join(f":{column}" for column in JOB_COLUMNS)
    string_updates = ",\n                ".join(
        f"{column}=COALESCE(NULLIF(excluded.{column}, ''), jobs.{column})"
        for column in _STRING_REFRESH_COLUMNS
    )
    profile_updates = ",\n                ".join(
        f"{column}=CASE "
        "WHEN excluded.match_reasons <> '' OR excluded.gaps <> '' "
        f"THEN excluded.{column} "
        f"ELSE COALESCE(NULLIF(excluded.{column}, ''), jobs.{column}) END"
        for column in _PROFILE_REFRESH_COLUMNS
    )

    existing_key = _find_existing_job_key(
        connection,
        job.job_key,
        identity_fingerprint,
        canonical_url,
    )
    job.job_key = existing_key or _allocate_job_key(
        connection,
        job,
        canonical_url,
    )
    existed = existing_key is not None
    if not existed:
        existed = (
            connection.execute(
                "SELECT 1 FROM jobs WHERE job_key = ?",
                (job.job_key,),
            ).fetchone()
            is not None
        )
    values = _job_values(job, identity_fingerprint, canonical_url)
    connection.execute(
        f"""
        INSERT INTO jobs ({columns}) VALUES ({placeholders})
        ON CONFLICT(job_key) DO UPDATE SET
            identity_fingerprint=excluded.identity_fingerprint,
            canonical_url=COALESCE(
                NULLIF(excluded.canonical_url, ''), jobs.canonical_url
            ),
            {string_updates},
            {profile_updates},
            last_seen_at=excluded.last_seen_at,
            recruiter_name=COALESCE(
                NULLIF(excluded.recruiter_name, ''), jobs.recruiter_name
            ),
            recruiter_email=COALESCE(
                NULLIF(excluded.recruiter_email, ''), jobs.recruiter_email
            ),
            contact_source_url=COALESCE(
                NULLIF(excluded.contact_source_url, ''), jobs.contact_source_url
            ),
            contact_confidence=COALESCE(
                NULLIF(excluded.contact_confidence, ''), jobs.contact_confidence
            ),
            duplicate_status=CASE
                WHEN excluded.duplicate_status NOT IN ('', 'unique')
                THEN excluded.duplicate_status ELSE jobs.duplicate_status END,
            match_score=CASE
                WHEN excluded.match_reasons <> '' OR excluded.gaps <> ''
                THEN excluded.match_score ELSE jobs.match_score END,
            match_reasons=CASE
                WHEN excluded.match_reasons <> '' OR excluded.gaps <> ''
                THEN excluded.match_reasons ELSE jobs.match_reasons END,
            gaps=CASE
                WHEN excluded.match_reasons <> '' OR excluded.gaps <> ''
                THEN excluded.gaps ELSE jobs.gaps END,
            priority=CASE
                WHEN excluded.match_reasons <> '' OR excluded.gaps <> ''
                THEN excluded.priority ELSE jobs.priority END,
            application_status=jobs.application_status
        """,
        values,
    )
    _register_identity_aliases(
        connection,
        job.job_key,
        identity_fingerprint,
        canonical_url,
        job.found_at,
    )
    return not existed


def upsert_job(db_path: str | Path, job: JobRecord) -> bool:
    init_database(db_path)
    with connect(db_path) as connection:
        return _upsert_job(connection, job)


def upsert_jobs(db_path: str | Path, jobs: Iterable[JobRecord]) -> tuple[int, int]:
    init_database(db_path)
    new_count = 0
    updated_count = 0
    with connect(db_path) as connection:
        for job in jobs:
            if _upsert_job(connection, job):
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
    successful = status in {"pass", "pass_with_warnings"}
    success_at = now if successful else ""
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
                    WHEN excluded.status IN (
                        'pass', 'pass_with_warnings'
                    ) THEN excluded.last_success_at
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
