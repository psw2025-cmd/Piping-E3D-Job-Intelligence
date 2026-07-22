from __future__ import annotations

import argparse
import os
from pathlib import Path

from .database import connect, init_database, upsert_job
from .excel_export import export_excel, verify_excel
from .manual_import import create_manual_job

DEFAULT_DB = os.getenv("JOB_INTEL_DB_PATH", "data/database/jobs.db")
DEFAULT_EXPORT = os.getenv(
    "JOB_INTEL_EXPORT_PATH", "data/exports/Piping_E3D_Jobs.xlsx"
)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _verify_database(db_path: str) -> list[str]:
    errors: list[str] = []
    init_database(db_path)
    with connect(db_path) as connection:
        duplicate_count = connection.execute(
            "SELECT COUNT(*) FROM (SELECT job_key FROM jobs GROUP BY job_key HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        if duplicate_count:
            errors.append(f"Duplicate job keys found: {duplicate_count}")
        missing_required = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE trim(title)='' OR trim(company)=''"
        ).fetchone()[0]
        if missing_required:
            errors.append(f"Jobs missing title/company: {missing_required}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Piping/E3D job intelligence CLI")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the local SQLite schema")

    import_parser = subparsers.add_parser("import-text", help="Import user-supplied vacancy text")
    import_parser.add_argument("--title", required=True)
    import_parser.add_argument("--company", required=True)
    import_parser.add_argument("--file", required=True, help="UTF-8 text evidence file")
    import_parser.add_argument("--location", default="")
    import_parser.add_argument("--apply-url", default="")
    import_parser.add_argument("--source-url", default="")
    import_parser.add_argument("--source-name", default="manual")
    import_parser.add_argument("--published-at", default="")

    export_parser = subparsers.add_parser("export", help="Generate the Excel tracker")
    export_parser.add_argument("--output", default=DEFAULT_EXPORT)

    verify_parser = subparsers.add_parser("verify", help="Verify database and Excel output")
    verify_parser.add_argument("--output", default=DEFAULT_EXPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "init-db":
        init_database(args.db)
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
            f"PASS: {action} job {job.job_key[:12]} | score={job.match_score} | priority={job.priority}"
        )
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
        print("PASS: database and Excel verification completed")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
