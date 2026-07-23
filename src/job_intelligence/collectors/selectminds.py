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
_LOCATION_RE = re.compile(r"(?:🔍\s*)?([^\n]+(?:India|United Arab Emirates|Qatar|Oman|Saudi Arabia|Kuwait|Bahrain|Malaysia|Singapore|United Kingdom|Scotland|Australia))", re.IGNORECASE)
_DATE_RE = re.compile(
    r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d+\s+(?:hours?|days?)\s+ago)\s+Post Date",
    re.IGNORECASE,
)
_DEFAULT_CLOSED = (
    "unfortunately this position has been closed",
    "job you are trying to apply for has been filled",
    "position is no longer available",
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


def _context(anchor) -> str:
    for parent_name in ("article", "li", "div"):
        parent = anchor.find_parent(parent_name)
        if not parent:
            continue
        text = _normalized(parent.get_text(" ", strip=True))
        if len(text) >= len(anchor.get_text(" ", strip=True)) and len(text) <= 4000:
            return text
    return _normalized(anchor.parent.get_text(" ", strip=True)) if anchor.parent else ""


def _listings(
    html_text: str,
    page_url: str,
    host: str,
    pattern: str,
    include_terms: tuple[str, ...],
    location_terms: tuple[str, ...],
) -> list[_Listing]:
    soup = BeautifulSoup(html_text, "html.parser")
    output: list[_Listing] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, str(anchor.get("href", "")).strip())
        parsed = urlsplit(url)
        if parsed.hostname != host or pattern not in parsed.path or url in seen:
            continue
        title = _normalized(anchor.get_text(" ", strip=True))
        context = _context(anchor)
        searchable = f"{title} {context}"
        if not title or not _matches(searchable, include_terms):
            continue
        if location_terms and not _matches(searchable, location_terms):
            continue
        seen.add(url)
        output.append(_Listing(url=url, title=title, context=context))
    return output


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


def collect_selectminds(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    listing_urls = [spec.require_text("url")]
    additional = spec.options.get("additional_urls", [])
    if not isinstance(additional, list) or any(
        not isinstance(value, str) or not value.strip() for value in additional
    ):
        raise ValueError(
            f"source {spec.source_id!r} option 'additional_urls' must be a text list"
        )
    listing_urls.extend(value.strip() for value in additional)
    host = (urlsplit(listing_urls[0]).hostname or "").lower()
    pattern = str(spec.options.get("job_link_pattern", "/jobs/")).strip()
    include_terms = spec.text_list_option("include_terms")
    location_terms = spec.text_list_option("location_terms")
    closed_patterns = spec.text_list_option("closed_text_patterns") or _DEFAULT_CLOSED
    max_items = spec.int_option("max_items", 200)

    evidence: list[EvidenceArtifact] = []
    warnings: list[str] = []
    queued: list[_Listing] = []
    seen: set[str] = set()
    for listing_url in listing_urls:
        if (urlsplit(listing_url).hostname or "").lower() != host:
            raise ValueError(f"source {spec.source_id!r} additional URL left source host")
        response = client.get(listing_url)
        evidence.append(_evidence(response))
        for listing in _listings(
            response.text,
            response.url,
            host,
            pattern,
            include_terms,
            location_terms,
        ):
            if listing.url in seen:
                continue
            seen.add(listing.url)
            queued.append(listing)
            if len(queued) >= max_items:
                break
        if len(queued) >= max_items:
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
