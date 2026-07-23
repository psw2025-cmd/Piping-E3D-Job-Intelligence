from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urljoin

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import (
    CollectionResult,
    EvidenceArtifact,
    html_to_text,
    join_nonempty,
    json_bytes,
)
from .http_client import HttpClient

_RESOURCE_PATH = "/hcmRestApi/resources/11.13.18.05/recruitingCEJobRequisitions"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _requisition_rows(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise ValueError("Oracle HCM response root must be a mapping")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Oracle HCM response items must be a list")

    rows: list[dict[str, Any]] = []
    total_jobs = 0
    for raw_wrapper in raw_items:
        wrapper = _mapping(raw_wrapper)
        try:
            total_jobs = max(total_jobs, int(wrapper.get("TotalJobsCount", 0) or 0))
        except (TypeError, ValueError):
            pass
        raw_rows = wrapper.get("requisitionList", [])
        if not isinstance(raw_rows, list):
            raise ValueError("Oracle HCM requisitionList must be a list")
        rows.extend(_mapping(row) for row in raw_rows if isinstance(row, dict))
    return rows, total_jobs


def _page_fingerprint(rows: list[dict[str, Any]]) -> str:
    identities = [
        _text(row.get("Id"))
        or "|".join(
            (
                _text(row.get("Title")),
                _text(row.get("PrimaryLocation")),
                _text(row.get("PostedDate")),
            )
        )
        for row in rows
    ]
    return hashlib.sha256(json_bytes(identities)).hexdigest()


def _contains_phrase(text: str, term: str) -> bool:
    cleaned = " ".join(term.casefold().split())
    if not cleaned:
        return False
    pattern = re.escape(cleaned).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text.casefold()) is not None


def _matches_terms(text: str, terms: tuple[str, ...]) -> bool:
    return not terms or any(_contains_phrase(text, term) for term in terms)


def _job_from_row(
    spec: SourceSpec,
    base_url: str,
    site_number: str,
    row: dict[str, Any],
) -> JobRecord | None:
    title = _text(row.get("Title"))
    requisition_id = _text(row.get("Id"))
    if not title or not requisition_id:
        return None

    location = _text(row.get("PrimaryLocation"))
    description_parts = (
        html_to_text(_text(row.get("ShortDescriptionStr"))),
        html_to_text(_text(row.get("ExternalResponsibilitiesStr"))),
        html_to_text(_text(row.get("ExternalQualificationsStr"))),
    )
    description = join_nonempty(description_parts, "\n\n")
    skills_text = join_nonempty(
        (row.get("JobFunction", ""), row.get("JobFamily", "")),
        "; ",
    )
    searchable = " ".join((title, location, description, skills_text)).lower()
    include_terms = spec.text_list_option("include_terms")
    location_terms = spec.text_list_option("location_terms")
    if not _matches_terms(searchable, include_terms):
        return None
    if not _matches_terms(location, location_terms):
        return None

    apply_url = urljoin(
        f"{base_url.rstrip('/')}/",
        f"hcmUI/CandidateExperience/en/sites/{site_number}/job/{requisition_id}",
    )
    return JobRecord(
        title=title,
        company=spec.company,
        location=location,
        description=description,
        apply_url=apply_url,
        source_url=apply_url,
        source_name=spec.name,
        published_at=_text(row.get("PostedDate")),
        job_type=join_nonempty(
            (
                row.get("JobType", ""),
                row.get("JobSchedule", ""),
                row.get("WorkerType", ""),
                row.get("WorkplaceType", ""),
            ),
            "; ",
        ),
        experience_text=_text(row.get("StudyLevel")),
        skills_text=skills_text,
    )


def collect_oracle_hcm(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    base_url = spec.require_text("base_url").rstrip("/")
    site_number = spec.require_text("site_number")
    endpoint = f"{base_url}{_RESOURCE_PATH}"
    max_items = spec.int_option("max_items", 200)
    max_scan_items = spec.int_option("max_scan_items", 2500)
    page_size = min(spec.int_option("page_size", 100), 100)
    max_pages = spec.int_option("max_pages", 30)

    jobs: list[JobRecord] = []
    evidence: list[EvidenceArtifact] = []
    seen_pages: set[str] = set()
    scanned = 0
    offset = 0

    while len(jobs) < max_items and scanned < max_scan_items:
        if len(evidence) >= max_pages:
            raise ValueError(
                f"source {spec.source_id!r} exceeded max_pages={max_pages}"
            )
        requested = min(page_size, max_scan_items - scanned)
        response = client.get(
            endpoint,
            params={
                "onlyData": "true",
                "expand": "requisitionList",
                "limit": requested,
                "offset": offset,
                "finder": (
                    f"findReqs;siteNumber={site_number},"
                    "sortBy=POSTING_DATES_DESC"
                ),
            },
        )
        payload = response.json()
        page_bytes = json_bytes(payload)
        rows, total_jobs = _requisition_rows(payload)
        if not rows:
            break
        page_fingerprint = _page_fingerprint(rows)
        if page_fingerprint in seen_pages:
            raise ValueError(
                f"source {spec.source_id!r} repeated a pagination page"
            )
        seen_pages.add(page_fingerprint)
        evidence.append(
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get(
                    "content-type", "application/json"
                ),
                body=page_bytes,
                status_code=response.status_code,
                suffix=".json",
            )
        )

        for row in rows:
            job = _job_from_row(spec, base_url, site_number, row)
            if job is not None:
                jobs.append(job)
                if len(jobs) >= max_items:
                    break
        scanned += len(rows)
        offset += len(rows)
        if (total_jobs and scanned >= total_jobs) or len(rows) < requested:
            break

    return CollectionResult(jobs=jobs, evidence=evidence)
