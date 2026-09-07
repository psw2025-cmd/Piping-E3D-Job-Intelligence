from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import yaml
from bs4 import BeautifulSoup
from defusedxml import ElementTree

from .collectors import COLLECTORS
from .collectors.http_client import DEFAULT_USER_AGENT, SafeHttpClient
from .collectors.schema_org import parse_job_postings
from .source_config import SourceSpec, load_source_config

LOGGER = logging.getLogger(__name__)

PIPING_TERMS = [
    "piping",
    "pipe layout",
    "plant layout",
    "plant design",
    "e3d",
    "aveva e3d",
    "pdms",
    "sp3d",
    "smart 3d",
    "smartplant 3d",
    "pipe support",
    "piping stress",
    "piping materials",
    "3d model",
]

KNOWN_ATS_HOST_TOKENS = (
    "greenhouse.io",
    "lever.co",
    "smartrecruiters.com",
    "myworkdayjobs.com",
    "oraclecloud.com",
)

JOB_URL_HINTS = ("/job/", "/jobs/", "/career/", "/careers/", "jobid=", "job_id=")


@dataclass(slots=True)
class DiscoveryRecord:
    company: str
    platform: str
    evidence_url: str
    source: dict[str, Any]
    confidence: str = "candidate"
    probe_status: str = "not_probed"
    probe_jobs: int = 0
    error: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "source")[:44]


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _path_parts(url: str) -> list[str]:
    return [part for part in urlsplit(url).path.split("/") if part]


def _source_id(company: str, suffix: str, identity: str = "") -> str:
    base = f"auto-{slugify(company)}-{suffix}"
    if not identity:
        return base[:64].rstrip("-")
    digest = hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()[:10]
    return f"{base[:53].rstrip('-')}-{digest}"


def detect_source(company: str, url: str) -> DiscoveryRecord | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    parts = _path_parts(url)
    if not host:
        return None

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        token = parts[0]
        return DiscoveryRecord(
            company=company,
            platform="greenhouse",
            evidence_url=url,
            source={
                "id": _source_id(company, "greenhouse", f"{host}:{token}"),
                "name": f"{company} official Greenhouse board",
                "type": "greenhouse",
                "company": company,
                "board_token": token,
                "enabled": True,
                "profile_filter": True,
                "timeout_seconds": 30,
                "rate_limit_per_minute": 20,
                "max_items": 500,
            },
        )

    if host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        site = parts[0]
        return DiscoveryRecord(
            company=company,
            platform="lever",
            evidence_url=url,
            source={
                "id": _source_id(company, "lever", f"{host}:{site}"),
                "name": f"{company} official Lever board",
                "type": "lever",
                "company": company,
                "site": site,
                "region": "eu" if host.startswith("jobs.eu.") else "global",
                "enabled": True,
                "profile_filter": True,
                "timeout_seconds": 30,
                "rate_limit_per_minute": 20,
                "max_items": 500,
                "page_size": 100,
            },
        )

    if host == "jobs.smartrecruiters.com" and parts:
        identifier = parts[0]
        return DiscoveryRecord(
            company=company,
            platform="smartrecruiters",
            evidence_url=url,
            source={
                "id": _source_id(company, "smartrecruiters", identifier),
                "name": f"{company} official SmartRecruiters postings",
                "type": "smartrecruiters",
                "company": company,
                "company_identifier": identifier,
                "enabled": True,
                "profile_filter": True,
                "fetch_details": True,
                "timeout_seconds": 30,
                "rate_limit_per_minute": 20,
                "max_items": 400,
                "page_size": 100,
                "max_pages": 20,
            },
        )

    if host == "api.smartrecruiters.com":
        match = re.search(r"/v1/companies/([^/]+)/postings", parsed.path)
        if match:
            identifier = match.group(1)
            return detect_source(company, f"https://jobs.smartrecruiters.com/{identifier}/")

    if host.endswith(".myworkdayjobs.com") and parts:
        locale = "en-US"
        site_index = 0
        if re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", parts[0]):
            locale = parts[0]
            site_index = 1
        if len(parts) > site_index:
            tenant = host.split(".", 1)[0]
            site = parts[site_index]
            return DiscoveryRecord(
                company=company,
                platform="workday",
                evidence_url=url,
                source={
                    "id": _source_id(company, "workday", f"{host}:{tenant}:{site}"),
                    "name": f"{company} official Workday careers",
                    "type": "workday",
                    "company": company,
                    "base_url": f"https://{host}",
                    "tenant": tenant,
                    "site": site,
                    "locale": locale,
                    "search_terms": ["piping", "e3d", "pdms", "sp3d", "plant layout"],
                    "include_terms": PIPING_TERMS,
                    "location_terms": [],
                    "enabled": True,
                    "profile_filter": True,
                    "timeout_seconds": 30,
                    "rate_limit_per_minute": 20,
                    "max_response_bytes": 5_000_000,
                    "max_items": 300,
                    "max_scan_items": 3000,
                    "max_pages": 40,
                    "page_size": 20,
                    "max_redirects": 3,
                    "pagination_repeat_action": "stop_search_term",
                },
            )

    if host.endswith(".oraclecloud.com"):
        match = re.search(r"/sites/([^/?#]+)", parsed.path)
        if match:
            return DiscoveryRecord(
                company=company,
                platform="oracle_hcm",
                evidence_url=url,
                source={
                    "id": _source_id(company, "oracle", f"{host}:{match.group(1)}"),
                    "name": f"{company} official Oracle HCM careers",
                    "type": "oracle_hcm",
                    "company": company,
                    "base_url": f"https://{host}",
                    "site_number": match.group(1),
                    "include_terms": PIPING_TERMS,
                    "location_terms": [],
                    "enabled": True,
                    "profile_filter": True,
                    "timeout_seconds": 30,
                    "rate_limit_per_minute": 30,
                    "max_response_bytes": 5_000_000,
                    "max_items": 300,
                    "max_scan_items": 5000,
                    "max_pages": 50,
                    "page_size": 100,
                },
            )

    return None


