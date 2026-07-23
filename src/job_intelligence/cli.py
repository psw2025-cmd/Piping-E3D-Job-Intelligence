from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from .collection_runner import collect_sources
from .database import connect, upsert_job
from .excel_export import export_excel, verify_excel
from .gmail_alerts import (
    DEFAULT_GMAIL_QUERY,
    authorize_gmail,
    import_gmail_service,
    init_gmail_tables,
    verify_gmail_imports,
)
from .manual_import import create_manual_job
from .private_import import (
    import_private_file,
    import_private_folder,
    init_private_import_tables,
    verify_private_imports,
)
from .proof import set_run_export_status
from .source_config import load_source_config

DEFAULT_DB = os.getenv("JOB_INTEL_DB_PATH", "data/database/jobs.db")
DEFAULT_EXPORT = os.getenv(
    "JOB_INTEL_EXPORT_PATH",
    "data/exports/Piping_E3D_Jobs.xlsx",
)
DEFAULT_SOURCES = os.getenv("JOB_INTEL_SOURCES_PATH", "config/sources.yaml")
DEFAULT_EVIDENCE = os.getenv("JOB_INTEL_EVIDENCE_PATH", "data/raw")
DEFAULT_PRIVATE_EVIDENCE = os.getenv(
    "JOB_INTEL_PRIVATE_EVIDENCE_PATH",
    "private-output/evidence",
)
DEFAULT_GMAIL_EVIDENCE = os.getenv(
    "JOB_INTEL_GMAIL_EVIDENCE_PATH",
    "private-output/gmail-evidence",
)
DEFAULT_GMAIL_CREDENTIALS = os.getenv(
    "JOB_INTEL_GMAIL_CREDENTIALS",
    "private-config/gmail_credentials.json",
)
DEFAULT_GMAIL_TOKEN = os.getenv(
    "JOB_INTEL_GMAIL_TOKEN",
    "private-config/gmail_token.json",
)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _verify_database(db_path: str) -> list[str]:
    errors: list[str] = []
    init_gmail_tables(db_path)
    with connect(db_path) as connection:
        duplicate_count = connection.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT job_key FROM jobs GROUP BY job_key HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        if duplicate_count:
            errors.append(f"Duplicate job keys found: {duplicate_count}")
        missing_required = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE trim(title)='' OR trim(company)=''"
        ).fetchone()[0]
        if missing_required:
            errors.append(f"Jobs missing title/company: {missing_required}")
        orphan_aliases = connection.execute(
            """
            SELECT COUNT(*)
            FROM job_identity_aliases AS aliases
            LEFT JOIN jobs ON jobs.job_key = aliases.job_key
            WHERE jobs.job_key IS NULL
            """
        ).fetchone()[0]
        if orphan_aliases:
            errors.append(f"Orphan identity aliases found: {orphan_aliases}")
        evidence_rows = connection.execute(
            "SELECT file_path, sha256 FROM source_evidence"
        ).fetchall()

    for row in evidence_rows:
        evidence_path = Path(row["file_path"])
        if not evidence_path.exists():
            errors.append(f"Missing evidence file: {evidence_path}")
            continue
        digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            errors.append(f"Evidence hash mismatch: {evidence_path}")
    errors.extend(verify_private_imports(db_path))
    errors.extend(verify_gmail_imports(db_path))
    return errors


def _add_private_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence-dir", default=DEFAULT_PRIVATE_EVIDENCE)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--tesseract-cmd", default="")
    parser.add_argument("--max-bytes", type=int, default=25_000_000)
    parser.add_argument("--output", default=DEFAULT_EXPORT)
    parser.add_argument("--no-export", action="store_true")


