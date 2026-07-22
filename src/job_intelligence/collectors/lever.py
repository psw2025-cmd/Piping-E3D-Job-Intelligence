from __future__ import annotations

from typing import Any

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import (
    CollectionResult,
    EvidenceArtifact,
    html_to_text,
    join_nonempty,
    json_bytes,
    salary_text_from_range,
)
from .http_client import HttpClient


def _description(item: dict[str, Any]) -> str:
    direct = str(item.get("descriptionPlain", "")).strip()
    if direct:
        return direct
    sections: list[str] = []
    opening = str(item.get("openingPlain", "")).strip()
    if opening:
        sections.append(opening)
    for entry in item.get("lists", []) or []:
        if not isinstance(entry, dict):
            continue
        heading = str(entry.get("text", "")).strip()
        content = html_to_text(str(entry.get("content", "")))
        sections.append(join_nonempty((heading, content), "\n"))
    additional = str(item.get("additionalPlain", "")).strip()
    if additional:
        sections.append(additional)
    if sections:
        return "\n\n".join(section for section in sections if section)
    return html_to_text(str(item.get("description", "")))


def collect_lever(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    site = spec.require_text("site")
    region = str(spec.options.get("region", "global")).strip().lower()
    host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    url = f"https://{host}/v0/postings/{site}"
    max_items = spec.int_option("max_items", 500)
    page_size = min(spec.int_option("page_size", 100), 100)

    jobs: list[JobRecord] = []
    evidence: list[EvidenceArtifact] = []
    skip = 0
    while len(jobs) < max_items:
        limit = min(page_size, max_items - len(jobs))
        response = client.get(
            url,
            params={"mode": "json", "skip": skip, "limit": limit},
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"source {spec.source_id!r} returned invalid Lever data")
        evidence.append(
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get("content-type", "application/json"),
                body=json_bytes(payload),
                status_code=response.status_code,
                suffix=".json",
            )
        )
        if not payload:
            break

        for raw in payload:
            if len(jobs) >= max_items:
                break
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("text", "")).strip()
            if not title:
                continue
            categories = raw.get("categories")
            categories = categories if isinstance(categories, dict) else {}
            all_locations = categories.get("allLocations")
            if isinstance(all_locations, list) and all_locations:
                location = join_nonempty(all_locations)
            else:
                location = str(categories.get("location", "")).strip()
            hosted_url = str(raw.get("hostedUrl", "")).strip()
            apply_url = str(raw.get("applyUrl", "")).strip()
            salary = salary_text_from_range(raw.get("salaryRange"))
            if not salary:
                salary = html_to_text(str(raw.get("salaryDescriptionPlain", "")))
            job_type = join_nonempty(
                (categories.get("commitment"), raw.get("workplaceType")),
                "; ",
            )
            skills = join_nonempty(
                (categories.get("team"), categories.get("department")),
                "; ",
            )
            jobs.append(
                JobRecord(
                    title=title,
                    company=spec.company,
                    location=location,
                    description=_description(raw),
                    apply_url=apply_url or hosted_url,
                    source_url=hosted_url or response.url,
                    source_name=spec.name,
                    job_type=job_type,
                    salary_text=salary,
                    skills_text=skills,
                )
            )

        if len(jobs) >= max_items or len(payload) < limit:
            break
        skip += len(payload)

    return CollectionResult(jobs=jobs, evidence=evidence)