def extract_candidate_urls(html: str, base_url: str, limit: int = 120) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    output: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor.get("href", "")).strip())
        parsed = urlsplit(absolute)
        host = (parsed.hostname or "").lower()
        lowered = absolute.lower()
        if parsed.scheme not in {"http", "https"}:
            continue
        if not (
            any(token in host for token in KNOWN_ATS_HOST_TOKENS)
            or any(hint in lowered for hint in JOB_URL_HINTS)
        ):
            continue
        normalized = absolute.split("#", 1)[0]
        if normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _source_identity(source: dict[str, Any]) -> tuple[str, str]:
    source_type = str(source.get("type", ""))
    if source_type == "greenhouse":
        key = str(source.get("board_token", ""))
    elif source_type == "lever":
        key = f"{source.get('region', 'global')}:{source.get('site', '')}"
    elif source_type == "smartrecruiters":
        key = str(source.get("company_identifier", ""))
    elif source_type == "workday":
        key = f"{source.get('base_url', '')}:{source.get('tenant', '')}:{source.get('site', '')}"
    elif source_type == "oracle_hcm":
        key = f"{source.get('base_url', '')}:{source.get('site_number', '')}"
    elif source_type == "sitemap":
        key = str(source.get("url", ""))
    else:
        key = str(source.get("url", source.get("id", "")))
    return source_type, key.lower()


def _spec_from_mapping(source: dict[str, Any]) -> SourceSpec:
    return SourceSpec(
        source_id=str(source["id"]),
        name=str(source["name"]),
        source_type=str(source["type"]),
        enabled=bool(source.get("enabled", True)),
        company=str(source["company"]),
        options={
            key: value
            for key, value in source.items()
            if key not in {"id", "name", "type", "enabled", "company"}
        },
    )


def probe_record(record: DiscoveryRecord) -> DiscoveryRecord:
    try:
        spec = _spec_from_mapping(record.source)
        client = SafeHttpClient(
            timeout_seconds=10,
            max_response_bytes=5_000_000,
            rate_limit_per_minute=30,
            max_redirects=3,
        )
        result = COLLECTORS[spec.source_type](spec, client)
        record.probe_status = "pass"
        record.probe_jobs = len(result.jobs)
        record.confidence = "verified_public_connector"
    except Exception as exc:
        record.probe_status = "fail"
        record.error = f"{type(exc).__name__}: {exc}"
        record.source["enabled"] = False
        record.confidence = "detected_unverified"
    return record


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _sitemap_urls(xml_body: bytes) -> tuple[str, list[str]]:
    root = ElementTree.fromstring(xml_body)
    root_name = _local_name(root.tag)
    values: list[str] = []
    child_name = "sitemap" if root_name == "sitemapindex" else "url"
    for child in root:
        if _local_name(child.tag) != child_name:
            continue
        for entry in child:
            if _local_name(entry.tag) == "loc" and (entry.text or "").strip():
                values.append((entry.text or "").strip())
                break
    return root_name, values


