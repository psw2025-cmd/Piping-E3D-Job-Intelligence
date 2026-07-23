from __future__ import annotations

import argparse

from job_intelligence.excel_export import export_excel, verify_excel
from job_intelligence.gmail_alerts import DEFAULT_GMAIL_QUERY, import_gmail_alerts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import authorized Gmail job alerts into the local job ledger."
    )
    parser.add_argument("--db", default="data/database/jobs.db")
    parser.add_argument("--credentials", default="private-input/gmail_credentials.json")
    parser.add_argument("--token", default="private-output/gmail/token.json")
    parser.add_argument("--query", default=DEFAULT_GMAIL_QUERY)
    parser.add_argument("--max-results", type=int, default=200)
    parser.add_argument("--max-bytes", type=int, default=25_000_000)
    parser.add_argument("--evidence-dir", default="private-output/evidence")
    parser.add_argument("--output", default="data/exports/Piping_E3D_Jobs.xlsx")
    parser.add_argument("--no-export", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = import_gmail_alerts(
        args.db,
        args.evidence_dir,
        credentials_path=args.credentials,
        token_path=args.token,
        query=args.query,
        max_results=args.max_results,
        max_bytes=args.max_bytes,
    )
    print(
        "GMAIL: "
        f"attempted={summary.attempted} created={summary.created} "
        f"updated={summary.updated} duplicates={summary.duplicates} "
        f"failed={summary.failed} review_required={summary.review_required}"
    )
    for result in summary.results:
        if result.status == "failed":
            print(f"FAIL: {result.input_path} | {result.error_message}")
    if not args.no_export:
        output = export_excel(args.db, args.output)
        errors = verify_excel(output)
        if errors:
            print("FAIL: " + " | ".join(errors))
            return 2
        print(f"PASS: Excel exported and verified at {output}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