def _add_gmail_auth_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--credentials", default=DEFAULT_GMAIL_CREDENTIALS)
    parser.add_argument("--token", default=DEFAULT_GMAIL_TOKEN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Piping/E3D job intelligence CLI")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or migrate the local SQLite schema")

    import_parser = subparsers.add_parser(
        "import-text",
        help="Import user-supplied vacancy text",
    )
    import_parser.add_argument("--title", required=True)
    import_parser.add_argument("--company", required=True)
    import_parser.add_argument("--file", required=True, help="UTF-8 text evidence file")
    import_parser.add_argument("--location", default="")
    import_parser.add_argument("--apply-url", default="")
    import_parser.add_argument("--source-url", default="")
    import_parser.add_argument("--source-name", default="manual")
    import_parser.add_argument("--published-at", default="")

    file_parser = subparsers.add_parser(
        "import-file",
        help="Import a private PDF, Word, email, text, or image vacancy file",
    )
    file_parser.add_argument("--file", required=True)
    file_parser.add_argument("--title", default="")
    file_parser.add_argument("--company", default="")
    file_parser.add_argument("--location", default="")
    file_parser.add_argument("--apply-url", default="")
    _add_private_common_arguments(file_parser)

    folder_parser = subparsers.add_parser(
        "import-folder",
        help="Import supported private vacancy files from a folder",
    )
    folder_parser.add_argument("--folder", required=True)
    folder_parser.add_argument("--recursive", action="store_true")
    folder_parser.add_argument("--max-files", type=int, default=500)
    _add_private_common_arguments(folder_parser)

    gmail_auth_parser = subparsers.add_parser(
        "gmail-auth",
        help="Authorize read-only Gmail API access using a local desktop OAuth client",
    )
    _add_gmail_auth_arguments(gmail_auth_parser)

    gmail_import_parser = subparsers.add_parser(
        "gmail-import",
        help="Import user-authorized job-alert emails from Gmail",
    )
    _add_gmail_auth_arguments(gmail_import_parser)
    gmail_import_parser.add_argument("--query", default=DEFAULT_GMAIL_QUERY)
    gmail_import_parser.add_argument("--max-messages", type=int, default=200)
    gmail_import_parser.add_argument("--evidence-dir", default=DEFAULT_GMAIL_EVIDENCE)
    gmail_import_parser.add_argument("--output", default=DEFAULT_EXPORT)
    gmail_import_parser.add_argument("--no-export", action="store_true")

    validate_parser = subparsers.add_parser(
        "validate-sources",
        help="Validate the public-source configuration without collecting",
    )
    validate_parser.add_argument("--sources", default=DEFAULT_SOURCES)

    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect all enabled public sources and update Excel",
    )
    collect_parser.add_argument("--sources", default=DEFAULT_SOURCES)
    collect_parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE)
    collect_parser.add_argument("--output", default=DEFAULT_EXPORT)
    collect_parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only this source id; may be repeated",
    )
    collect_parser.add_argument("--no-export", action="store_true")

    export_parser = subparsers.add_parser("export", help="Generate the Excel tracker")
    export_parser.add_argument("--output", default=DEFAULT_EXPORT)

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify database, public/private evidence, Gmail imports, and Excel output",
    )
    verify_parser.add_argument("--output", default=DEFAULT_EXPORT)
    return parser


def _print_collection_summary(summary) -> None:
    print(
        "RUN: "
        f"{summary.run_id} | status={summary.status} | "
        f"sources={summary.sources_passed}/{summary.sources_attempted} passed | "
        f"jobs={summary.jobs_collected} | new={summary.new_jobs} | "
        f"updated={summary.updated_jobs}"
    )
    for result in summary.source_results:
        message = (
            f"SOURCE: {result.source_id} | {result.status} | "
            f"jobs={result.jobs_collected} | new={result.new_jobs} | "
            f"updated={result.updated_jobs}"
        )
        if result.error_message:
            message += f" | {result.error_message}"
        print(message)


