from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text
from .http_client import DEFAULT_USER_AGENT, HttpClient

_DEFAULT_INCLUDE = (
    "recruitment",
    "vacancy",
    "vacancies",
    "advertisement",
    "notification",
    "job opening",
    "walk-in",
    "walk in",
    "corrigendum",
    "addendum",
    "extension of deadline",
    "apply online",
)
_DEFAULT_EXCLUDE = (
    "admit card",
    "call letter",
    "scorecard",
    "score card",
    "result",
    "shortlisted",
    "shortlist",
    "selected candidates",
    "selection list",
    "interview schedule",
    "medical examination",
    "document verification",
)
_DATE_VALUE = (
    r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|"
    r"\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{4}|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2},?\s+\d{4})"
)
_CLOSING_RE = re.compile(
    rf"(?:last\s+date|closing\s+date|application\s+closes?|apply\s+(?:by|before)|"
    rf"online\s+application[^\n]{{0,60}}?(?:till|until|up\s+to|closes?\s+on))"
    rf"[^\n]{{0,40}}?({_DATE_VALUE})",
    re.IGNORECASE,
)
_PUBLISHED_RE = re.compile(
    rf"(?:published\s+(?:on|date)|advertisement\s+date|dated?)"
    rf"[^\n]{{0,30}}?({_DATE_VALUE})",
    re.IGNORECASE,
)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class _NoticeLink:
    url: str
    title: str
    context: str


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

    def can_fetch(self, url: str) -> bool:
        if not self.enabled:
            return True
        parsed = urlsplit(url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
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
                    return False
                self.cache[origin] = None
        parser = self.cache[origin]
        return True if parser is None else parser.can_fetch(self.user_agent, url)


def _terms(spec: SourceSpec, key: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    configured = spec.text_list_option(key)
    return configured or defaults


def _allowed_domains(spec: SourceSpec) -> set[str]:
    return {value.lower() for value in spec.text_list_option("allowed_domains")}


def _is_allowed(url: str, domains: set[str]) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.hostname.lower() in domains
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _nearest_context(anchor: Tag) -> str:
    for tag_name in ("tr", "li", "article", "section", "div"):
        parent = anchor.find_parent(tag_name)
        if parent is not None:
            text = _SPACE_RE.sub(" ", parent.get_text(" ", strip=True)).strip()
            if text:
                return text
    return _SPACE_RE.sub(" ", anchor.get_text(" ", strip=True)).strip()


def _anchor_title(anchor: Tag, context: str) -> str:
    text = _SPACE_RE.sub(" ", anchor.get_text(" ", strip=True)).strip()
    generic = {
        "click here",
        "details",
        "download",
        "download advertisement",
        "view",
        "view details",
        "apply online",
    }
    if text.casefold() not in generic and len(text) >= 8:
        return text
    for heading in anchor.find_all_previous(["h1", "h2", "h3", "h4", "strong"], limit=3):
        heading_text = _SPACE_RE.sub(" ", heading.get_text(" ", strip=True)).strip()
        if heading_text and _contains_any(heading_text, _DEFAULT_INCLUDE):
            return heading_text
    return context[:300].strip()


def _extract_notice_links(html_text: str, page_url: str, spec: SourceSpec) -> list[_NoticeLink]:
    soup = BeautifulSoup(html_text, "html.parser")
    domains = _allowed_domains(spec)
    link_patterns = spec.text_list_option("notice_link_patterns")
    include_terms = _terms(spec, "include_notice_terms", _DEFAULT_INCLUDE)
    exclude_terms = _terms(spec, "exclude_notice_terms", _DEFAULT_EXCLUDE)
    include_followups = spec.bool_option("include_followup_notices", False)
    seen: set[str] = set()
    notices: list[_NoticeLink] = []

    for anchor in soup.find_all("a", href=True):
        target = urljoin(page_url, str(anchor.get("href", "")).strip())
        if not target or target in seen or not _is_allowed(target, domains):
            continue
        if link_patterns and not any(pattern in target.casefold() for pattern in link_patterns):
            continue
        context = _nearest_context(anchor)
        candidate_text = f"{anchor.get_text(' ', strip=True)} {context}".strip()
        if not _contains_any(candidate_text, include_terms):
            continue
        if not include_followups and _contains_any(candidate_text, exclude_terms):
            continue
        title = _anchor_title(anchor, context)
        if not title:
            continue
        seen.add(target)
        notices.append(_NoticeLink(target, title, context))
    return notices


def _extract_pdf_text(content: bytes, max_pages: int) -> str:
    reader = PdfReader(BytesIO(content))
    parts: list[str] = []
    for page in list(reader.pages)[:max_pages]:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def _extract_document_text(content: bytes, content_type: str, url: str, max_pages: int) -> str:
    lowered_type = content_type.casefold()
    if "pdf" in lowered_type or urlsplit(url).path.casefold().endswith(".pdf"):
        return _extract_pdf_text(content, max_pages)
    decoded = content.decode("utf-8", errors="replace")
    return html_to_text(decoded)


def _date_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _notice_kind(text: str) -> str:
    lowered = text.casefold()
    if "corrigendum" in lowered:
        return "corrigendum"
    if "addendum" in lowered:
        return "addendum"
    if "extension" in lowered and ("deadline" in lowered or "last date" in lowered):
        return "deadline_extension"
    if "walk-in" in lowered or "walk in" in lowered:
        return "walk_in"
    return "advertisement"


def _job_from_notice(
    spec: SourceSpec,
    notice: _NoticeLink,
    document_text: str,
) -> JobRecord:
    combined = "\n".join(part for part in (notice.context, document_text) if part)
    kind = _notice_kind(f"{notice.title}\n{combined}")
    description = f"Notice kind: {kind}\n{combined}".strip()
    return JobRecord(
        title=notice.title,
        company=spec.company,
        country=str(spec.options.get("country", "India")).strip(),
        location=str(spec.options.get("location", "India")).strip(),
        description=description,
        apply_url=notice.url,
        source_url=notice.url,
        source_name=spec.name,
        published_at=_date_match(_PUBLISHED_RE, combined),
        closing_at=_date_match(_CLOSING_RE, combined),
        job_type="Public recruitment notice",
        employment_type="Public recruitment notice",
        sector=str(spec.options.get("sector", "")).strip(),
    )


def collect_public_notice(
    spec: SourceSpec,
    client: HttpClient,
    *,
    respect_robots_txt: bool = True,
) -> CollectionResult:
    listing_url = spec.require_text("url")
    max_items = spec.int_option("max_items", 100)
    max_pdf_pages = spec.int_option("max_pdf_pages", 40)
    robots = _RobotsCache(
        client,
        enabled=respect_robots_txt,
        deny_on_error=spec.bool_option("deny_on_robots_error", True),
    )
    if not robots.can_fetch(listing_url):
        raise PermissionError(f"listing blocked by robots.txt: {listing_url}")

    listing_response = client.get(listing_url)
    evidence = [
        EvidenceArtifact(
            source_url=listing_response.url,
            content_type=listing_response.headers.get("content-type", "text/html"),
            body=listing_response.content,
            status_code=listing_response.status_code,
            suffix=".html",
        )
    ]
    links = _extract_notice_links(listing_response.text, listing_response.url, spec)
    jobs: list[JobRecord] = []
    warnings: list[str] = []
    for notice in links[:max_items]:
        document_text = ""
        if not robots.can_fetch(notice.url):
            warnings.append(f"notice blocked by robots.txt; listing retained: {notice.url}")
        else:
            try:
                response = client.get(notice.url)
                content_type = response.headers.get("content-type", "application/octet-stream")
                suffix = ".pdf" if "pdf" in content_type.casefold() else ".html"
                evidence.append(
                    EvidenceArtifact(
                        source_url=response.url,
                        content_type=content_type,
                        body=response.content,
                        status_code=response.status_code,
                        suffix=suffix,
                    )
                )
                document_text = _extract_document_text(
                    response.content,
                    content_type,
                    response.url,
                    max_pdf_pages,
                )
            except Exception as exc:
                warnings.append(
                    "notice fetch or parse failed; listing retained: "
                    f"{notice.url} ({type(exc).__name__}: {exc})"
                )
        jobs.append(_job_from_notice(spec, notice, document_text))
    return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
