from __future__ import annotations

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text, join_nonempty, json_bytes
from .http_client import HttpClient


def collect_greenhouse(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    board_token = spec.require_text("board_token")
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    response = client.get(url, params={"content": "true"})
    payload = response.json()
    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(raw_jobs, list):
        raise ValueError(f"source {spec.source_id!r} returned invalid Greenhouse jobs data")

    max_items = spec.int_option("max_items", 500)
    jobs: list[JobRecord] = []
    for item in raw_jobs[:max_items]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        company = str(item.get("company_name", "")).strip() or spec.company
        if not title or not company:
            continue
        location = ""
        raw_location = item.get("location")
        if isinstance(raw_location, dict):
            location = str(raw_location.get("name", "")).strip()

        metadata: list[str] = []
        for entry in item.get("metadata", []) or []:
            if isinstance(entry, dict):
                metadata.append(
                    join_nonempty((entry.get("name"), entry.get("value")), ": ")
                )
        departments = [
            str(entry.get("name", "")).strip()
            for entry in item.get("departments", []) or []
            if isinstance(entry, dict)
        ]
        offices = [
            str(entry.get("name", "")).strip()
            for entry in item.get("offices", []) or []
            if isinstance(entry, dict)
        ]
        skills_text = join_nonempty((*departments, *offices, *metadata), "; ")
        apply_url = str(item.get("absolute_url", "")).strip()
        jobs.append(
            JobRecord(
                title=title,
                company=company,
                location=location,
                description=html_to_text(str(item.get("content", ""))),
                apply_url=apply_url,
                source_url=apply_url or response.url,
                source_name=spec.name,
                published_at=str(
                    item.get("first_published") or item.get("updated_at") or ""
                ).strip(),
                skills_text=skills_text,
            )
        )

    return CollectionResult(
        jobs=jobs,
        evidence=[
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get("content-type", "application/json"),
                body=json_bytes(payload),
                status_code=response.status_code,
                suffix=".json",
            )
        ],
    )
