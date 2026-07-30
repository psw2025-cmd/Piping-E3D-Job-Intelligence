from __future__ import annotations

import argparse
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from job_intelligence import source_discovery
from job_intelligence.source_discovery import discover_registry, write_outputs

NAME_FIELDS = (
    "canonical_company_name",
    "name",
    "company",
    "organization",
)
URL_FIELDS = (
    "direct_ats_endpoint",
    "public_job_url",
    "official_jobs_url",
    "official_careers_url",
    "careers_url",
    "career_url",
    "careers_page",
    "official_url",
    "official_domain",
    "website",
    "url",
)

_ORIGINAL_PROBE = source_discovery.probe_record


def _bounded_probe(record: source_discovery.DiscoveryRecord):
    production_source = deepcopy(record.source)
    probe_source = deepcopy(record.source)
    source_type = str(probe_source.get("type", ""))
    probe_source["max_items"] = 3
    probe_source["max_pages"] = 3
    if source_type in {"workday", "oracle_hcm"}:
        probe_source["max_scan_items"] = 80
        probe_source["page_size"] = 20
    elif source_type == "smartrecruiters":
        probe_source["page_size"] = 3
        probe_source["fetch_details"] = True
    elif source_type == "lever":
        probe_source["page_size"] = 3
    if source_type == "workday":
        probe_source["search_terms"] = ["piping"]
    record.source = probe_source
    result = _ORIGINAL_PROBE(record)
    if result.probe_status == "pass":
        result.source = production_source
    else:
        production_source["enabled"] = False
        result.source = production_source
    return result


def _record_name(record: dict[str, Any]) -> str:
    for field in NAME_FIELDS:
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return ""


def _iter_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        if _record_name(payload):
            yield payload
        for value in payload.values():
            yield from _iter_records(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_records(item)


def _http_urls(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in URL_FIELDS:
        raw = record.get(field)
        candidates = raw if isinstance(raw, list) else [raw]
        for candidate in candidates:
            value = str(candidate or "").strip().split("#", 1)[0]
            if value.startswith(("http://", "https://")) and value not in values:
                values.append(value)
    return values


def build_combined_registry(
    registry_paths: list[str],
    output_path: Path,
    *,
    shard_index: int,
    shard_count: int,
    max_organizations: int,
) -> int:
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid shard configuration")
    targets: list[dict[str, str]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    position = 0
    for registry_path in registry_paths:
        payload = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        for record in _iter_records(payload):
            company = _record_name(record)
            urls = _http_urls(record)
            if not company or not urls or company.endswith("Job Alerts"):
                continue
            key = (company.casefold(), tuple(url.casefold() for url in urls))
            if key in seen:
                continue
            seen.add(key)
            if position % shard_count == shard_index:
                targets.append(
                    {
                        "company": company,
                        "official_careers_url": urls[0],
                        "public_job_url": urls[1] if len(urls) > 1 else "",
                    }
                )
                if max_organizations and len(targets) >= max_organizations:
                    break
            position += 1
        if max_organizations and len(targets) >= max_organizations:
            break
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump({"employers": targets}, sort_keys=False),
        encoding="utf-8",
    )
    return len(targets)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and verify official public ATS and JobPosting sitemap sources "
            "without using Gmail."
        )
    )
    parser.add_argument(
        "--registry",
        action="append",
        default=[],
        help="Repeat for each employer or recruiter registry to scan.",
    )
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
        default="output/source-discovery/runtime-sources.yaml",
    )
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--max-organizations", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    registries = args.registry or ["config/employer_registry.yaml"]
    combined_path = Path(args.runtime_sources).with_name("combined-registry.yaml")
    target_count = build_combined_registry(
        registries,
        combined_path,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        max_organizations=args.max_organizations,
    )
    source_discovery.probe_record = _bounded_probe
    records, runtime = discover_registry(combined_path, args.base_sources)
    write_outputs(
        records,
        runtime,
        report_json=args.report_json,
        report_md=args.report_md,
        runtime_sources=args.runtime_sources,
    )
    verified = sum(record.probe_status == "pass" for record in records)
    print(
        "PASS: official-source discovery completed; "
        f"targets={target_count} detected={len(records)} verified={verified} "
        f"shard={args.shard_index}/{args.shard_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
