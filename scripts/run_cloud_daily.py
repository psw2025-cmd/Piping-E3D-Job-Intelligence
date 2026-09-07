from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_intelligence.cli import _verify_database
from job_intelligence.collection_runner import CollectionRunSummary, collect_sources
from job_intelligence.excel_export import export_excel, verify_excel
from job_intelligence.proof import set_run_export_status
from job_intelligence.source_config import load_source_config


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _markdown(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _query_rows(db_path: Path, query: str) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(query).fetchall()
    finally:
        connection.close()


def _build_summary(
    db_path: Path,
    status: dict[str, Any],
) -> str:
    runs = _query_rows(
        db_path,
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1",
    )
    health = _query_rows(
        db_path,
        "SELECT source_id, source_name, status, records_found, error_message, "
        "last_success_at FROM source_health ORDER BY source_id",
    )
    evidence = _query_rows(
        db_path,
        "SELECT source_id, COUNT(*) AS files, SUM(size_bytes) AS bytes "
        "FROM source_evidence GROUP BY source_id ORDER BY source_id",
    )
    jobs = _query_rows(
        db_path,
        "SELECT company, title, location, published_at, match_score, priority, "
        "apply_url FROM jobs "
        "ORDER BY match_score DESC, published_at DESC, company, title LIMIT 100",
    )

    run = runs[0] if runs else None
    result = "PASS" if status["exit_code"] == 0 else "FAIL"
    lines = [
        "# Daily Piping/E3D Job Intelligence",
        "",
        f"Generated: `{status['generated_at']}`",
        f"Overall result: **{result}**",
        f"Collection status: `{status.get('collection_status', 'not_started')}`",
        f"Verification: `{'PASS' if status.get('verified') else 'FAIL'}`",
    ]
    if status.get("error"):
        lines.append(f"Error: `{_markdown(status['error'])}`")

    if run is not None:
        lines.extend(
            [
                "",
                "## Run proof",
                "",
                f"- Run ID: `{run['run_id']}`",
                (f"- Sources attempted/passed/failed: "
                f"`{run['sources_attempted']}/{run['sources_passed']}/"
                f"{run['sources_failed']}`"),
                f"- Filtered jobs collected: `{run['jobs_collected']}`",
                f"- New jobs: `{run['new_jobs']}`",
                f"- Export status: `{run['export_status']}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Source health",
            "",
            "| Source | Status | Records | Last success | Message |",
            "|---|---:|---:|---|---|",
        ]
    )
    if health:
        for row in health:
            lines.append(
                f"| {_markdown(row['source_name'])} (`{row['source_id']}`) | "
                f"{_markdown(row['status'])} | {row['records_found']} | "
                f"{_markdown(row['last_success_at'])} | "
                f"{_markdown(row['error_message'])} |"
            )
    else:
        lines.append("| No source records | — | 0 | — | — |")

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            "| Source | Files | Bytes |",
            "|---|---:|---:|",
        ]
    )
    if evidence:
        for row in evidence:
            lines.append(
                f"| `{row['source_id']}` | {row['files']} | {row['bytes'] or 0} |"
            )
    else:
        lines.append("| No evidence | 0 | 0 |")

    lines.extend(
        [
            "",
            "## Filtered target jobs",
            "",
            "| Company | Title | Location | Posted | Score | Priority | Apply |",
            "|---|---|---|---|---:|---|---|",
        ]
    )
    if jobs:
        for row in jobs:
            apply_url = str(row["apply_url"] or "").strip()
            apply_cell = f"[Open]({apply_url})" if apply_url else "—"
            lines.append(
                f"| {_markdown(row['company'])} | {_markdown(row['title'])} | "
                f"{_markdown(row['location'])} | "
                f"{_markdown(row['published_at'])} | {row['match_score']} | "
                f"{_markdown(row['priority'])} | {apply_cell} |"
            )
    else:
        lines.append("| No filtered matches | — | — | — | 0 | — | — |")

    lines.extend(
        [
            "",
            "## Artifact contents",
            "",
            "- `Piping_E3D_Jobs.xlsx` — verified Excel tracker",
            "- `jobs.db` — SQLite ledger and proof tables",
            "- `raw/` — public source evidence retained with SHA-256 records",
            "- `run.log` — execution log",
            "- `status.json` — machine-readable result",
            "- `Piping_E3D_Daily_Bundle.zip` — portable bundle preserving paths",
            "",
        ]
    )
    return "\n".join(lines)


def _write_bundle(output_dir: Path) -> None:
    archive_base = output_dir.parent / "Piping_E3D_Daily_Bundle"
    archive_path = Path(
        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=output_dir.parent,
            base_dir=output_dir.name,
        )
    )
    destination = output_dir / archive_path.name
    destination.unlink(missing_ok=True)
    archive_path.replace(destination)


