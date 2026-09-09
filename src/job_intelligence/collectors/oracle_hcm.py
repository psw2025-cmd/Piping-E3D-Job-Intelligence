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


def _optional_nonnegative_int(wrapper: dict[str, Any], field: str) -> int | None:
    value = wrapper.get(field)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Oracle HCM response {field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Oracle HCM response {field} must be a non-negative integer"
        ) from exc
    if parsed < 0:
        raise ValueError(f"Oracle HCM response {field} must be a non-negative integer")
    return parsed


def _requisition_rows(
    payload: Any,
) -> tuple[list[dict[str, Any]], int | None, int | None, int | None]:
    if not isinstance(payload, dict):
        raise ValueError("Oracle HCM response root must be a mapping")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Oracle HCM response items must be a list")

    rows: list[dict[str, Any]] = []
    total_jobs: int | None = None
    response_limit: int | None = None
    response_offset: int | None = None
    for raw_wrapper in raw_items:
        wrapper = _mapping(raw_wrapper)
        wrapper_total = _optional_nonnegative_int(wrapper, "TotalJobsCount")
        wrapper_limit = _optional_nonnegative_int(wrapper, "Limit")
        wrapper_offset = _optional_nonnegative_int(wrapper, "Offset")
        if total_jobs is not None and wrapper_total not in {None, total_jobs}:
            raise ValueError("Oracle HCM response has contradictory TotalJobsCount values")
        if response_limit is not None and wrapper_limit not in {None, response_limit}:
            raise ValueError("Oracle HCM response has contradictory Limit values")
        if response_offset is not None and wrapper_offset not in {None, response_offset}:
            raise ValueError("Oracle HCM response has contradictory Offset values")
        total_jobs = wrapper_total if wrapper_total is not None else total_jobs
        response_limit = wrapper_limit if wrapper_limit is not None else response_limit
        response_offset = wrapper_offset if wrapper_offset is not None else response_offset
        raw_rows = wrapper.get("requisitionList", [])
        if not isinstance(raw_rows, list):
            raise ValueError("Oracle HCM requisitionList must be a list")
        rows.extend(_mapping(row) for row in raw_rows if isinstance(row, dict))
    return rows, total_jobs, response_limit, response_offset


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
    searchable = f"{title} {location} {description} {skills_text}".lower()
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
                "finder": (
                    f"findReqs;siteNumber={site_number},"
                    "sortBy=POSTING_DATES_DESC,"
                    f"limit={requested},offset={offset}"
                ),
            },
        )
        payload = response.json()
        page_bytes = json_bytes(payload)
        rows, total_jobs, response_limit, response_offset = _requisition_rows(payload)
        if response_offset is not None and response_offset != offset:
            raise ValueError(
                f"source {spec.source_id!r} returned Offset={response_offset} "
                f"for requested offset={offset}"
            )
        if response_limit is not None and (
            response_limit > requested or len(rows) > response_limit
        ):
            raise ValueError(
                f"source {spec.source_id!r} returned contradictory Limit metadata"
            )
        if total_jobs is not None and total_jobs < offset + len(rows):
            raise ValueError(
                f"source {spec.source_id!r} returned contradictory TotalJobsCount"
            )
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
        if (
            (total_jobs is not None and scanned >= total_jobs)
            or len(rows) < requested
        ):
            break

    return CollectionResult(jobs=jobs, evidence=evidence)
