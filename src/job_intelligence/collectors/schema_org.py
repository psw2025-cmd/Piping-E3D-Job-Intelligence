from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import flatten_json_ld, html_to_text, join_nonempty


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._capturing = False
        self._parts: list[str] = []
        self.documents: list[Any] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attributes = {key.lower(): (value or "") for key, value in attrs}
        script_type = attributes.get("type", "").lower().split(";", 1)[0].strip()
        if script_type == "application/ld+json":
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._capturing:
            return
        raw = "".join(self._parts).strip()
        self._capturing = False
        self._parts = []
        if not raw:
            return
        try:
            self.documents.append(json.loads(raw))
        except json.JSONDecodeError:
            return


def _is_job_posting(value: dict[str, Any]) -> bool:
    raw_type = value.get("@type")
    if isinstance(raw_type, list):
        types = {str(item).lower() for item in raw_type}
    else:
        types = {str(raw_type).lower()}
    return "jobposting" in types


def _organization_name(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        return str(value.get("name", "")).strip() or fallback
    return fallback


def _address_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    address = value.get("address", value)
    if not isinstance(address, dict):
        return str(address).strip()
    return join_nonempty(
        (
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("postalCode"),
            address.get("addressCountry"),
        )
    )


def _job_location(value: dict[str, Any]) -> str:
    raw_locations = value.get("jobLocation")
    if isinstance(raw_locations, list):
        locations = [_address_text(location) for location in raw_locations]
    else:
        locations = [_address_text(raw_locations)]
    if str(value.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        locations.append("Remote")
    return join_nonempty(locations, " / ")


def _salary(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    currency = str(value.get("currency", "")).strip()
    raw_amount = value.get("value")
    if isinstance(raw_amount, dict):
        minimum = raw_amount.get("minValue", raw_amount.get("value"))
        maximum = raw_amount.get("maxValue")
        unit = raw_amount.get("unitText")
    else:
        minimum = raw_amount
        maximum = None
        unit = ""
    if minimum is None and maximum is None:
        return ""
    amount = str(minimum if maximum is None else f"{minimum}–{maximum}")
    return join_nonempty((currency, amount, f"per {unit}" if unit else ""), " ")


def parse_job_postings(html_text: str, page_url: str, spec: SourceSpec) -> list[JobRecord]:
    parser = _JsonLdParser()
    parser.feed(html_text)
    jobs: list[JobRecord] = []
    for document in parser.documents:
        for value in flatten_json_ld(document):
            if not _is_job_posting(value):
                continue
            title = str(value.get("title", "")).strip()
            company = _organization_name(value.get("hiringOrganization"), spec.company)
            if not title or not company:
                continue
            employment = value.get("employmentType")
            if isinstance(employment, list):
                job_type = join_nonempty(employment, "; ")
            else:
                job_type = str(employment or "").strip()
            skills = value.get("skills")
            if isinstance(skills, list):
                skills_text = join_nonempty(skills, "; ")
            else:
                skills_text = html_to_text(str(skills or ""))
            description = html_to_text(str(value.get("description", "")))
            jobs.append(
                JobRecord(
                    title=title,
                    company=company,
                    location=_job_location(value),
                    description=description,
                    apply_url=str(value.get("url") or page_url).strip(),
                    source_url=page_url,
                    source_name=spec.name,
                    published_at=str(value.get("datePosted", "")).strip(),
                    job_type=job_type,
                    salary_text=_salary(value.get("baseSalary")),
                    experience_text=html_to_text(
                        str(value.get("experienceRequirements", ""))
                    ),
                    skills_text=skills_text,
                )
            )
    return jobs
