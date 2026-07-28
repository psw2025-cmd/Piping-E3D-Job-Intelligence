from __future__ import annotations

import argparse

from job_intelligence.source_discovery import discover_registry, write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and verify official public ATS and JobPosting sitemap sources "
            "without using Gmail."
        )
    )
    parser.add_argument("--registry", default="config/employer_registry.yaml")
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    records, runtime = discover_registry(args.registry, args.base_sources)
    write_outputs(
        records,
        runtime,
        report_json=args.report_json,
        report_md=args.report_md,
        runtime_sources=args.runtime_sources,
    )
    verified = sum(record.probe_status == "pass" for record in records)
    print(
        f"PASS: official-source discovery completed; "
        f"detected={len(records)} verified={verified}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
