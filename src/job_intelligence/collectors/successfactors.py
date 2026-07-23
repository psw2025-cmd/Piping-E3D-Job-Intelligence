from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text
from .http_client import HttpClient
from .schema_org import parse_job_postings

_SPACE_RE = re.compile(r"\s+")
_LOCATION_RE = re.compile(r"(?:work location|location)\s*:\s*([^\n]+)", re.IGNORECASE)
_DATE_RE = re.compile(
    r"(?:date posted|posting date|date)\s*:\s*"
    r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_DEFAULT_CLOSED = (
    "job you are trying to apply for has been filled",
    "position is no longer available",
    "job is no longer available",
)


@dataclass(frozen=True, slots=True)
class _Listing:
    url: str
    title: str
    context: str


def _evidence(response) -> EvidenceArtifact:
    return EvidenceArtifact(
        source_url=response.url,
        content_type=response.headers.get("content-type", "text/html"),
        body=response.content,
        status_code=response.status_code,
        suffix=".html",
    )


def _normalized(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def _matches(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return not terms or any(term in lowered for term in terms)


def _listing_context(anchor) -> str:
    for parent_name in ("tr", "li", "article"):
        parent = anchor.find_parent(parent_name)
        if parent:
            return _normalized(parent.get_text(" ", strip=True))
    parent = anchor.parent
    return _normalized(parent.get_text(" ", strip=True)) if parent else ""


def _extract_listings(
    html_text: str,
    page_url: str,
    *,
    host: str,
    link_pattern: str,
    include_terms: tuple[str, ...],
    location_terms: tuple[str, ...],
) -> list[_Listing]:
    soup = BeautifulSoup(html_text, "html.parser")
    listings: list[_Listing] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, str(anchor.get("href", "")).strip())
        parsed = urlsplit(url)
        if parsed.hostname != host or link_pattern not in parsed.path or url in seen:
            continue
        title = _normalized(anchor.get_text(" ", strip=True))
        context = _listing_context(anchor)
        searchable = f"{title} {context}"
        if not title or not _matches(searchable, include_terms):
            continue
        if location_terms and not _matches(searchable, location_terms):
            continue
        seen.add(url)
        listings.append(_Listing(url=url, title=title, context=context))
    return listings


def _detail_job(
    html_text: str,
    page_url: str,
    spec: SourceSpec,
    listing: _Listing,
) -> JobRecord | None:
    structured = parse_job_postings(html_text, page_url, spec)
    if structured:
        return structured[0]
    soup = BeautifulSoup(html_text, "html.parser")
    heading = soup.find("h1")
    title = _normalized(heading.get_text(" ", strip=True)) if heading else listing.title
    if not title:
        return None
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    description = html_to_text(str(main))
    location_match = _LOCATION_RE.search(description)
    date_match = _DATE_RE.search(description)
    return JobRecord(
        title=title,
        company=spec.company,
        location=_normalized(location_match.group(1)) if location_match else "",
        description=description or listing.context,
        apply_url=page_url,
        source_url=page_url,
        source_name=spec.name,
        published_at=_normalized(date_match.group(1)) if date_match else "",
    )


def collect_successfactors(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    template = spec.require_text("page_url_template")
    if "{offset}" not in template:
        raise ValueError(
            f"source {spec.source_id!r} page_url_template must contain '{{offset}}'"
        )
    host = (urlsplit(template.format(offset=0)).hostname or "").lower()
    if not host:
        raise ValueError(f"source {spec.source_id!r} has invalid page_url_template")
    page_size = spec.int_option("page_size", 25)
    max_pages = spec.int_option("max_pages", 20)
    max_items = spec.int_option("max_items", 300)
    link_pattern = str(spec.options.get("job_link_pattern", "/job/")).strip()
    include_terms = spec.text_list_option("include_terms")
    location_terms = spec.text_list_option("location_terms")
    closed_patterns = spec.text_list_option("closed_text_patterns") or _DEFAULT_CLOSED

    evidence: list[EvidenceArtifact] = []
    warnings: list[str] = []
    queued: list[_Listing] = []
    seen: set[str] = set()
    for page_index in range(max_pages):
        page_url = template.format(offset=page_index * page_size)
        response = client.get(page_url)
        evidence.append(_evidence(response))
        page_listings = _extract_listings(
            response.text,
            response.url,
            host=host,
            link_pattern=link_pattern,
            include_terms=include_terms,
            location_terms=location_terms,
        )
        new_count = 0
        for listing in page_listings:
            if listing.url in seen:
                continue
            seen.add(listing.url)
            queued.append(listing)
            new_count += 1
            if len(queued) >= max_items:
                break
        if len(queued) >= max_items or new_count == 0:
            break

    jobs: list[JobRecord] = []
    for listing in queued[:max_items]:
        try:
            response = client.get(listing.url)
        except Exception as exc:
            jobs.append(
                JobRecord(
                    title=listing.title,
                    company=spec.company,
                    description=listing.context,
                    apply_url=listing.url,
                    source_url=listing.url,
                    source_name=spec.name,
                )
            )
            warnings.append(
                f"detail fetch failed; listing retained: {listing.url} "
                f"({type(exc).__name__}: {exc})"
            )
            continue
        evidence.append(_evidence(response))
        lowered = response.text.casefold()
        if any(pattern in lowered for pattern in closed_patterns):
            warnings.append(f"closed vacancy skipped: {listing.url}")
            continue
        job = _detail_job(response.text, response.url, spec, listing)
        if job:
            jobs.append(job)
        else:
            warnings.append(f"unparseable vacancy skipped: {listing.url}")

    return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
