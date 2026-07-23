from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_intelligence.collectors import COLLECTORS
from job_intelligence.collectors.http_client import SafeHttpClient
from job_intelligence.source_config import SourceSpec, load_source_config


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _safe_suffix(value: str) -> str:
    suffix = value.lower() if value.startswith(".") else f".{value.lower()}"
    return suffix if suffix in {".html", ".pdf", ".xml", ".json", ".bin"} else ".bin"


def _proof_spec(source: SourceSpec, max_notices: int, max_pdf_pages: int) -> SourceSpec:
    options = dict(source.options)
    options["max_items"] = min(source.int_option("max_items", max_notices), max_notices)
    options["max_pdf_pages"] = min(
        source.int_option("max_pdf_pages", max_pdf_pages),
        max_pdf_pages,
    )
    options["rate_limit_per_minute"] = min(
        source.int_option("rate_limit_per_minute", 10),
        10,
    )
    options["timeout_seconds"] = min(source.int_option("timeout_seconds", 30), 30)
    options["max_response_bytes"] = min(
        source.int_option("max_response_bytes", 15_000_000),
        15_000_000,
    )
    return replace(source, enabled=True, options=options)


def _save_evidence(
    output: Path,
    source_id: str,
    artifacts: list[Any],
) -> list[dict[str, Any]]:
    destination = output / "evidence" / source_id
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts, start=1):
        digest = hashlib.sha256(artifact.body).hexdigest()
        suffix = _safe_suffix(artifact.suffix)
        path = destination / f"{index:03d}_{digest[:16]}{suffix}"
        path.write_bytes(artifact.body)
        records.append(
            {
                "source_url": artifact.source_url,
                "file_path": str(path),
                "sha256": digest,
                "content_type": artifact.content_type,
                "status_code": artifact.status_code,
                "size_bytes": len(artifact.body),
            }
        )
    return records


def _source_result(
    source: SourceSpec,
    output: Path,
    *,
    max_notices: int,
    max_pdf_pages: int,
    min_notices: int,
) -> dict[str, Any]:
    proof_source = _proof_spec(source, max_notices, max_pdf_pages)
    client = SafeHttpClient(
        timeout_seconds=proof_source.int_option("timeout_seconds", 30),
        max_response_bytes=proof_source.int_option(
            "max_response_bytes", 15_000_000
        ),
        rate_limit_per_minute=proof_source.int_option(
            "rate_limit_per_minute", 10
        ),
        max_redirects=proof_source.int_option("max_redirects", 5, minimum=0),
        allowed_domains=proof_source.text_list_option("allowed_domains") or None,
    )
    try:
        collector = COLLECTORS[proof_source.source_type]
    except KeyError as exc:
        raise ValueError(
            f"no production collector registered for {proof_source.source_type!r}"
        ) from exc
    result = collector(proof_source, client)
    evidence = _save_evidence(output, source.source_id, result.evidence)
    jobs = [
        {
            "title": job.title,
            "company": job.company,
            "published_at": job.published_at,
            "closing_at": job.closing_at,
            "apply_url": job.apply_url,
            "source_url": job.source_url,
            "notice_kind": (
                job.description.splitlines()[0]
                if job.description.startswith("Notice kind:")
                else ""
            ),
        }
        for job in result.jobs
    ]
    errors: list[str] = []
    if not evidence:
        errors.append("no listing or document evidence was saved")
    if len(jobs) < min_notices:
        errors.append(
            f"expected at least {min_notices} accepted notice(s), found {len(jobs)}"
        )
    return {
        "source_id": source.source_id,
        "name": source.name,
        "company": source.company,
        "status": "pass" if not errors else "fail",
        "jobs_found": len(jobs),
        "evidence_files": len(evidence),
        "warnings": result.warnings,
        "errors": errors,
        "jobs": jobs,
        "evidence": evidence,
    }


def run(
    config_path: Path,
    output: Path,
    *,
    only: set[str] | None,
    max_notices: int,
    max_pdf_pages: int,
    min_notices: int,
) -> int:
    output.mkdir(parents=True, exist_ok=True)
    config = load_source_config(config_path)
    selected = [
        source
        for source in config.sources
        if source.source_type == "public_notice"
        and (only is None or source.source_id in only)
    ]
    if only:
        unknown = sorted(only - {source.source_id for source in selected})
        if unknown:
            raise ValueError(f"unknown public notice sources: {', '.join(unknown)}")
    if not selected:
        raise ValueError("no public notice sources selected")

    results: list[dict[str, Any]] = []
    for source in selected:
        try:
            result = _source_result(
                source,
                output,
                max_notices=max_notices,
                max_pdf_pages=max_pdf_pages,
                min_notices=min_notices,
            )
        except Exception as exc:
            result = {
                "source_id": source.source_id,
                "name": source.name,
                "company": source.company,
                "status": "fail",
                "jobs_found": 0,
                "evidence_files": 0,
                "warnings": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
                "jobs": [],
                "evidence": [],
            }
        results.append(result)
        print(
            f"SOURCE: {source.source_id} | {result['status']} | "
            f"jobs={result['jobs_found']} evidence={result['evidence_files']}"
        )
        for error in result["errors"]:
            print(f"FAIL: {source.source_id} | {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {source.source_id} | {warning}")

    failed = sum(result["status"] != "pass" for result in results)
    status = {
        "generated_at": _now(),
        "config": str(config_path),
        "sources_attempted": len(results),
        "sources_passed": len(results) - failed,
        "sources_failed": failed,
        "max_notices_per_source": max_notices,
        "max_pdf_pages": max_pdf_pages,
        "min_notices_per_source": min_notices,
        "verified": failed == 0,
        "results": results,
    }
    (output / "status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_lines = [
        "# India Public Notice Live Contract Proof",
        "",
        f"- Generated: `{status['generated_at']}`",
        f"- Sources passed: `{status['sources_passed']}/{status['sources_attempted']}`",
        f"- Verification: `{'PASS' if status['verified'] else 'FAIL'}`",
        "",
        "| Source | Status | Notices | Evidence | Warnings |",
        "|---|---:|---:|---:|---:|",
    ]
    for result in results:
        summary_lines.append(
            f"| {result['source_id']} | {result['status']} | "
            f"{result['jobs_found']} | {result['evidence_files']} | "
            f"{len(result['warnings'])} |"
        )
    (output / "SUMMARY.md").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded live contract proof for official public notices."
    )
    parser.add_argument("--config", default="config/sources.india-notices.yaml")
    parser.add_argument("--output", default="output/live-india-notices")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--max-notices", type=int, default=5)
    parser.add_argument("--max-pdf-pages", type=int, default=10)
    parser.add_argument("--min-notices", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run(
        Path(args.config),
        Path(args.output),
        only=set(args.only) if args.only else None,
        max_notices=args.max_notices,
        max_pdf_pages=args.max_pdf_pages,
        min_notices=args.min_notices,
    )


if __name__ == "__main__":
    sys.exit(main())
