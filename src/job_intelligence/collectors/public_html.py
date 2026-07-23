from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup, Tag

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text
from .http_client import DEFAULT_USER_AGENT, HttpClient
from .schema_org import parse_job_postings

_SPACE_RE = re.compile(r"\s+")
_DATE_RE = re.compile(
    r"(?:posting date|date posted|posted|date published)\s*:?\s*(.+)",
    re.IGNORECASE,
)
_CLOSING_DATE_RE = re.compile(
    r"(?:closing date|closing|application deadline|apply by)\s*:?\s*(.+)",
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(
    r"(?:work location|job location|locations?|near location)\s*:?\s*(.+)",
    re.IGNORECASE,
)
_JOB_TYPE_RE = re.compile(
    r"(?:job schedule|employment type|contract type|job type)\s*:?\s*(.+)",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(
    r"(?:salary range|salary|rate|pay)\s*:?\s*(.+)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_GENERIC_TITLES = {
    "apply",
    "apply now",
    "career site",
    "careers",
    "job details",
    "jobs",
    "learn more",
    "oracle careers",
    "read more",
    "view job",
    "view job and apply",
    "view jobs",
}
_METADATA_PREFIXES = (
    "apply",
    "competitive",
    "contract",
    "date published",
    "employment type",
    "experience",
    "full time",
    "job id",
    "job reference",
    "location",
    "part time",
    "permanent",
    "posted",
    "salary",
    "temporary",
    "view job",
)


@dataclass(frozen=True, slots=True)
class _ListingLink:
    url: str
    anchor_text: str
    context_text: str = ""


class _RobotsCache:
    def __init__(
        self,
        client: HttpClient,
        *,
        enabled: bool,
        deny_on_error: bool,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.deny_on_error = deny_on_error
        self.user_agent = getattr(client, "user_agent", DEFAULT_USER_AGENT)
        self.cache: dict[str, RobotFileParser | None] = {}
        self.denied_origins: set[str] = set()

    def can_fetch(self, url: str) -> bool:
        if not self.enabled:
            return True
        parsed = urlsplit(url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        if origin in self.denied_origins:
            return False
        if origin not in self.cache:
            robots_url = f"{origin}/robots.txt"
            try:
                response = self.client.get(robots_url, allowed_statuses={404})
                if response.status_code == 404:
                    self.cache[origin] = None
                else:
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse(response.text.splitlines())
                    self.cache[origin] = parser
            except Exception:
                if self.deny_on_error:
                    self.denied_origins.add(origin)
                    return False
                self.cache[origin] = None
        parser = self.cache[origin]
        return True if parser is None else parser.can_fetch(self.user_agent, url)


def _text_list(value: object, field: str, source_id: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"source {source_id!r} requires non-empty {field!r} list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"source {source_id!r} requires non-empty {field!r} list")
    return result


def _optional_text_list(value: object, field: str, source_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"source {source_id!r} option {field!r} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]


def _allowed_domains(spec: SourceSpec) -> set[str]:
    root_host = (urlsplit(spec.require_text("url")).hostname or "").lower()
    configured = _text_list(
        spec.options.get("allowed_domains", [root_host]),
        "allowed_domains",
        spec.source_id,
    )
    domains = {root_host}
    domains.update(value.lower() for value in configured)
    return domains


def _is_allowed_url(url: str, domains: set[str]) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.hostname.lower() in domains
    )


def _matches_any(value: str, patterns: list[str]) -> bool:
    lowered = value.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _matches_all(value: str, patterns: list[str]) -> bool:
    lowered = value.lower()
    return all(pattern.lower() in lowered for pattern in patterns)


def _matches_anchor_filters(
    filter_text: str,
    include_patterns: list[str],
    required_patterns: list[str],
    exclude_patterns: list[str],
) -> bool:
    if include_patterns and not _matches_any(filter_text, include_patterns):
        return False
    if required_patterns and not _matches_all(filter_text, required_patterns):
        return False
    return not (exclude_patterns and _matches_any(filter_text, exclude_patterns))


def _page_urls(spec: SourceSpec) -> list[str]:
    base_url = spec.require_text("url")
    template = str(spec.options.get("page_url_template", "")).strip()
    max_pages = spec.int_option("max_pages", 1)
    if not template:
        return [base_url]
    if "{page}" not in template:
        raise ValueError(
            f"source {spec.source_id!r} page_url_template must contain '{{page}}'"
        )
    page = spec.int_option("page_start", 0, minimum=0)
    step = spec.int_option("page_step", 1)
    return [template.format(page=page + index * step) for index in range(max_pages)]


def _listing_context(anchor: Tag) -> str:
    anchor_text = _SPACE_RE.sub(" ", anchor.get_text(" ", strip=True)).strip()
    best = anchor_text
    for depth, parent in enumerate(anchor.parents):
        if depth >= 6 or not isinstance(parent, Tag) or parent.name in {"body", "html"}:
            break
        text = _SPACE_RE.sub(" ", parent.get_text(" ", strip=True)).strip()
        if not text or len(text) > 10_000:
            continue
        if len(text) >= len(best):
            best = text
        lowered = text.lower()
        if (
            len(text) <= 6_000
            and any(
                marker in lowered
                for marker in (
                    "date published",
                    "employment type",
                    "job id",
                    "job reference",
                    "posted",
                    "salary",
                    "location",
                )
            )
        ):
            return text
    return best


def _extract_listing_links(
    html_text: str,
    page_url: str,
    domains: set[str],
    link_patterns: list[str],
    anchor_include_patterns: list[str],
    anchor_required_patterns: list[str],
    anchor_exclude_patterns: list[str],
) -> list[_ListingLink]:
    soup = BeautifulSoup(html_text, "html.parser")
    found: list[_ListingLink] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        target = urljoin(page_url, str(anchor.get("href", "")).strip())
        anchor_text = _SPACE_RE.sub(" ", anchor.get_text(" ", strip=True)).strip()
        context_text = _listing_context(anchor)
        filter_text = f"{anchor_text} {context_text}".strip()
        if (
            not target
            or target in seen
            or not _is_allowed_url(target, domains)
            or not _matches_any(target, link_patterns)
            or not _matches_anchor_filters(
                filter_text,
                anchor_include_patterns,
                anchor_required_patterns,
                anchor_exclude_patterns,
            )
        ):
            continue
        seen.add(target)
        found.append(
            _ListingLink(
                url=target,
                anchor_text=anchor_text,
                context_text=context_text,
            )
        )
    return found


def _first_match(pattern: re.Pattern[str], lines: list[str]) -> str:
    for line in lines:
        match = pattern.search(line)
        if match:
            return _SPACE_RE.sub(" ", match.group(1)).strip(" :-")
    return ""


def _meta_content(soup: BeautifulSoup, *selectors: tuple[str, str]) -> str:
    for attribute, value in selectors:
        element = soup.find("meta", attrs={attribute: value})
        if element and element.get("content"):
            return str(element.get("content")).strip()
    return ""


def _clean_document_text(soup: BeautifulSoup) -> str:
    for element in soup(["script", "style", "noscript", "svg", "form"]):
        element.decompose()
    for selector in ("nav", "header", "footer"):
        for element in soup.select(selector):
            element.decompose()
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    return html_to_text(str(main))


def _context_lines(value: str) -> list[str]:
    return [
        _SPACE_RE.sub(" ", line).strip(" -:|")
        for line in re.split(r"[\r\n]+", value)
        if _SPACE_RE.sub(" ", line).strip(" -:|")
    ]


def _listing_title(
    listing_text: str,
    *,
    include_patterns: list[str] | None = None,
) -> str:
    split_title = re.split(
        r"\bJob ID\s*:",
        listing_text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    if split_title and len(split_title) <= 200 and split_title.lower() not in _GENERIC_TITLES:
        if not include_patterns or _matches_any(split_title, include_patterns):
            return split_title

    patterns = include_patterns or []
    for line in _context_lines(listing_text):
        lowered = line.lower()
        if (
            4 <= len(line) <= 200
            and lowered not in _GENERIC_TITLES
            and not lowered.startswith(_METADATA_PREFIXES)
            and (not patterns or _matches_any(line, patterns))
        ):
            return line
    return ""


def _listing_location(listing_text: str) -> str:
    lines = _context_lines(listing_text)
    labeled = _first_match(_LOCATION_RE, lines)
    if labeled:
        return labeled
    match = re.search(
        r"Job ID\s*:\s*#?\S+\s+(.+?)\s+"
        r"(?:Full Time|Part Time|Contract|Temporary)$",
        listing_text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _source_metadata(job: JobRecord, spec: SourceSpec, page_url: str) -> JobRecord:
    agency_name = str(spec.options.get("agency_name", "")).strip()
    if agency_name:
        job.agency_name = agency_name
        if (
            spec.bool_option("replace_agency_company", False)
            and job.company.strip().lower() == agency_name.lower()
        ):
            job.company = spec.company
    for address in _EMAIL_RE.findall(job.description):
        lowered = address.lower()
        if any(term in lowered for term in ("noreply", "no-reply", "donotreply")):
            continue
        job.recruiter_email = lowered
        job.contact_source_url = page_url
        job.contact_confidence = "PUBLIC_UNVERIFIED"
        break
    return job


def _listing_job(link: _ListingLink, spec: SourceSpec) -> JobRecord | None:
    listing_text = link.context_text or link.anchor_text
    include_patterns = _optional_text_list(
        spec.options.get("anchor_text_patterns"),
        "anchor_text_patterns",
        spec.source_id,
    )
    title = _listing_title(link.anchor_text, include_patterns=include_patterns)
    if not title:
        title = _listing_title(listing_text, include_patterns=include_patterns)
    if not title:
        return None
    job_type = ""
    for candidate in ("Full Time", "Part Time", "Contract", "Temporary", "Permanent"):
        if re.search(rf"\b{re.escape(candidate)}\b", listing_text, re.IGNORECASE):
            job_type = candidate
            break
    return _source_metadata(
        JobRecord(
            title=title,
            company=spec.company,
            location=_listing_location(listing_text),
            description=listing_text,
            apply_url=link.url,
            source_url=link.url,
            source_name=spec.name,
            job_type=job_type,
            employment_type=job_type,
        ),
        spec,
        link.url,
    )


def _fallback_job(
    html_text: str,
    page_url: str,
    spec: SourceSpec,
    listing_text: str,
) -> JobRecord | None:
    soup = BeautifulSoup(html_text, "html.parser")
    heading = soup.find("h1")
    title = heading.get_text(" ", strip=True) if heading else ""
    if not title:
        title = _meta_content(
            soup,
            ("property", "og:title"),
            ("name", "twitter:title"),
        )
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    title = re.sub(
        r"\s+(?:job details|careers|career site).*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    if title.lower() in _GENERIC_TITLES:
        title = ""
    title = title or _listing_title(listing_text)
    if not title:
        return None

    description = _clean_document_text(soup) or listing_text
    lines = [line.strip() for line in description.splitlines() if line.strip()]
    location = _first_match(_LOCATION_RE, lines) or _listing_location(listing_text)
    published_at = _first_match(_DATE_RE, lines)
    closing_at = _first_match(_CLOSING_DATE_RE, lines)
    job_type = _first_match(_JOB_TYPE_RE, lines)
    salary_text = _first_match(_SALARY_RE, lines)
    if not job_type:
        for candidate in ("Full Time", "Part Time", "Contract", "Temporary", "Permanent"):
            if re.search(rf"\b{re.escape(candidate)}\b", listing_text, re.IGNORECASE):
                job_type = candidate
                break

    return _source_metadata(
        JobRecord(
            title=_SPACE_RE.sub(" ", title),
            company=spec.company,
            location=location,
            description=description,
            apply_url=page_url,
            source_url=page_url,
            source_name=spec.name,
            published_at=published_at,
            closing_at=closing_at,
            job_type=job_type,
            employment_type=job_type,
            salary_text=salary_text,
        ),
        spec,
        page_url,
    )


def _parse_detail(
    html_text: str,
    page_url: str,
    spec: SourceSpec,
    listing_text: str,
) -> list[JobRecord]:
    jobs = parse_job_postings(html_text, page_url, spec)
    if jobs:
        return [_source_metadata(job, spec, page_url) for job in jobs]
    fallback = _fallback_job(html_text, page_url, spec, listing_text)
    return [fallback] if fallback else []


def collect_public_html(
    spec: SourceSpec,
    client: HttpClient,
    *,
    respect_robots_txt: bool = True,
) -> CollectionResult:
    domains = _allowed_domains(spec)
    link_patterns = _text_list(
        spec.options.get("job_link_patterns", []),
        "job_link_patterns",
        spec.source_id,
    )
    anchor_include_patterns = _optional_text_list(
        spec.options.get("anchor_text_patterns"),
        "anchor_text_patterns",
        spec.source_id,
    )
    anchor_required_patterns = _optional_text_list(
        spec.options.get("required_anchor_text_patterns"),
        "required_anchor_text_patterns",
        spec.source_id,
    )
    anchor_exclude_patterns = _optional_text_list(
        spec.options.get("exclude_anchor_text_patterns"),
        "exclude_anchor_text_patterns",
        spec.source_id,
    )
    max_items = spec.int_option("max_items", 100)
    fetch_details = spec.bool_option("fetch_details", True)
    robots = _RobotsCache(
        client,
        enabled=respect_robots_txt,
        deny_on_error=spec.bool_option("deny_on_robots_error", True),
    )

    evidence: list[EvidenceArtifact] = []
    warnings: list[str] = []
    links: deque[_ListingLink] = deque()
    seen_links: set[str] = set()
    for page_url in _page_urls(spec):
        if not _is_allowed_url(page_url, domains):
            raise ValueError(
                f"source {spec.source_id!r} generated page outside allowed domains"
            )
        if not robots.can_fetch(page_url):
            warnings.append(f"listing blocked by robots.txt: {page_url}")
            continue
        response = client.get(page_url)
        evidence.append(
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get("content-type", "text/html"),
                body=response.content,
                status_code=response.status_code,
                suffix=".html",
            )
        )
        page_links = _extract_listing_links(
            response.text,
            response.url,
            domains,
            link_patterns,
            anchor_include_patterns,
            anchor_required_patterns,
            anchor_exclude_patterns,
        )
        for link in page_links:
            if link.url in seen_links:
                continue
            seen_links.add(link.url)
            links.append(link)
            if len(links) >= max_items:
                break
        if len(links) >= max_items:
            break

    jobs: list[JobRecord] = []
    while links and len(jobs) < max_items:
        link = links.popleft()
        listing_job = _listing_job(link, spec)
        if not fetch_details:
            if listing_job:
                jobs.append(listing_job)
            continue
        if not robots.can_fetch(link.url):
            if listing_job:
                jobs.append(listing_job)
            warnings.append(f"detail blocked by robots.txt; listing retained: {link.url}")
            continue
        try:
            response = client.get(link.url)
        except Exception as exc:
            if listing_job:
                jobs.append(listing_job)
            warnings.append(
                "detail fetch failed; listing retained: "
                f"{link.url} ({type(exc).__name__}: {exc})"
            )
            continue
        evidence.append(
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get("content-type", "text/html"),
                body=response.content,
                status_code=response.status_code,
                suffix=".html",
            )
        )
        remaining = max_items - len(jobs)
        detail_jobs = _parse_detail(
            response.text,
            response.url,
            spec,
            link.context_text or link.anchor_text,
        )
        if detail_jobs:
            jobs.extend(detail_jobs[:remaining])
        elif listing_job:
            jobs.append(listing_job)
            warnings.append(f"detail page unparseable; listing retained: {link.url}")

    return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
