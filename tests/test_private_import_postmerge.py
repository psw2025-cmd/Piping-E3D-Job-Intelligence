from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

import job_intelligence.private_import as private_import_module
from job_intelligence.database import connect as database_connect
from job_intelligence.private_import import (
    import_private_file,
    import_private_folder,
    verify_private_imports,
)


def _vacancy_text() -> str:
    return (
        "Job Title: Senior Piping Engineer\n"
        "Company: Example EPC\n"
        "Location: Mumbai\n"
        "AVEVA E3D refinery piping layout role."
    )


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_duplicate_reimport_repairs_evidence(tmp_path: Path, damage: str) -> None:
    source = tmp_path / "vacancy.txt"
    source.write_text(_vacancy_text(), encoding="utf-8")
    db_path = tmp_path / "jobs.db"
    evidence = tmp_path / "evidence"

    first = import_private_file(db_path, source, evidence)
    stored = Path(first.stored_path)
    if damage == "missing":
        stored.unlink()
    else:
        stored.write_text("corrupted evidence", encoding="utf-8")

    recovered = import_private_file(db_path, source, evidence)

    assert recovered.status == "updated"
    repaired = Path(recovered.stored_path)
    assert repaired.exists()
    assert hashlib.sha256(repaired.read_bytes()).hexdigest() == recovered.sha256
    assert verify_private_imports(db_path) == []
    with database_connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM private_imports").fetchone()[0] == 1


def test_folder_import_reports_supported_symlink_as_failure(tmp_path: Path) -> None:
    folder = tmp_path / "incoming"
    folder.mkdir()
    target = folder / "role.txt"
    target.write_text(_vacancy_text(), encoding="utf-8")
    link = folder / "linked-role.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")

    summary = import_private_folder(
        tmp_path / "jobs.db",
        folder,
        tmp_path / "evidence",
    )

    assert summary.attempted == 2
    assert summary.created == 1
    assert summary.failed == 1
    failed = [result for result in summary.results if result.status == "failed"]
    assert len(failed) == 1
    assert "symbolic-link" in failed[0].error_message


class _FailingStagedInsertConnection:
    def __init__(self, db_path: str | Path) -> None:
        self._connection = database_connect(db_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()

    def execute(self, sql: str, parameters=()):
        if "INSERT INTO private_imports" in sql:
            raise sqlite3.IntegrityError("simulated staged insert failure")
        return self._connection.execute(sql, parameters)

    def executescript(self, script: str):
        return self._connection.executescript(script)


def test_staged_insert_failure_removes_orphan_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "vacancy.txt"
    source.write_text(_vacancy_text(), encoding="utf-8")
    db_path = tmp_path / "jobs.db"
    evidence = tmp_path / "evidence"

    monkeypatch.setattr(
        private_import_module,
        "connect",
        lambda path: _FailingStagedInsertConnection(path),
    )

    with pytest.raises(sqlite3.IntegrityError, match="staged insert failure"):
        import_private_file(db_path, source, evidence)

    with database_connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM private_imports").fetchone()[0] == 0
    assert list(evidence.rglob("*.*")) == []
