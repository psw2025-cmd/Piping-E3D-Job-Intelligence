from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from job_intelligence.source_config import load_source_config
from job_intelligence.source_discovery import (
    DiscoveryRecord,
    _source_identity,
    write_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge sharded official ATS and sitemap discovery reports."
    )
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--base-sources", default="config/sources.yaml")
    parser.add_argument(
        "--report-json",
        default="docs/LATEST_OFFICIAL_SOURCE_DISCOVERY.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/LATEST_OFFICIAL_SOURCE_DISCOVERY.md",
    )
    parser.add_argument(
        "--runtime-sources",
        default="config/runtime_sources.generated.yaml",
    )
    return parser


def _load_records(root: Path) -> list[DiscoveryRecord]:
    records: list[DiscoveryRecord] = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw_records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(raw_records, list):
            continue
        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            try:
                records.append(
                    DiscoveryRecord(
                        company=str(raw.get("company", "")),
                        platform=str(raw.get("platform", "")),
                        evidence_url=str(raw.get("evidence_url", "")),
                        source=dict(raw.get("source", {})),
                        confidence=str(raw.get("confidence", "candidate")),
                        probe_status=str(raw.get("probe_status", "not_probed")),
                        probe_jobs=int(raw.get("probe_jobs", 0) or 0),
                        error=str(raw.get("error", "")),
                    )
                )
            except (TypeError, ValueError):
                continue
    return records


def _merge_runtime(
    base_sources_path: Path,
    records: list[DiscoveryRecord],
) -> tuple[list[DiscoveryRecord], dict[str, Any]]:
    base = yaml.safe_load(base_sources_path.read_text(encoding="utf-8")) or {}
    load_source_config(base_sources_path)
    base_sources = base.get("sources", [])
    if not isinstance(base_sources, list):
        raise ValueError("base source configuration requires a sources list")
    identities = {
        _source_identity(source)
        for source in base_sources
        if isinstance(source, dict)
    }
    ids = {
        str(source.get("id", ""))
        for source in base_sources
        if isinstance(source, dict)
    }
    merged_records: list[DiscoveryRecord] = []
    generated: list[dict[str, Any]] = []
    seen_record_keys: set[tuple[str, str, str]] = set()
    for record in records:
        record_key = (
            record.company.casefold(),
            record.platform.casefold(),
            record.evidence_url.casefold(),
        )
        if record_key not in seen_record_keys:
            seen_record_keys.add(record_key)
            merged_records.append(record)
        if record.probe_status != "pass" or record.source.get("enabled") is not True:
            continue
        identity = _source_identity(record.source)
        source_id = str(record.source.get("id", ""))
        if identity in identities or not source_id or source_id in ids:
            continue
        identities.add(identity)
        ids.add(source_id)
        generated.append(record.source)
    runtime = {
        "sources": [*base_sources, *generated],
        "policy": {
            **(base.get("policy", {}) if isinstance(base.get("policy"), dict) else {}),
            "respect_robots_txt": True,
            "skip_login_required_pages": True,
            "bypass_captcha": False,
            "use_rotating_proxies": False,
            "retain_source_evidence": True,
        },
    }
    return merged_records, runtime


def main() -> int:
    args = build_parser().parse_args()
    records = _load_records(Path(args.input_root))
    merged_records, runtime = _merge_runtime(Path(args.base_sources), records)
    write_outputs(
        merged_records,
        runtime,
        report_json=args.report_json,
        report_md=args.report_md,
        runtime_sources=args.runtime_sources,
    )
    enabled_generated = len(runtime["sources"]) - len(
        (yaml.safe_load(Path(args.base_sources).read_text(encoding="utf-8")) or {}).get(
            "sources", []
        )
    )
    print(
        "PASS: discovery shards merged; "
        f"records={len(merged_records)} generated_sources={enabled_generated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
