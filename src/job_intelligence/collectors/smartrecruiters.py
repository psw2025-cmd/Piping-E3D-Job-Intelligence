from __future__ import annotations

import hashlib
import re
from typing import Any

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text, join_nonempty, json_bytes
from .http_client import HttpClient

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _location(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    location = join_nonempty(
        (value.get("city"), value.get("region"), value.get("country"))
    )
    if value.get("remote"):
        return join_nonempty((location, "Remote"), " / ")
    return location


def _description(detail: dict[str, Any]) -> str:
    job_ad = detail.get("jobAd")
    if not isinstance(job_ad, dict):
        return ""
    sections = job_ad.get("sections")
    if isinstance(sections, dict):
        values = sections.values()
    else:
        values = job_ad.values()
    output: list[str] = []
    for section in values:
        if isinstance(section, dict):
            title = str(section.get("title", "")).strip()
            text = html_to_text(str(section.get("text", "")))
            combined = join_nonempty((title, text), "\n")
        else:
            combined = html_to_text(str(section))
        if combined:
            output.append(combined)
    return "\n\n".join(output)


def _salary(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts = (
        value.get("currency"),
        value.get("min"),
        value.get("max"),
        value.get("period"),
        value.get("description"),
    )
    return join_nonempty(parts, " ")


def _normalized(value: str) -> str:
    return " ".join(_NON_ALNUM.sub(" ", value.lower()).split())


def _title_is_candidate(title: str, include_terms: tuple[str, ...]) -> bool:
    if not include_terms:
        return True
    normalized_title = _normalized(title)
    return any(_normalized(term) in normalized_title for term in include_terms)


def _queries(spec: SourceSpec) -> tuple[str, ...]:
    configured = spec.text_list_option("search_terms")
    return configured or ("",)


def collect_smartrecruiters(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    identifier = spec.require_text("company_identifier")
    list_url = f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"
    max_items = spec.int_option("max_items", 300)
    page_size = min(spec.int_option("page_size", 100), 100)
    fetch_details = spec.bool_option("fetch_details", True)
    include_terms = spec.text_list_option("include_terms")
    default_max_pages = max(4, ((max_items + page_size - 1) // page_size) * 4)
    max_pages = spec.int_option("max_pages", default_max_pages)

    jobs: list[JobRecord] = []
    evidence: list[EvidenceArtifact] = []
    seen_posting_ids: set[str] = set()
    for query in _queries(spec):
        if len(jobs) >= max_items:
            break
        seen_pages: set[str] = set()
        pages_fetched = 0
        offset = 0
        while len(jobs) < max_items:
            if pages_fetched >= max_pages:
                raise ValueError(
                    f"source {spec.source_id!r} query {query!r} "
                    f"exceeded max_pages={max_pages}"
                )
            params: dict[str, object] = {
                "offset": offset,
                "limit": page_size,
                "destination": "PUBLIC",
            }
            if query:
                params["q"] = query
            response = client.get(list_url, params=params)
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(
                    f"source {spec.source_id!r} returned invalid SmartRecruiters data"
                )
            page_bytes = json_bytes(payload)
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
            page_fingerprint = hashlib.sha256(page_bytes).hexdigest()
            if page_fingerprint in seen_pages:
                raise ValueError(
                    f"source {spec.source_id!r} repeated a pagination page "
                    f"for query {query!r}"
                )
            seen_pages.add(page_fingerprint)
            pages_fetched += 1
            raw_postings = payload.get("content", payload.get("postings", []))
            if not isinstance(raw_postings, list):
                raise ValueError(
                    f"source {spec.source_id!r} returned invalid postings list"
                )
            if not raw_postings:
                break

            for summary in raw_postings:
                if len(jobs) >= max_items:
                    break
                if not isinstance(summary, dict):
                    continue
                summary_title = str(summary.get("name", "")).strip()
                posting_id = str(
                    summary.get("id") or summary.get("uuid") or ""
                ).strip()
                identity = posting_id or str(
                    summary.get("postingUrl") or summary.get("ref") or summary_title
                ).strip()
                if not identity or identity in seen_posting_ids:
                    continue
                if not summary_title or not _title_is_candidate(
                    summary_title, include_terms
                ):
                    continue
                seen_posting_ids.add(identity)
                detail = summary
                if fetch_details and posting_id:
                    detail_url = f"{list_url}/{posting_id}"
                    detail_response = client.get(detail_url)
                    detail_payload = detail_response.json()
                    if isinstance(detail_payload, dict):
                        detail = detail_payload
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

                title = str(detail.get("name", summary_title)).strip()
                company_data = detail.get("company", summary.get("company"))
                if isinstance(company_data, dict):
                    company = (
                        str(company_data.get("name", "")).strip() or spec.company
                    )
                else:
                    company = spec.company
                if not title or not company:
                    continue
                apply_url = str(
                    detail.get("applyUrl") or summary.get("applyUrl") or ""
                ).strip()
                posting_url = str(
                    detail.get("postingUrl")
                    or summary.get("postingUrl")
                    or summary.get("ref")
                    or ""
                ).strip()
                employment = detail.get("typeOfEmployment")
                experience = detail.get("experienceLevel")
                department = detail.get("department")
                function = detail.get("function")
                jobs.append(
                    JobRecord(
                        title=title,
                        company=company,
                        location=_location(
                            detail.get("location", summary.get("location"))
                        ),
                        description=_description(detail),
                        apply_url=apply_url or posting_url,
                        source_url=posting_url or response.url,
                        source_name=spec.name,
                        published_at=str(
                            detail.get("releasedDate")
                            or summary.get("releasedDate")
                            or ""
                        ).strip(),
                        job_type=str(
                            employment.get("label", "")
                            if isinstance(employment, dict)
                            else employment or ""
                        ).strip(),
                        salary_text=_salary(detail.get("compensation")),
                        experience_text=str(
                            experience.get("label", "")
                            if isinstance(experience, dict)
                            else experience or ""
                        ).strip(),
                        skills_text=join_nonempty(
                            (
                                department.get("label", "")
                                if isinstance(department, dict)
                                else department,
                                function.get("label", "")
                                if isinstance(function, dict)
                                else function,
                            ),
                            "; ",
                        ),
                    )
                )

            if len(raw_postings) < page_size:
                break
            offset += len(raw_postings)

    return CollectionResult(jobs=jobs, evidence=evidence)