def discover_sitemap(
    company: str,
    seed_url: str,
    client: SafeHttpClient,
    *,
    max_sitemaps: int = 4,
    max_samples: int = 3,
) -> DiscoveryRecord | None:
    origin = _origin(seed_url)
    robots_url = f"{origin}/robots.txt"
    sitemap_candidates: list[str] = []
    parser = RobotFileParser()
    try:
        robots = client.get(robots_url, allowed_statuses={404})
        if robots.status_code != 404:
            lines = robots.text.splitlines()
            parser.set_url(robots_url)
            parser.parse(lines)
            for line in lines:
                if line.lower().startswith("sitemap:"):
                    sitemap_candidates.append(line.split(":", 1)[1].strip())
    except Exception as exc:
        LOGGER.warning("Skipping sitemap discovery for %s: %s", seed_url, exc)
        return None
    if not sitemap_candidates:
        sitemap_candidates.append(f"{origin}/sitemap.xml")

    queue = list(dict.fromkeys(sitemap_candidates))[:max_sitemaps]
    seen: set[str] = set()
    job_urls: list[str] = []
    root_sitemap = ""
    while queue and len(seen) < max_sitemaps:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen or urlsplit(sitemap_url).hostname != urlsplit(origin).hostname:
            continue
        seen.add(sitemap_url)
        try:
            response = client.get(sitemap_url, allowed_statuses={404})
            if response.status_code == 404:
                continue
            root_name, urls = _sitemap_urls(response.content)
        except Exception as exc:
            LOGGER.warning("Skipping unreadable sitemap %s: %s", sitemap_url, exc)
            continue
        root_sitemap = root_sitemap or sitemap_url
        if root_name == "sitemapindex":
            queue.extend(urls[: max_sitemaps - len(seen)])
        elif root_name == "urlset":
            for value in urls:
                lowered = value.lower()
                if any(hint in lowered for hint in JOB_URL_HINTS):
                    job_urls.append(value)

    if not root_sitemap or not job_urls:
        return None

    sample_spec = SourceSpec(
        source_id=_source_id(company, "sitemap-sample", root_sitemap),
        name=f"{company} official careers sitemap sample",
        source_type="sitemap",
        enabled=True,
        company=company,
        options={},
    )
    jobs_found = 0
    for job_url in job_urls[:max_samples]:
        try:
            if not parser.can_fetch(DEFAULT_USER_AGENT, job_url):
                continue
            response = client.get(job_url)
            jobs_found += len(parse_job_postings(response.text, response.url, sample_spec))
        except Exception as exc:
            LOGGER.warning("Skipping unreadable sample job %s: %s", job_url, exc)
            continue
    if jobs_found == 0:
        return None

    host = (urlsplit(root_sitemap).hostname or "").lower()
    return DiscoveryRecord(
        company=company,
        platform="schema_org_sitemap",
        evidence_url=root_sitemap,
        confidence="verified_jobposting_sitemap",
        probe_status="pass",
        probe_jobs=jobs_found,
        source={
            "id": _source_id(company, "sitemap", root_sitemap),
            "name": f"{company} official JobPosting sitemap",
            "type": "sitemap",
            "company": company,
            "url": root_sitemap,
            "allowed_domains": [host],
            "job_url_patterns": list(JOB_URL_HINTS[:4]),
            "enabled": True,
            "profile_filter": True,
            "timeout_seconds": 30,
            "rate_limit_per_minute": 10,
            "max_items": 300,
            "max_sitemaps": 20,
            "deny_on_robots_error": True,
        },
    )


