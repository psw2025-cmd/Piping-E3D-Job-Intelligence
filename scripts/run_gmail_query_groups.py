from __future__ import annotations

import argparse
import sys
from pathlib import Path

from job_intelligence.cli import _verify_database
from job_intelligence.coverage_registry import load_gmail_query_groups
from job_intelligence.coverage_workbook import (
    append_coverage_sheets,
    verify_coverage_workbook,
)
from job_intelligence.excel_export import export_excel, verify_excel
from job_intelligence.gmail_alerts import authorize_gmail, import_gmail_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import all enabled Gmail job-alert query groups and verify one workbook."
    )
    parser.add_argument("--db", default="data/database/jobs.db")
    parser.add_argument("--credentials", default="private-config/gmail_credentials.json")
    parser.add_argument("--token", default="private-config/gmail_token.json")
    parser.add_argument("--evidence-dir", default="private-output/gmail-evidence")
    parser.add_argument("--workbook", default="data/exports/Piping_E3D_Jobs.xlsx")
    parser.add_argument("--config", default="config/gmail_query_groups.yaml")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--only", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    groups = load_gmail_query_groups(args.config)
    requested = set(args.only)
    if requested:
        known = {group["id"] for group in groups}
        unknown = sorted(requested - known)
        if unknown:
            print(f"FAIL: unknown Gmail query groups: {', '.join(unknown)}")
            return 2
        groups = [group for group in groups if group["id"] in requested]
    groups = [group for group in groups if group["enabled"]]
    if not groups:
        print("FAIL: no enabled Gmail query groups selected")
        return 2

    service = authorize_gmail(
        credentials_path=args.credentials,
        token_path=args.token,
    )
    totals = {
        "attempted": 0,
        "processed": 0,
        "duplicates": 0,
        "no_match": 0,
        "failed": 0,
        "jobs_created": 0,
        "jobs_updated": 0,
    }
    for group in groups:
        summary = import_gmail_service(
            service,
            args.db,
            evidence_root=Path(args.evidence_dir) / group["id"],
            query=group["query"],
            max_messages=group["max_messages"],
        )
        for key in totals:
            totals[key] += int(getattr(summary, key))
        print(
            f"GROUP: {group['id']} | attempted={summary.attempted} "
            f"processed={summary.processed} duplicates={summary.duplicates} "
            f"no_match={summary.no_match} failed={summary.failed} "
            f"created={summary.jobs_created} updated={summary.jobs_updated}"
        )
        for result in summary.results:
            if result.status == "failed":
                print(
                    f"FAIL: group={group['id']} message={result.message_id} | "
                    f"{result.error_message}"
                )

    workbook = export_excel(args.db, args.workbook)
    append_coverage_sheets(args.db, workbook, config_dir=args.config_dir)
    errors = (
        _verify_database(args.db)
        + verify_excel(workbook)
        + verify_coverage_workbook(workbook)
    )
    if errors:
        print("FAIL: " + " | ".join(errors))
        return 2
    print(
        "PASS: grouped Gmail alerts imported and worldwide workbook verified | "
        + " ".join(f"{key}={value}" for key, value in totals.items())
    )
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
