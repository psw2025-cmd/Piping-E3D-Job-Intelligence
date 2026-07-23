from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import job_intelligence.private_import as private_import_module
from job_intelligence.database import connect, fetch_jobs, upsert_job
from job_intelligence.manual_import import create_manual_job
from job_intelligence.private_import import (
    import_private_file,
    init_private_import_tables,
)
from job_intelligence.models import utc_now_iso


def _vacancy_text() -> str:
    return (
        "Job Title: Senior Piping Engineer\n"
        "Company: Example EPC\n"
        "Location: Mumbai\n"
        "AVEVA E3D refinery piping layout role."
    )


def test_symlink_is_rejected_before_resolution(tmp_path: Path) -> None:
    source = tmp_path / "vacancy.txt"
    source.write_text(_vacancy_text(), encoding="utf-8")
    link = tmp_path / "linked-vacancy.txt"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")

    with pytest.raises(ValueError, match="symbolic-link"):
        import_private_file(
            tmp_path / "jobs.db",
            link,
            tmp_path / "evidence",
        )


def test_staged_import_is_recovered_automatically(tmp_path: Path) -> None:
    source = tmp_path / "vacancy.txt"
    source.write_text(_vacancy_text(), encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    db_path = tmp_path / "jobs.db"
    init_private_import_tables(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO private_imports (
                import_id, sha256, original_path, original_name, stored_path,
                mime_type, size_bytes, extraction_method, extracted_chars,
                review_required, warnings, job_key, status, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'staged', ?)
            """,
            (
                "interrupted-import",
                digest,
                str(source),
                source.name,
                str(tmp_path / "missing-evidence.txt"),
                "text/plain",
                source.stat().st_size,
                "text-decoder",
                len(_vacancy_text()),
                1,
                "interrupted test",
                utc_now_iso(),
            ),
        )

    result = import_private_file(db_path, source, tmp_path / "evidence")

    assert result.status == "created"
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT import_id, status FROM private_imports WHERE sha256=?",
            (digest,),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["import_id"] != "interrupted-import"
    assert rows[0]["status"] == "complete"


def test_review_required_updates_existing_new_job(tmp_path: Path) -> None:
    source = tmp_path / "vacancy.txt"
    text = _vacancy_text()
    source.write_text(text, encoding="utf-8")
    db_path = tmp_path / "jobs.db"
    existing = create_manual_job(
        title="Senior Piping Engineer",
        company="Example EPC",
        text=text,
        location="Mumbai",
    )
    assert upsert_job(db_path, existing) is True

    result = import_private_file(db_path, source, tmp_path / "evidence")

    assert result.status == "updated"
    assert result.review_required is True
    jobs = fetch_jobs(db_path)
    assert len(jobs) == 1
    assert jobs[0]["application_status"] == "review_required"


def test_private_import_job_and_ledger_finalize_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "vacancy.txt"
    source.write_text(_vacancy_text(), encoding="utf-8")
    db_path = tmp_path / "jobs.db"
    original_upsert = private_import_module._upsert_job

    def write_then_fail(connection, job):
        original_upsert(connection, job)
        raise RuntimeError("simulated failure after job write")

    monkeypatch.setattr(private_import_module, "_upsert_job", write_then_fail)

    with pytest.raises(RuntimeError, match="simulated failure"):
        import_private_file(db_path, source, tmp_path / "evidence")

    assert fetch_jobs(db_path) == []
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM private_imports").fetchone()[0] == 0
    assert list((tmp_path / "evidence").rglob("*.*")) == []