def _export_after_import(db_path: str, output: str, disabled: bool) -> int:
    if disabled:
        return 0
    exported = export_excel(db_path, output)
    errors = verify_excel(exported)
    if errors:
        print("FAIL: " + " | ".join(errors))
        return 2
    print(f"PASS: Excel exported and verified at {exported}")
    return 0


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "init-db":
        init_gmail_tables(args.db)
        print(f"PASS: database initialized at {args.db}")
        return 0

    if args.command == "import-text":
        job = create_manual_job(
            title=args.title,
            company=args.company,
            text=_read_text(args.file),
            location=args.location,
            apply_url=args.apply_url,
            source_url=args.source_url,
            source_name=args.source_name,
            published_at=args.published_at,
        )
        created = upsert_job(args.db, job)
        action = "created" if created else "updated"
        print(
            f"PASS: {action} job {job.job_key[:12]} | "
            f"score={job.match_score} | priority={job.priority}"
        )
        return 0

    if args.command == "import-file":
        result = import_private_file(
            args.db,
            args.file,
            args.evidence_dir,
            title=args.title,
            company=args.company,
            location=args.location,
            apply_url=args.apply_url,
            ocr=args.ocr,
            tesseract_cmd=args.tesseract_cmd or None,
            max_bytes=args.max_bytes,
        )
        print(
            f"PASS: private import {result.status} | job={result.job_key[:12]} | "
            f"review_required={int(result.review_required)} | sha256={result.sha256}"
        )
        for warning in result.warnings:
            print(f"REVIEW: {warning}")
        return _export_after_import(args.db, args.output, args.no_export)

    if args.command == "import-folder":
        summary = import_private_folder(
            args.db,
            args.folder,
            args.evidence_dir,
            recursive=args.recursive,
            ocr=args.ocr,
            tesseract_cmd=args.tesseract_cmd or None,
            max_files=args.max_files,
            max_bytes=args.max_bytes,
        )
        print(
            "IMPORT: "
            f"attempted={summary.attempted} created={summary.created} "
            f"updated={summary.updated} duplicates={summary.duplicates} "
            f"failed={summary.failed} review_required={summary.review_required}"
        )
        for result in summary.results:
            if result.status == "failed":
                print(f"FAIL: {result.input_path} | {result.error_message}")
        export_code = _export_after_import(args.db, args.output, args.no_export)
        if export_code:
            return export_code
        return 1 if summary.failed else 0

    if args.command == "gmail-auth":
        authorize_gmail(
            credentials_path=args.credentials,
            token_path=args.token,
        )
        print(f"PASS: Gmail read-only authorization stored locally at {args.token}")
        return 0

    if args.command == "gmail-import":
        service = authorize_gmail(
            credentials_path=args.credentials,
            token_path=args.token,
        )
        summary = import_gmail_service(
            service,
            args.db,
            evidence_root=args.evidence_dir,
            query=args.query,
            max_messages=args.max_messages,
        )
        print(
            "GMAIL: "
            f"attempted={summary.attempted} processed={summary.processed} "
            f"duplicates={summary.duplicates} no_match={summary.no_match} "
            f"failed={summary.failed} created={summary.jobs_created} "
            f"updated={summary.jobs_updated}"
        )
        for result in summary.results:
            if result.status == "failed":
                print(f"FAIL: Gmail {result.message_id} | {result.error_message}")
        export_code = _export_after_import(args.db, args.output, args.no_export)
        if export_code:
            return export_code
        return 1 if summary.failed else 0

    if args.command == "validate-sources":
        config = load_source_config(args.sources)
        enabled = sum(source.enabled for source in config.sources)
        print(
            f"PASS: {len(config.sources)} sources valid; "
            f"{enabled} enabled; policy restrictions valid"
        )
        return 0

    if args.command == "collect":
        summary = collect_sources(
            args.db,
            args.sources,
            args.evidence_dir,
            only_source_ids=set(args.only) if args.only else None,
        )
        _print_collection_summary(summary)
        if not args.no_export:
            try:
                output = export_excel(args.db, args.output)
                errors = verify_excel(output)
                if errors:
                    raise ValueError(" | ".join(errors))
                set_run_export_status(args.db, summary.run_id, "pass")
                print(f"PASS: Excel exported and verified at {output}")
            except Exception as exc:
                set_run_export_status(args.db, summary.run_id, "fail", str(exc))
                print(f"FAIL: Excel export failed: {type(exc).__name__}: {exc}")
                return 2
        if summary.status == "fail":
            return 2
        if summary.status == "partial":
            return 1
        return 0

    if args.command == "export":
        output = export_excel(args.db, args.output)
        errors = verify_excel(output)
        if errors:
            print("FAIL: " + " | ".join(errors))
            return 1
        print(f"PASS: Excel exported and verified at {output}")
        return 0

    if args.command == "verify":
        errors = _verify_database(args.db) + verify_excel(args.output)
        if errors:
            print("FAIL: " + " | ".join(errors))
            return 1
        print("PASS: database, evidence, private imports, Gmail imports, and Excel verified")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
