from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text
from .http_client import DEFAULT_USER_AGENT, HttpClient
from .schema_org import parse_job_postings

_SPACE_RE = re.compile(r"\s+")
_LOCATION_RE = re.compile(r"(?:location|country)\s*:?\s*([^\n]+)", re.IGNORECASE)
_DATE_RE = re.compile(
    r"(?:posting date|date posted|published)\s*:?\s*([^\n]+)",
    re.IGNORECASE,
)
_CLOSING_RE = re.compile(r"closing date\s*:?\s*([^\n]+)", re.IGNORECASE)
_GENERIC_LINK_TEXT = {
    "apply",
    "apply now",
    "details",
    "more details",
    "view job",
    "view details",
}


@dataclass(frozen=True, slots=True)
class _CardLink:
    url: str
    link_text: str
    context: str
    title_hint: str = ""


class _RobotsCache:
    def __init__(self, client: HttpClient, deny_on_error: bool) -> None:
        self.client = client
        self.deny_on_error = deny_on_error
        self.user_agent = getattr(client, "user_agent", DEFAULT_USER_AGENT)
        self.cache: dict[str, RobotFileParser | None] = {}
        self.denied_origins: set[str] = set()

    def can_fetch(self, url: str) -> bool:
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


def _normalized(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def _terms(spec: SourceSpec, key: str) -> tuple[str, ...]:
    return spec.text_list_option(key)


def _matches_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return not terms or any(term in lowered for term in terms)


def _heading_text(element) -> str:
    heading = element.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading is None:
        heading = element.find("strong")
    if heading is None:
        return ""
    value = _normalized(heading.get_text(" ", strip=True))
    if value.casefold() in _GENERIC_LINK_TEXT or len(value) > 180:
        return ""
    return value


def _card_context(anchor, include_terms: tuple[str, ...]) -> tuple[str, str]:
    element = anchor
    fallback = _normalized(anchor.get_text(" ", strip=True))
    fallback_title = ""
    for _ in range(8):
        element = element.parent
        if element is None:
            break
        text = _normalized(element.get_text(" ", strip=True))
        if not text:
            continue
        title_hint = _heading_text(element)
        if len(text) <= 6000:
            fallback = text
            if title_hint:
                fallback_title = title_hint
        if _matches_any(text, include_terms) and len(text) <= 6000:
            return text, title_hint or fallback_title
    return fallback, fallback_title


def _allowed_hosts(spec: SourceSpec) -> set[str]:
    values = spec.options.get("allowed_domains", [])
    if not isinstance(values, list) or not values:
        raise ValueError(
            f"source {spec.source_id!r} requires non-empty allowed_domains"
        )
    hosts = {
        str(value).strip().casefold()
        for value in values
        if isinstance(value, str) and value.strip()
    }
    root = (urlsplit(spec.require_text("url")).hostname or "").casefold()
    if root not in hosts:
        raise ValueError(
            f"source {spec.source_id!r} allowed_domains must include listing host"
        )
    return hosts


def _listing_urls(spec: SourceSpec) -> list[str]:
    base = spec.require_text("url")
    template = str(spec.options.get("page_url_template", "")).strip()
    if not template:
        return [base]
    if "{page}" not in template:
        raise ValueError(
            f"source {spec.source_id!r} page_url_template must contain '{{page}}'"
        )
    start = spec.int_option("page_start", 0, minimum=0)
    step = spec.int_option("page_step", 1)
    maximum = spec.int_option("max_pages", 1)
    return [template.format(page=start + index * step) for index in range(maximum)]


def _extract_cards(
    html_text: str,
    page_url: str,
    spec: SourceSpec,
    allowed_hosts: set[str],
) -> list[_CardLink]:
    soup = BeautifulSoup(html_text, "html.parser")
    link_patterns = _terms(spec, "job_link_patterns")
    include_terms = _terms(spec, "include_terms")
    location_terms = _terms(spec, "location_terms")
    exclude_terms = _terms(spec, "exclude_terms")
    output: list[_CardLink] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        target = urljoin(page_url, str(anchor.get("href", "")).strip())
        parsed = urlsplit(target)
        if (
            not parsed.hostname
            or parsed.hostname.casefold() not in allowed_hosts
            or target in seen
            or not any(pattern in target.casefold() for pattern in link_patterns)
        ):
            continue
        link_text = _normalized(anchor.get_text(" ", strip=True))
        context, title_hint = _card_context(anchor, include_terms)
        if not _matches_any(context, include_terms):
            continue
        if location_terms and not _matches_any(context, location_terms):
            continue
        if exclude_terms and _matches_any(context, exclude_terms):
            continue
        seen.add(target)
        output.append(_CardLink(target, link_text, context, title_hint))
    return output


def _guess_title(card: _CardLink) -> str:
    if card.title_hint:
        return card.title_hint
    if card.link_text.casefold() not in _GENERIC_LINK_TEXT:
        return card.link_text
    cleaned = card.context
    for generic in sorted(_GENERIC_LINK_TEXT, key=len, reverse=True):
        cleaned = re.sub(re.escape(generic), " ", cleaned, flags=re.IGNORECASE)
    cleaned = _normalized(cleaned)
    if cleaned and len(cleaned) <= 180:
        return cleaned
    return ""


def _fallback_job(
    html_text: str,
    page_url: str,
    spec: SourceSpec,
    card: _CardLink,
) -> JobRecord | None:
    soup = BeautifulSoup(html_text, "html.parser")
    heading = soup.find("h1")
    title = _normalized(heading.get_text(" ", strip=True)) if heading else ""
    title = title or _guess_title(card)
    if not title:
        return None
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    description = html_to_text(str(main)) or card.context
    location_match = _LOCATION_RE.search(description)
    date_match = _DATE_RE.search(description)
    closing_match = _CLOSING_RE.search(description)
    if closing_match:
        description = f"{description}\nClosing date: {closing_match.group(1).strip()}"
    return JobRecord(
        title=title,
        company=spec.company,
        location=_normalized(location_match.group(1)) if location_match else "",
        description=description,
        apply_url=page_url,
        source_url=page_url,
        source_name=spec.name,
        published_at=_normalized(date_match.group(1)) if date_match else "",
    )


def collect_card_html(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    allowed_hosts = _allowed_hosts(spec)
    max_items = spec.int_option("max_items", 200)
    closed_patterns = _terms(spec, "closed_text_patterns")
    robots = _RobotsCache(
        client,
        deny_on_error=spec.bool_option("deny_on_robots_error", True),
    )
    evidence: list[EvidenceArtifact] = []
    warnings: list[str] = []
    cards: list[_CardLink] = []
    seen: set[str] = set()

    for listing_url in _listing_urls(spec):
        parsed = urlsplit(listing_url)
        if not parsed.hostname or parsed.hostname.casefold() not in allowed_hosts:
            raise ValueError(
                f"source {spec.source_id!r} generated listing outside allowlist"
            )
        if not robots.can_fetch(listing_url):
            warnings.append(f"listing blocked by robots.txt: {listing_url}")
            continue
        response = client.get(listing_url)
        evidence.append(
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get("content-type", "text/html"),
                body=response.content,
                status_code=response.status_code,
                suffix=".html",
            )
        )
        for card in _extract_cards(response.text, response.url, spec, allowed_hosts):
            if card.url in seen:
                continue
            seen.add(card.url)
            cards.append(card)
            if len(cards) >= max_items:
                break
        if len(cards) >= max_items:
            break

    jobs: list[JobRecord] = []
    for card in cards[:max_items]:
        if not robots.can_fetch(card.url):
            warnings.append(f"detail blocked by robots.txt: {card.url}")
            continue
        try:
            response = client.get(card.url)
        except Exception as exc:
            title = _guess_title(card)
            if title:
                jobs.append(
                    JobRecord(
                        title=title,
                        company=spec.company,
                        description=card.context,
                        apply_url=card.url,
                        source_url=card.url,
                        source_name=spec.name,
                    )
                )
            warnings.append(
                f"detail fetch failed: {card.url} ({type(exc).__name__}: {exc})"
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
        lowered = response.text.casefold()
        if any(pattern in lowered for pattern in closed_patterns):
            warnings.append(f"closed vacancy skipped: {card.url}")
            continue
        parsed_jobs = parse_job_postings(response.text, response.url, spec)
        job = parsed_jobs[0] if parsed_jobs else _fallback_job(
            response.text,
            response.url,
            spec,
            card,
        )
        if job:
            jobs.append(job)
        else:
            warnings.append(f"unparseable vacancy skipped: {card.url}")

    return CollectionResult(jobs=jobs, evidence=evidence, warnings=warnings)
