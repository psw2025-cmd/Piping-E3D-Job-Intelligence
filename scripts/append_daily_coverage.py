from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_intelligence.coverage_workbook import (
    append_coverage_sheets,
    verify_coverage_workbook,
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _write_status(path: Path, status: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _replace_summary_section(summary: str, section: str) -> str:
    marker = "\n## Worldwide coverage proof\n"
    if marker in summary:
        summary = summary.split(marker, 1)[0].rstrip() + "\n"
    return summary.rstrip() + "\n" + section


def _rebuild_bundle(output_dir: Path) -> None:
    destination = output_dir / "Piping_E3D_Daily_Bundle.zip"
    destination.unlink(missing_ok=True)
    archive_base = output_dir.parent / "Piping_E3D_Daily_Bundle_coverage"
    archive_path = Path(
        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=output_dir.parent,
            base_dir=output_dir.name,
        )
    )
    archive_path.replace(destination)


def run(output_dir: Path, config_dir: Path) -> int:
    status_path = output_dir / "status.json"
    summary_path = output_dir / "SUMMARY.md"
    log_path = output_dir / "run.log"
    db_path = output_dir / "jobs.db"
    workbook_path = output_dir / "Piping_E3D_Jobs.xlsx"
    if not status_path.exists():
        raise FileNotFoundError(f"daily status does not exist: {status_path}")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    try:
        frames = append_coverage_sheets(
            db_path,
            workbook_path,
            config_dir=config_dir,
        )
        errors = verify_coverage_workbook(workbook_path)
        if errors:
            raise ValueError(" | ".join(errors))
        registry = frames["Company_Registry"]
        country = frames["Country_Coverage"]
        active = int(registry["coverage_active"].sum()) if not registry.empty else 0
        india = country[country["country"].eq("India")]
        india_percentage = (
            float(india.iloc[0]["coverage_percentage"]) if not india.empty else 0.0
        )
        status.update(
            {
                "coverage_verified": True,
                "coverage_generated_at": _now(),
                "coverage_company_count": len(registry),
                "coverage_active_count": active,
                "india_coverage_percentage": india_percentage,
            }
        )
        section = "\n".join(
            [
                "",
                "## Worldwide coverage proof",
                "",
                f"- Registry companies: `{len(registry)}`",
                f"- Active direct/alert/notice/manual coverage: `{active}`",
                f"- India batch coverage: `{india_percentage:.1f}%`",
                f"- Coverage workbook verification: `PASS`",
                "- Coverage sheets: `Company_Registry`, `Country_Coverage`, "
                "`Missing_Companies`, `ATS_Coverage`, `Coverage_Gaps` and proof views",
                "",
            ]
        )
        summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
        summary_path.write_text(
            _replace_summary_section(summary, section),
            encoding="utf-8",
        )
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"{_now()} worldwide coverage PASS companies={len(registry)} "
                f"active={active} india_coverage={india_percentage:.1f}%\n"
            )
        _write_status(status_path, status)
        _rebuild_bundle(output_dir)
        print(
            f"PASS: worldwide coverage appended | companies={len(registry)} | "
            f"active={active} | India={india_percentage:.1f}%"
        )
        return 0
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        status["coverage_verified"] = False
        status["coverage_generated_at"] = _now()
        status["verified"] = False
        status["exit_code"] = 2
        previous = str(status.get("error") or "").strip()
        status["error"] = f"{previous} | Coverage failure: {message}" if previous else message
        _write_status(status_path, status)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"{_now()} ERROR worldwide coverage {message}\n")
            log.write(traceback.format_exc())
        try:
            _rebuild_bundle(output_dir)
        except Exception as bundle_exc:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(
                    f"{_now()} ERROR rebuilding coverage bundle: "
                    f"{type(bundle_exc).__name__}: {bundle_exc}\n"
                )
        print(f"FAIL: worldwide coverage append failed: {message}")
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append worldwide coverage proof to the verified daily artifact."
    )
    parser.add_argument("--output", default="output/daily")
    parser.add_argument("--config-dir", default="config")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run(Path(args.output), Path(args.config_dir))


if __name__ == "__main__":
    sys.exit(main())
