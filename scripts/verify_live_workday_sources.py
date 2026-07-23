from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from job_intelligence.collectors.http_client import SafeHttpClient
from job_intelligence.collectors.workday import collect_workday
from job_intelligence.source_config import load_source_config

SOURCE_IDS = ("kbr_workday", "atkinsrealis_workday")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config = load_source_config(root / "config" / "sources.yaml")
    by_id = {source.source_id: source for source in config.sources}
    proof: list[dict[str, object]] = []

    for source_id in SOURCE_IDS:
        source = by_id[source_id]
        constrained = replace(
            source,
            options={
                **source.options,
                "search_terms": ["piping"],
                "include_terms": ["piping", "pipe layout", "pipe support"],
                "location_terms": [],
                "max_items": 3,
                "max_scan_items": 40,
                "max_pages": 2,
                "page_size": 20,
                "rate_limit_per_minute": 60,
            },
        )
        client = SafeHttpClient(
            timeout_seconds=30,
            max_response_bytes=5_000_000,
            rate_limit_per_minute=60,
            max_redirects=3,
        )
        result = collect_workday(constrained, client)
        if not result.evidence:
            raise RuntimeError(f"{source_id} returned no verifiable evidence")
        if not result.jobs:
            raise RuntimeError(f"{source_id} returned no current piping job")
        expected_host = (urlsplit(source.require_text("base_url")).hostname or "").lower()
        for job in result.jobs:
            apply_host = (urlsplit(job.apply_url).hostname or "").lower()
            source_host = (urlsplit(job.source_url).hostname or "").lower()
            if expected_host not in {apply_host, source_host}:
                raise RuntimeError(
                    f"{source_id} returned an unexpected job host: {job.apply_url}"
                )
            if not job.title or not job.company or not job.location:
                raise RuntimeError(f"{source_id} returned incomplete required fields")
        proof.append(
            {
                "source_id": source_id,
                "company": source.company,
                "jobs": len(result.jobs),
                "evidence": len(result.evidence),
                "sample_titles": [job.title for job in result.jobs[:3]],
                "sample_urls": [job.apply_url for job in result.jobs[:3]],
            }
        )

    print(json.dumps({"status": "PASS", "sources": proof}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
