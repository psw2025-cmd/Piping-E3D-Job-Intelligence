_from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from job_intelligence.database import JOB_COLUMNS, init_database
from job_intelligence.excel_export import export_excel, verify_excel
from job_intelligence.proof import init_proof_tables
from job_intelligence.run_cloud_daily import _build_summary

_TABLES = (
    "jobs",
    "job_identity_aliases",
    "source_health",
    "runs",
    "source_evidence",
    "private_imports",
    "gmail_alert_messages",
    "gmail_alert_jobs",
)
_SHARD_RE = re.compile(r"shard-\d{3}")


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]


def shard_id_for(path: Path) -> str | None:
    for part in reversed(path.parts):
        match = _SHARD_RE.search(part)
        if match:
            return match.group(0)
    return None


def evidence_destination(old_path: str, raw_destination: Path) -> str:
    path = Path(old_path)
    parts = list(path.parts)
    if "raw" in parts:
        relative = Path(*parts[parts.index("raw") + 1 :])
    else:
        relative = Path(path.name)
    return str(raw_destination / relative)


def copy_table(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    table: str,
    *,
    raw_destination: Path | None = None,
) -> int:
    if not table_exists(source, table) or not table_exists(destination, table):
        return 0
    source_columns = columns(source, table)
    destination_columns = columns(destination, table)
    selected = [column for column in source_columns if column in destination_columns]
    if not selected:
        return 0
    placeholders = ", ".join("?" for _ in selected)
    quoted = ", ".join(f'"{column}"' for column in selected)
    sql = (
        f'INSERT OR REPLACE INTO "{table}" ({quoted}) '
        f"VALUES ({placeholders})"
    )
    path_index = selected.index("file_path") if table == "source_evidence" and "file_path" in selected else None
    count = 0
    for row in source.execute(f'SELECT {quoted} FROM "{table}"'):
        values = list(row)
        if path_index is not None and raw_destination is not None:
            values[path_index] = evidence_destination(str(values[path_index]), raw_destination)
        destination.execute(sql, values)
        count += 1
    return count


def write_bundle(output_dir: Path) -> None:
    destination = output_dir / "Piping_E3D_Daily_Bundle.zip"
    destination.unlink(missing_ok=True)
    archive_base = output_dir.parent / "Piping_E3D_Daily_Bundle_batched"
    archive_path = Path(
        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=output_dir.parent,
            base_dir=output_dir.name,
        )
    )
    archive_path.replace(destination)


def merge(plan_path: Path, shards_root: Path, output_dir: Path) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    expected = {item["id"] for item in plan.get("shards", [])}
    status_files = list(shards_root.rglob("status.json"))
    statuses: dict[str, dict] = {}
    shard_dirs: dict[str, Path] = {}
    for status_path in status_files:
        shard_id = shard_id_for(status_path.parent)
        if not shard_id:
            continue
        statuses[shard_id] = json.loads(status_path.read_text(encoding="utf-8"))
        shard_dirs[shard_id] = status_path.parent

    missing = sorted(expected - set(statuses))
    shard_errors = []
    for shard_id in sorted(expected):
        status = statuses.get(shard_id)
        if status is None:
            shard_errors.append(f"missing shard artifact: {shard_id}")
        elif status.get("exit_code") != 0 or status.get("verified") is not True:
            shard_errors.append(
                f"{shard_id}: {status.get('error') or status.get('collection_status') or 'unverified'}"
            )

    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_db = output_dir / "jobs.db"
    init_database(merged_db)
    init_proof_tables(merged_db)
    raw_root = output_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    copied_tables = {table: 0 for table in _TABLES}

    with sqlite3.connect(merged_db) as destination:
        for shard_id in sorted(shard_dirs):
            shard_dir = shard_dirs[shard_id]
            shard_db = shard_dir / "jobs.db"
            if not shard_db.exists():
                shard_errors.append(f"{shard_id}: jobs.db missing")
                continue
            source_raw = shard_dir / "raw"
            raw_destination = raw_root / shard_id
            if source_raw.exists():
                shutil.copytree(source_raw, raw_destination, dirs_exist_ok=True)
            with sqlite3.connect(shard_db) as source:
                for table in _TABLES:
                    copied_tables[table] += copy_table(
                        source,
                        destination,
                        table,
                        raw_destination=raw_destination if source_raw.exists() else None,
                    )
        destination.commit()

    attempted = sum(int(item.get("sources_attempted", 0)) for item in statuses.values())
    passed = sum(int(item.get("sources_passed", 0)) for item in statuses.values())
    failed = sum(int(item.get("sources_failed", 0)) for item in statuses.values())
    jobs = sum(int(item.get("jobs_collected", 0)) for item in statuses.values())
    new_jobs = sum(int(item.get("new_jobs", 0)) for item in statuses.values())
    updated_jobs = sum(int(item.get("updated_jobs", 0)) for item in statuses.values())
    all_shards_passed = not shard_errors and expected == set(statuses)

    status = {
        "generated_at": now(),
        "run_id": f"batched-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "exit_code": 1 if not all_shards_passed else 0,
        "collection_status": "pass" if all_shards_passed else ("partial" if passed else "fail"),
        "verified": False,
        "coverage_verified": False,
        "error": " | ".join(shard_errors),
        "sources_attempted": attempted,
        "sources_passed": passed,
        "sources_failed": failed,
        "jobs_collected": jobs,
        "new_jobs": new_jobs,
        "updated_jobs": updated_jobs,
        "shards_expected": len(expected),
        "shards_completed": len(statuses),
        "shards_failed": len(shard_errors),
    }
    (output_dir / "shard_statuses.json").write_text(
        json.dumps({"plan": plan, "statuses": statuses, "errors": shard_errors}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    export_error = ""
    try:
        workbook = output_dir / "Piping_E3D_Jobs.xlsx"
        export_excel(merged_db, workbook)
        errors = verify_excel(workbook)
        if errors:
            export_error = " | ".join(errors)
    except Exception as exc:  # pragma: no cover - CI reports the exact export failure
        export_error = f"{type(exc).__name__}: {exc}"
    if export_error:
        status["error"] = " | ".join(filter(None, [status["error"], export_error]))
        status["exit_code"] = 1
        status["verified"] = False
    else:
        status["verified"] = all_shards_passed

    (output_dir / "status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "run.log").write_text(
        f"{now()} merged {len(statuses)}/{len(expected)} shards; "
        f"sources={passed}/{attempted}; jobs={jobs}; errors={status['error']}\n",
        encoding="utf-8",
    )
    summary = _build_summary(merged_db, status)
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    write_bundle(output_dir)
    print(json.dumps({"status": status, "copied_tables": copied_tables}, sort_keys=True))
    return int(status["exit_code"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--shards-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    return merge(args.plan, args.shards_root, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
dir / "shard_statuses.json").write_text(
          json.dumps({"plan": plan, "statuses": statuses, "errors": shard_errors}, indent=2)
          + "\n",
          encoding="utf-8",
)

    export_error = ""
    try:
              workbook = output_dir / "Piping_E3D_Jobs.xlsx"
              export_excel(merged_db, workbook)
              errors = verify_excel(workbook)
              if errors:
                            export_error = " | ".join(errors)
    except Exception as exc:  # pragma: no cover - CI reports the exact export failure
              export_error = f"{type(exc).__name__}: {exc}"
          if export_error:
                    status["error"] = " | ".join(filter(None, [status["error"], export_error]))
                    status["exit_code"] = 1
                    status
