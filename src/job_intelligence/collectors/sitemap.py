from __future__ import annotations

from collections import deque
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from defusedxml import ElementTree

from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact
from .http_client import DEFAULT_USER_AGENT, HttpClient
from .schema_org import parse_job_postings


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ElementTree.Element, name: str) -> str:
    for child in element:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _allowed_domains(spec: SourceSpec) -> set[str]:
    root_host = urlsplit(spec.require_text("url")).hostname or ""
    configured = spec.options.get("allowed_domains", [])
    domains = {root_host.lower()}
    if isinstance(configured, list):
        domains.update(str(value).strip().lower() for value in configured if value)
    return domains


def _is_allowed_url(url: str, domains: set[str]) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in domains


def _matches_patterns(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    lowered = url.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


class _RobotsCache:
    def __init__(
        self,
        client: HttpClient,
        *,
        enabled: bool,
        user_agent: str,
        deny_on_error: bool,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.user_agent = user_agent
        self.deny_on_error = deny_on_error
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


def collect_sitemap(
    spec: SourceSpec,
    client: HttpClient,
    *,
    respect_robots_txt: bool = True,
) -> CollectionResult:
    root_url = spec.require_text("url")
    domains = _allowed_domains(spec)
    max_items = spec.int_option("max_items", 300)
    max_sitemaps = spec.int_option("max_sitemaps", 20)
    patterns_value = spec.options.get("job_url_patterns", [])
    patterns = (
        [str(value) for value in patterns_value]
        if isinstance(patterns_value, list)
        else []
    )
    robots = _RobotsCache(
        client,
        enabled=respect_robots_txt,
        user_agent=getattr(client, "user_agent", DEFAULT_USER_AGENT),
        deny_on_error=bool(spec.options.get("deny_on_robots_error", True)),
    )

    evidence: list[EvidenceArtifact] = []
    page_urls: list[str] = []
    sitemap_queue = deque([root_url])
    seen_sitemaps: set[str] = set()

    while sitemap_queue and len(seen_sitemaps) < max_sitemaps:
        sitemap_url = sitemap_queue.popleft()
        if sitemap_url in seen_sitemaps or not _is_allowed_url(sitemap_url, domains):
            continue
        seen_sitemaps.add(sitemap_url)
        response = client.get(sitemap_url)
        evidence.append(
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get("content-type", "application/xml"),
                body=response.content,
                status_code=response.status_code,
                suffix=".xml",
            )
        )
        root = ElementTree.fromstring(response.content)
        root_name = _local_name(root.tag)
        if root_name == "sitemapindex":
            for entry in root:
                if _local_name(entry.tag) != "sitemap":
                    continue
                child_url = _child_text(entry, "loc")
                if child_url and _is_allowed_url(child_url, domains):
                    sitemap_queue.append(child_url)
        elif root_name == "urlset":
            for entry in root:
                if _local_name(entry.tag) != "url":
                    continue
                page_url = _child_text(entry, "loc")
                if (
                    page_url
                    and _is_allowed_url(page_url, domains)
                    and _matches_patterns(page_url, patterns)
                ):
                    page_urls.append(page_url)
                    if len(page_urls) >= max_items:
                        break
        else:
            raise ValueError(
                f"source {spec.source_id!r} returned unsupported sitemap root {root_name!r}"
            )
        if len(page_urls) >= max_items:
            break

    jobs = []
    for page_url in page_urls[:max_items]:
        if len(jobs) >= max_items:
            break
        if not robots.can_fetch(page_url):
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
        remaining = max_items - len(jobs)
        parsed_jobs = parse_job_postings(response.text, response.url, spec)
        jobs.extend(parsed_jobs[:remaining])

    return CollectionResult(jobs=jobs, evidence=evidence)
