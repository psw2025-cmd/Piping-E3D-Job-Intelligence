from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from job_intelligence.collectors.http_client import SafeHttpClient
from job_intelligence.collectors.public_html import collect_public_html
from job_intelligence.source_registry import load_source_registry

SOURCE_IDS = (
    "airswift_global_public",
    "nesfircroft_piping_public",
    "brunel_global_public",
)
PROOF_PATH = Path("live-recruiter-proof.json")


def _verify_source(source_id: str, source) -> dict[str, object]:
    max_pages = 33 if source_id == "airswift_global_public" else 8
    if source_id == "brunel_global_public":
        max_pages = 1
    constrained = replace(
        source,
        options={
            **source.options,
            "max_items": 3,
            "max_pages": max_pages,
            "rate_limit_per_minute": 60,
        },
    )
    client = SafeHttpClient(
        timeout_seconds=30,
        max_response_bytes=5_000_000,
        rate_limit_per_minute=60,
        max_redirects=5,
    )
    result = collect_public_html(
        constrained,
        client,
        respect_robots_txt=True,
    )
    if not result.evidence:
        raise RuntimeError(f"{source_id} returned no verifiable evidence")
    if not result.jobs:
        raise RuntimeError(f"{source_id} returned no current target-role job")
    listing_host = (urlsplit(source.require_text("url")).hostname or "").lower()
    agency = str(source.options.get("agency_name", "")).strip()
    for job in result.jobs:
        apply_host = (urlsplit(job.apply_url).hostname or "").lower()
        source_host = (urlsplit(job.source_url).hostname or "").lower()
        if listing_host not in {apply_host, source_host}:
            raise RuntimeError(
                f"{source_id} returned an unexpected job host: {job.apply_url}"
            )
        if not job.title or not job.company or not job.location:
            raise RuntimeError(
                f"{source_id} returned incomplete fields: "
                f"title={job.title!r}, company={job.company!r}, "
                f"location={job.location!r}, url={job.apply_url!r}"
            )
        if job.agency_name != agency:
            raise RuntimeError(
                f"{source_id} lost recruiter identity for {job.title!r}: "
                f"{job.agency_name!r} != {agency!r}"
            )
        if job.company != "Undisclosed client":
            raise RuntimeError(
                f"{source_id} did not keep end-client separate from agency: "
                f"{job.company!r}"
            )
    return {
        "source_id": source_id,
        "status": "PASS",
        "agency": agency,
        "jobs": len(result.jobs),
        "evidence": len(result.evidence),
        "warnings": result.warnings,
        "sample_titles": [job.title for job in result.jobs[:3]],
        "sample_locations": [job.location for job in result.jobs[:3]],
        "sample_urls": [job.apply_url for job in result.jobs[:3]],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    registry = load_source_registry(root / "config" / "sources.yaml")
    by_id = {source.source_id: source for source in registry.sources}
    proof: list[dict[str, object]] = []
    failures: list[str] = []

    for source_id in SOURCE_IDS:
        try:
            proof.append(_verify_source(source_id, by_id[source_id]))
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            failures.append(f"{source_id}: {message}")
            proof.append({"source_id": source_id, "status": "FAIL", "error": message})

    payload = {
        "status": "FAIL" if failures else "PASS",
        "sources": proof,
        "failures": failures,
    }
    PROOF_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