def discover_registry(
    registry_path: str | Path,
    base_sources_path: str | Path,
) -> tuple[list[DiscoveryRecord], dict[str, Any]]:
    registry = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
    base = yaml.safe_load(Path(base_sources_path).read_text(encoding="utf-8")) or {}
    load_source_config(base_sources_path)
    employers = registry.get("employers", [])
    if not isinstance(employers, list):
        raise ValueError("employer registry must contain an employers list")

    existing_sources = base.get("sources", [])
    existing_identities = {
        _source_identity(source)
        for source in existing_sources
        if isinstance(source, dict)
    }
    records: list[DiscoveryRecord] = []
    seen_candidates: set[tuple[str, str]] = set()

    for employer in employers:
        if not isinstance(employer, dict):
            continue
        company = str(employer.get("company", "")).strip()
        if not company or company.endswith("Job Alerts"):
            continue
        seeds = [
            str(employer.get("public_job_url", "")).strip(),
            str(employer.get("official_careers_url", "")).strip(),
        ]
        seeds = [seed for seed in dict.fromkeys(seeds) if seed]
        client = SafeHttpClient(
            timeout_seconds=10,
            max_response_bytes=5_000_000,
            rate_limit_per_minute=30,
            max_redirects=4,
        )
        discovered_urls: list[str] = []
        for seed in seeds:
            try:
                response = client.get(seed)
            except Exception as exc:
                LOGGER.warning("Skipping unreachable discovery seed %s: %s", seed, exc)
                continue
            discovered_urls.append(response.url)
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type or response.text.lstrip().startswith("<"):
                discovered_urls.extend(extract_candidate_urls(response.text, response.url))

        for candidate_url in dict.fromkeys(discovered_urls):
            record = detect_source(company, candidate_url)
            if record is None:
                continue
            identity = _source_identity(record.source)
            if identity in existing_identities or identity in seen_candidates:
                continue
            seen_candidates.add(identity)
            records.append(probe_record(record))

        for seed in seeds[:1]:
            sitemap_record = discover_sitemap(company, seed, client)
            if sitemap_record is None:
                continue
            identity = _source_identity(sitemap_record.source)
            if identity not in existing_identities and identity not in seen_candidates:
                seen_candidates.add(identity)
                records.append(sitemap_record)

    verified_sources = [
        record.source
        for record in records
        if record.probe_status == "pass" and record.source.get("enabled") is True
    ]
    runtime = {
        "sources": [*existing_sources, *verified_sources],
        "policy": {
            **(base.get("policy", {}) if isinstance(base.get("policy"), dict) else {}),
            "respect_robots_txt": True,
            "skip_login_required_pages": True,
            "bypass_captcha": False,
            "use_rotating_proxies": False,
            "retain_source_evidence": True,
        },
    }
    return records, runtime


def write_outputs(
    records: list[DiscoveryRecord],
    runtime: dict[str, Any],
    *,
    report_json: str | Path,
    report_md: str | Path,
    runtime_sources: str | Path,
) -> None:
    json_path = Path(report_json)
    md_path = Path(report_md)
    runtime_path = Path(runtime_sources)
    for path in (json_path, md_path, runtime_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "principle": "Official public sources first; Gmail is not used by this discovery engine.",
        "detected": len(records),
        "verified": sum(record.probe_status == "pass" for record in records),
        "records": [record.to_json() for record in records],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False), encoding="utf-8")
    load_source_config(runtime_path)

    lines = [
        "# Latest Official Source Autodiscovery",
        "",
        "Gmail dependency: **NONE**. Discovery uses official career pages, public ATS connectors, robots.txt, sitemaps and JobPosting structured data.",
        "",
        f"Detected candidates: `{len(records)}`",
        f"Verified public sources added to runtime: `{sum(record.probe_status == 'pass' for record in records)}`",
        "",
        "| Company | Platform | Confidence | Probe | Jobs observed | Evidence | Error |",
        "|---|---|---|---|---:|---|---|",
    ]
    for record in records:
        evidence = record.evidence_url.replace("|", "%7C")
        error = record.error.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {record.company} | {record.platform} | {record.confidence} | "
            f"{record.probe_status} | {record.probe_jobs} | [Open]({evidence}) | {error or '—'} |"
        )
    if not records:
        lines.append("| No new candidates | — | — | — | 0 | — | — |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
