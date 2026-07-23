from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact
from .http_client import HttpClient
from .public_notice import (
    _DEFAULT_EXCLUDE,
    _DEFAULT_INCLUDE,
    _NoticeLink,
    _RobotsCache,
    _allowed_domains,
    _contains_any,
    _extract_document_text,
    _is_allowed,
    _job_from_notice,
    _terms,
)

_SPACE_RE = re.compile(r"\s+")
_TEMPLATE_RE = re.compile(r"`(?P<body>.*?)`", re.DOTALL)
_POST_DATE_RE = re.compile(
    r"(?:post\s+date|posted\s+on)\s*:?\s*"
    r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    re.IGNORECASE,
)
_AUXILIARY_LINK_TERMS = (
    "frequently asked",
    "faq",
    "important instruction",
    "mock test",
    "english newspaper",
    "hindi newspaper",
    "apply online",
)
_GENERIC_LINK_TERMS = (
    "click here",
    "details",
    "download",
    "advertisement",
    "view",
    "brief",
    "apply online",
)
_SEMANTIC_CLASSES = (
    "vacancy-card",
    "job-card",
    "notice-card",
    "opening-card",
    "career-card",
)


def _clean_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def _embedded_soups(html_text: str) -> Iterable[BeautifulSoup]:
    page = BeautifulSoup(html_text, "html.parser")
    yield page
    fragments = 0
    for script in page.find_all("script"):
        body = script.string or script.get_text()
        if "<a" not in body.casefold():
            continue
        if len(body) > 5_000_000:
            continue
        for match in _TEMPLATE_RE.finditer(body):
            fragment = match.group("body")
            if "<a" not in fragment.casefold() or len(fragment) > 2_000_000:
                continue
            yield BeautifulSoup(fragment, "html.parser")
            fragments += 1
            if fragments >= 50:
                return


def _semantic_container(anchor: Tag) -> Tag | None:
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        classes = {str(value).casefold() for value in parent.get("class", [])}
        if parent.name in {"tr", "li", "article", "section"}:
            return parent
        if classes.intersection(_SEMANTIC_CLASSES):
            return parent
    return None


def _context(anchor: Tag) -> tuple[str, Tag | None]:
    container = _semantic_container(anchor)
    if container is not None:
        text = _clean_text(container.get_text(" ", strip=True))
        if text:
            return text, container
    for tag_name in ("tr", "li", "article", "section", "div"):
        parent = anchor.find_parent(tag_name)
        if parent is not None:
            text = _clean_text(parent.get_text(" ", strip=True))
            if text:
                return text, parent
    return _clean_text(anchor.get_text(" ", strip=True)), None


def _heading(container: Tag | None) -> str:
    if container is None:
        return ""
    heading = container.find(["h1", "h2", "h3", "h4", "strong"])
    return _clean_text(heading.get_text(" ", strip=True)) if heading else ""


def _title(anchor: Tag, context: str, container: Tag | None) -> str:
    link_text = _clean_text(anchor.get_text(" ", strip=True))
    heading = _heading(container)
    lowered = link_text.casefold()
    if heading and any(term in lowered for term in _GENERIC_LINK_TERMS):
        return heading
    if link_text and len(link_text) >= 8:
        return link_text
    return heading or context[:300].strip()


def _extract_notice_links(
    html_text: str,
    page_url: str,
    spec: SourceSpec,
) -> list[_NoticeLink]:
    domains = _allowed_domains(spec)
    link_patterns = spec.text_list_option("notice_link_patterns")
    include_terms = _terms(spec, "include_notice_terms", _DEFAULT_INCLUDE)
    exclude_terms = _terms(spec, "exclude_notice_terms", _DEFAULT_EXCLUDE)
    include_followups = spec.bool_option("include_followup_notices", False)
    seen: set[str] = set()
    notices: list[_NoticeLink] = []

    for soup in _embedded_soups(html_text):
        for anchor in soup.find_all("a", href=True):
            target = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not target or target in seen or not _is_allowed(target, domains):
                continue
            if link_patterns and not any(
                pattern in target.casefold() for pattern in link_patterns
            ):
                continue
            link_text = _clean_text(anchor.get_text(" ", strip=True))
            if any(term in link_text.casefold() for term in _AUXILIARY_LINK_TERMS):
                continue
            context, container = _context(anchor)
            candidate_text = f"{link_text} {context}".strip()
            if not _contains_any(candidate_text, include_terms):
                continue
            if not include_followups and _contains_any(candidate_text, exclude_terms):
                continue
            title = _title(anchor, context, container)
            if not title:
                continue
            seen.add(target)
            notices.append(_NoticeLink(target, title, context))
    return notices


def collect_public_notice_adaptive(
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
    jobs = []
    warnings: list[str] = []
    for notice in links[:max_items]:
        document_text = ""
        if not robots.can_fetch(notice.url):
            warnings.append(f"notice blocked by robots.txt; listing retained: {notice.url}")
        else:
            try:
                response = client.get(notice.url)
                content_type = response.headers.get(
                    "content-type", "application/octet-stream"
                )
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
        job = _job_from_notice(spec, notice, document_text)
        if not job.published_at:
            match = _POST_DATE_RE.search(f"{notice.context}\n{document_text}")
            if match:
                job.published_at = match.group(1)
        jobs.append(job)
    return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
