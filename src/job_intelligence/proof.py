from __future__ import annotations

from pathlib import Path

from .database import connect, init_database
from .models import utc_now_iso


def init_proof_tables(db_path: str | Path) -> None:
    init_database(db_path)
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_evidence (
                evidence_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                file_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT '',
                status_code INTEGER NOT NULL DEFAULT 0,
                size_bytes INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_source_evidence_run
                ON source_evidence(run_id, source_id);
            """
        )


def start_run(
    db_path: str | Path,
    run_id: str,
    *,
    started_at: str | None = None,
) -> None:
    init_proof_tables(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO runs (run_id, started_at, status)
            VALUES (?, ?, 'running')
            ON CONFLICT(run_id) DO UPDATE SET
                started_at=excluded.started_at,
                ended_at='',
                status='running',
                error_message=''
            """,
            (run_id, started_at or utc_now_iso()),
        )


def finish_run(
    db_path: str | Path,
    run_id: str,
    *,
    status: str,
    sources_attempted: int,
    sources_passed: int,
    sources_failed: int,
    jobs_collected: int,
    new_jobs: int,
    export_status: str = "",
    error_message: str = "",
) -> None:
    init_proof_tables(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE runs SET
                ended_at=?,
                status=?,
                sources_attempted=?,
                sources_passed=?,
                sources_failed=?,
                jobs_collected=?,
                new_jobs=?,
                export_status=?,
                error_message=?
            WHERE run_id=?
            """,
            (
                utc_now_iso(),
                status,
                sources_attempted,
                sources_passed,
                sources_failed,
                jobs_collected,
                new_jobs,
                export_status,
                error_message[:2000],
                run_id,
            ),
        )


def record_evidence(
    db_path: str | Path,
    *,
    evidence_id: str,
    run_id: str,
    source_id: str,
    source_url: str,
    file_path: str,
    sha256: str,
    content_type: str,
    status_code: int,
    size_bytes: int,
    fetched_at: str | None = None,
) -> None:
    init_proof_tables(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO source_evidence (
                evidence_id, run_id, source_id, fetched_at, source_url, file_path,
                sha256, content_type, status_code, size_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                run_id,
                source_id,
                fetched_at or utc_now_iso(),
                source_url,
                file_path,
                sha256,
                content_type,
                status_code,
                size_bytes,
            ),
        )


def set_run_export_status(
    db_path: str | Path,
    run_id: str,
    status: str,
    error_message: str = "",
) -> None:
    init_proof_tables(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE runs SET
                export_status=?,
                error_message=CASE
                    WHEN ? = '' THEN error_message
                    WHEN error_message = '' THEN ?
                    ELSE error_message || ' | ' || ?
                END
            WHERE run_id=?
            """,
            (
                status,
                error_message,
                error_message[:2000],
                error_message[:2000],
                run_id,
            ),
        )