def _write_status_files(
    output_dir: Path,
    db_path: Path,
    status: dict[str, Any],
    log_lines: list[str],
) -> str:
    status["generated_at"] = _now()
    (output_dir / "run.log").write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )
    (output_dir / "status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_text = _build_summary(db_path, status)
    (output_dir / "SUMMARY.md").write_text(summary_text, encoding="utf-8")
    return summary_text


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "jobs.db"
    evidence_dir = output_dir / "raw"
    workbook_path = output_dir / "Piping_E3D_Jobs.xlsx"
    log_lines = [f"{_now()} START cloud daily run"]
    status: dict[str, Any] = {
        "generated_at": _now(),
        "exit_code": 2,
        "collection_status": "not_started",
        "verified": False,
        "error": "",
        "run_id": "",
    }
    collection: CollectionRunSummary | None = None

    try:
        config = load_source_config(args.sources)
        enabled_count = sum(source.enabled for source in config.sources)
        log_lines.append(
            f"{_now()} validated {len(config.sources)} sources; "
            f"{enabled_count} enabled"
        )

        collection = collect_sources(
            db_path,
            args.sources,
            evidence_dir,
        )
        status["collection_status"] = collection.status
        status["run_id"] = collection.run_id
        status.update(
            {
                "sources_attempted": collection.sources_attempted,
                "sources_passed": collection.sources_passed,
                "sources_failed": collection.sources_failed,
                "jobs_collected": collection.jobs_collected,
                "new_jobs": collection.new_jobs,
                "updated_jobs": collection.updated_jobs,
            }
        )
        log_lines.append(
            f"{_now()} collection status={collection.status} "
            f"sources={collection.sources_passed}/{collection.sources_attempted} "
            f"jobs={collection.jobs_collected} new={collection.new_jobs} "
            f"updated={collection.updated_jobs}"
        )
        for source in collection.source_results:
            log_lines.append(
                f"{_now()} source={source.source_id} status={source.status} "
                f"jobs={source.jobs_collected} new={source.new_jobs} "
                f"updated={source.updated_jobs} message={source.error_message}"
            )

        export_excel(db_path, workbook_path)
        verification_errors = _verify_database(str(db_path)) + verify_excel(workbook_path)
        if verification_errors:
            raise ValueError(" | ".join(verification_errors))

        acceptable_statuses = {"pass"}
        if getattr(args, "allow_no_sources", False):
            acceptable_statuses.add("no_sources")
        if collection.status not in acceptable_statuses:
            raise RuntimeError(
                f"collection finished with non-success status {collection.status}; "
                "partial source results are not verified"
            )

        set_run_export_status(db_path, collection.run_id, "pass")
        status["verified"] = True
        status["exit_code"] = 0
        log_lines.append(f"{_now()} database, evidence and workbook verification PASS")
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
        log_lines.append(f"{_now()} ERROR {status['error']}")
        log_lines.append(traceback.format_exc())
        if collection is not None:
            try:
                set_run_export_status(
                    db_path,
                    collection.run_id,
                    "fail",
                    status["error"],
                )
            except Exception as proof_exc:
                log_lines.append(
                    f"{_now()} ERROR recording export failure: "
                    f"{type(proof_exc).__name__}: {proof_exc}"
                )
    finally:
        summary_text = _write_status_files(output_dir, db_path, status, log_lines)
        try:
            _write_bundle(output_dir)
        except Exception as bundle_exc:
            status["exit_code"] = 2
            status["verified"] = False
            bundle_error = f"{type(bundle_exc).__name__}: {bundle_exc}"
            previous_error = str(status.get("error") or "").strip()
            status["error"] = (
                f"{previous_error} | Bundle failure: {bundle_error}"
                if previous_error
                else bundle_error
            )
            log_lines.append(f"{_now()} ERROR {bundle_error}")
            log_lines.append(traceback.format_exc())
            (output_dir / "Piping_E3D_Daily_Bundle.zip").unlink(missing_ok=True)
            if collection is not None:
                try:
                    set_run_export_status(
                        db_path,
                        collection.run_id,
                        "fail",
                        status["error"],
                    )
                except Exception as proof_exc:
                    log_lines.append(
                        f"{_now()} ERROR recording bundle failure: "
                        f"{type(proof_exc).__name__}: {proof_exc}"
                    )
            summary_text = _write_status_files(output_dir, db_path, status, log_lines)
        print(summary_text)

    return int(status["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the verified daily cloud job-intelligence workflow."
    )
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--output", default="output/daily")
    parser.add_argument(
        "--allow-no-sources",
        action="store_true",
        help="Treat a validated zero-source CI configuration as successful.",
    )
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
