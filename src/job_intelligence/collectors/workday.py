from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote, urljoin

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


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _search_rows(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise ValueError("Workday search response root must be a mapping")
    raw_rows = payload.get("jobPostings")
    if not isinstance(raw_rows, list):
        raise ValueError("Workday search response jobPostings must be a list")
    rows = [_mapping(row) for row in raw_rows if isinstance(row, dict)]
    try:
        total = int(payload.get("total", 0) or 0)
    except (TypeError, ValueError):
        total = 0
    return rows, total


def _page_fingerprint(rows: list[dict[str, Any]]) -> str:
    identities = [
        _text(row.get("externalPath"))
        or "|".join(
            (
                _text(row.get("title")),
                _text(row.get("locationsText")),
                _text(row.get("postedOn")),
            )
        )
        for row in rows
    ]
    return hashlib.sha256(json_bytes(identities)).hexdigest()


def _matches_terms(text: str, terms: tuple[str, ...]) -> bool:
    return not terms or any(term in text for term in terms)


def _detail_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Workday detail response root must be a mapping")
    info = payload.get("jobPostingInfo")
    if not isinstance(info, dict):
        raise ValueError("Workday detail response requires jobPostingInfo")
    return info


def _candidate_url(
    *,
    base_url: str,
    locale: str,
    site: str,
    external_path: str,
) -> str:
    encoded_locale = quote(locale.strip("/"), safe="-")
    encoded_site = quote(site.strip("/"), safe="_-.")
    return urljoin(
        f"{base_url.rstrip('/')}/",
        f"{encoded_locale}/{encoded_site}{external_path}",
    )


def _job_from_detail(
    spec: SourceSpec,
    *,
    detail: dict[str, Any],
    fallback_row: dict[str, Any],
    candidate_url: str,
) -> JobRecord | None:
    title = _text(detail.get("title")) or _text(fallback_row.get("title"))
    if not title:
        return None
    location = (
        _text(detail.get("location"))
        or _text(detail.get("locationText"))
        or _text(fallback_row.get("locationsText"))
    )
    description = html_to_text(
        _text(detail.get("jobDescription"))
        or _text(detail.get("description"))
    )
    job_req_id = (
        _text(detail.get("jobReqId"))
        or _text(detail.get("jobRequisitionId"))
        or join_nonempty(fallback_row.get("bulletFields", []), "; ")
    )
    searchable = f"{title} {location} {description} {job_req_id}".lower()
    include_terms = spec.text_list_option("include_terms")
    location_terms = spec.text_list_option("location_terms")
    if not _matches_terms(searchable, include_terms):
        return None
    if not _matches_terms(location.lower(), location_terms):
        return None

    apply_url = (
        _text(detail.get("externalUrl"))
        or _text(detail.get("jobPostingUrl"))
        or candidate_url
    )
    return JobRecord(
        title=title,
        company=spec.company,
        location=location,
        description=description,
        apply_url=apply_url,
        source_url=candidate_url,
        source_name=spec.name,
        published_at=(
            _text(detail.get("startDate"))
            or _text(detail.get("postedOn"))
            or _text(fallback_row.get("postedOn"))
        ),
        closing_at=_text(detail.get("endDate")),
        job_type=join_nonempty(
            (
                detail.get("timeType", ""),
                detail.get("remoteType", ""),
                detail.get("workerType", ""),
            ),
            "; ",
        ),
        employment_type=_text(detail.get("timeType")),
        experience_text=job_req_id,
        skills_text=join_nonempty(
            (
                detail.get("jobFamily", ""),
                detail.get("jobCategory", ""),
                job_req_id,
            ),
            "; ",
        ),
    )


def collect_workday(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    base_url = spec.require_text("base_url").rstrip("/")
    tenant = spec.require_text("tenant")
    site = spec.require_text("site")
    locale = _text(spec.options.get("locale", "en-US")) or "en-US"
    endpoint = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"
    search_terms = spec.text_list_option("search_terms")
    include_terms = spec.text_list_option("include_terms")
    location_terms = spec.text_list_option("location_terms")
    del include_terms, location_terms

    max_items = spec.int_option("max_items", 250)
    max_scan_items = spec.int_option("max_scan_items", 3000)
    page_size = min(spec.int_option("page_size", 20), 100)
    max_pages = spec.int_option("max_pages", 40)

    jobs: list[JobRecord] = []
    evidence: list[EvidenceArtifact] = []
    warnings: list[str] = []
    seen_paths: set[str] = set()
    seen_pages: set[str] = set()
    scanned = 0
    search_pages = 0

    for search_term in search_terms:
        offset = 0
        expected_total = 0
        while len(jobs) < max_items and scanned < max_scan_items:
            if search_pages >= max_pages:
                warnings.append(
                    f"Workday scan stopped at configured max_pages={max_pages}"
                )
                return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
            requested = min(page_size, max_scan_items - scanned)
            response = client.post_json(
                endpoint,
                json_body={
                    "appliedFacets": {},
                    "limit": requested,
                    "offset": offset,
                    "searchText": search_term,
                },
            )
            payload = response.json()
            rows, total = _search_rows(payload)
            if offset == 0 and total > 0:
                expected_total = total
            evidence.append(
                EvidenceArtifact(
                    source_url=response.url,
                    content_type=response.headers.get(
                        "content-type", "application/json"
                    ),
                    body=json_bytes(payload),
                    status_code=response.status_code,
                    suffix=".json",
                )
            )
            search_pages += 1
            if not rows:
                break
            fingerprint = hashlib.sha256(
                f"{search_term}|{_page_fingerprint(rows)}".encode()
            ).hexdigest()
            if fingerprint in seen_pages:
                raise ValueError(
                    f"source {spec.source_id!r} repeated Workday pagination page"
                )
            seen_pages.add(fingerprint)

            for row in rows:
                scanned += 1
                external_path = _text(row.get("externalPath"))
                title = _text(row.get("title"))
                preliminary = " ".join(
                    (
                        title,
                        _text(row.get("locationsText")),
                        join_nonempty(row.get("bulletFields", []), "; "),
                    )
                ).lower()
                if not external_path or external_path in seen_paths:
                    continue
                if not _matches_terms(
                    preliminary,
                    spec.text_list_option("include_terms"),
                ):
                    continue
                seen_paths.add(external_path)
                detail_endpoint = f"{base_url}/wday/cxs/{tenant}/{site}{external_path}"
                detail_response = client.get(detail_endpoint)
                detail_payload = detail_response.json()
                evidence.append(
                    EvidenceArtifact(
                        source_url=detail_response.url,
                        content_type=detail_response.headers.get(
                            "content-type", "application/json"
                        ),
                        body=json_bytes(detail_payload),
                        status_code=detail_response.status_code,
                        suffix=".json",
                    )
                )
                candidate_url = _candidate_url(
                    base_url=base_url,
                    locale=locale,
                    site=site,
                    external_path=external_path,
                )
                job = _job_from_detail(
                    spec,
                    detail=_detail_payload(detail_payload),
                    fallback_row=row,
                    candidate_url=candidate_url,
                )
                if job is not None:
                    jobs.append(job)
                    if len(jobs) >= max_items:
                        break

            offset += len(rows)
            if (
                (expected_total and offset >= expected_total)
                or len(rows) < requested
            ):
                break

        if len(jobs) >= max_items or scanned >= max_scan_items:
            break

    return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
