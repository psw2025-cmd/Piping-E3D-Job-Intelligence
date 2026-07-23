from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import private_import as _impl
from .database import connect

_ORIGINAL_IMPORT_PRIVATE_FILE = _impl.import_private_file
_ORIGINAL_IMPORT_PRIVATE_FOLDER = _impl.import_private_folder


def _lexically_within(path: Path, parent: Path) -> bool:
    try:
        path.absolute().relative_to(parent.absolute())
        return True
    except ValueError:
        return False


def _remove_managed_file(path: Path, evidence_root: Path) -> None:
    if not _lexically_within(path, evidence_root):
        return
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)


def _stored_evidence_is_valid(path: Path, digest: str) -> bool:
    try:
        return path.is_file() and not path.is_symlink() and _impl._sha256_file(path) == digest
    except OSError:
        return False


def import_private_file(
    db_path: str | Path,
    input_path: str | Path,
    evidence_root: str | Path,
    *,
    title: str = "",
    company: str = "",
    location: str = "",
    apply_url: str = "",
    ocr: bool = False,
    tesseract_cmd: str | None = None,
    max_bytes: int = 25_000_000,
) -> _impl.PrivateImportResult:
    """Repair duplicate evidence and clean orphan copies around the core importer."""
    unresolved_source = Path(input_path).expanduser()
    _impl._validate_source_file(unresolved_source, max_bytes)
    source = unresolved_source.resolve(strict=True)
    digest = _impl._sha256_file(source)
    evidence_folder = Path(evidence_root)
    _impl.init_private_import_tables(db_path)

    with connect(db_path) as connection:
        existing = connection.execute(
            """
            SELECT imports.stored_path, imports.status,
                   CASE WHEN jobs.job_key IS NULL THEN 0 ELSE 1 END AS job_exists
            FROM private_imports AS imports
            LEFT JOIN jobs ON jobs.job_key = imports.job_key
            WHERE imports.sha256=?
            """,
            (digest,),
        ).fetchone()

    if existing and existing["status"] == "complete":
        stored_path = Path(str(existing["stored_path"]))
        if not _stored_evidence_is_valid(stored_path, digest):
            with connect(db_path) as connection:
                connection.execute(
                    "DELETE FROM private_imports WHERE sha256=? AND status='complete'",
                    (digest,),
                )
            _remove_managed_file(stored_path, evidence_folder)
        elif existing["job_exists"]:
            return _ORIGINAL_IMPORT_PRIVATE_FILE(
                db_path,
                source,
                evidence_folder,
                title=title,
                company=company,
                location=location,
                apply_url=apply_url,
                ocr=ocr,
                tesseract_cmd=tesseract_cmd,
                max_bytes=max_bytes,
            )

    expected_path = (
        evidence_folder / digest[:2] / f"{digest}{source.suffix.lower()}"
    )
    temporary_path = expected_path.with_suffix(expected_path.suffix + ".tmp")
    try:
        return _ORIGINAL_IMPORT_PRIVATE_FILE(
            db_path,
            source,
            evidence_folder,
            title=title,
            company=company,
            location=location,
            apply_url=apply_url,
            ocr=ocr,
            tesseract_cmd=tesseract_cmd,
            max_bytes=max_bytes,
        )
    except Exception:
        with connect(db_path) as connection:
            referenced = connection.execute(
                "SELECT 1 FROM private_imports "
                "WHERE sha256=? OR stored_path=? LIMIT 1",
                (digest, str(expected_path)),
            ).fetchone()
        if not referenced:
            _remove_managed_file(expected_path, evidence_folder)
            _remove_managed_file(temporary_path, evidence_folder)
        raise


def _candidate_files(
    folder: Path,
    recursive: bool,
    excluded_root: Path,
) -> Iterable[Path]:
    iterator = folder.rglob("*") if recursive else folder.glob("*")
    for path in sorted(iterator):
        if _lexically_within(path, excluded_root):
            continue
        if path.is_symlink():
            if path.suffix.lower() in _impl.SUPPORTED_EXTENSIONS:
                yield path
            continue
        if path.is_file() and path.suffix.lower() in _impl.SUPPORTED_EXTENSIONS:
            yield path


def import_private_folder(
    db_path: str | Path,
    folder: str | Path,
    evidence_root: str | Path,
    *,
    recursive: bool = False,
    ocr: bool = False,
    tesseract_cmd: str | None = None,
    max_files: int = 500,
    max_bytes: int = 25_000_000,
) -> _impl.FolderImportSummary:
    unresolved_folder = Path(folder).expanduser()
    if unresolved_folder.is_symlink():
        raise ValueError(f"symbolic-link folders are not allowed: {unresolved_folder}")
    return _ORIGINAL_IMPORT_PRIVATE_FOLDER(
        db_path,
        unresolved_folder,
        evidence_root,
        recursive=recursive,
        ocr=ocr,
        tesseract_cmd=tesseract_cmd,
        max_files=max_files,
        max_bytes=max_bytes,
    )


_impl.import_private_file = import_private_file
_impl._candidate_files = _candidate_files
_impl.import_private_folder = import_private_folder
_impl._POSTMERGE_RECOVERY_APPLIED = True
