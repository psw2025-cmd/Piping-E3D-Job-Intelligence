from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

_SUPPORTED_TYPES = {
    "greenhouse",
    "lever",
    "oracle_hcm",
    "public_html",
    "smartrecruiters",
    "rss",
    "sitemap",
    "workday",
}
_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_SITE_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_WORKDAY_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_LOCALE_PATTERN = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9.-]+$", re.IGNORECASE)
_POLICY_DEFAULTS = {
    "respect_robots_txt": True,
    "bypass_captcha": False,
    "use_rotating_proxies": False,
    "retain_source_evidence": True,
}


def _strict_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be true or false")


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    name: str
    source_type: str
    enabled: bool
    company: str
    options: dict[str, Any]

    def require_text(self, key: str) -> str:
        value = str(self.options.get(key, "")).strip()
        if not value:
            raise ValueError(f"source {self.source_id!r} requires {key!r}")
        return value

    def int_option(self, key: str, default: int, minimum: int = 1) -> int:
        raw_value = self.options.get(key, default)
        if isinstance(raw_value, bool):
            raise ValueError(
                f"source {self.source_id!r} option {key!r} must be an integer"
            )
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"source {self.source_id!r} option {key!r} must be an integer"
            ) from exc
        if value < minimum:
            raise ValueError(
                f"source {self.source_id!r} option {key!r} must be >= {minimum}"
            )
        return value

    def bool_option(self, key: str, default: bool) -> bool:
        value = self.options.get(key, default)
        return _strict_bool(value, f"source {self.source_id!r} option {key!r}")

    def text_list_option(self, key: str) -> tuple[str, ...]:
        raw_value = self.options.get(key, [])
        if not isinstance(raw_value, list):
            raise ValueError(
                f"source {self.source_id!r} option {key!r} must be a list"
            )
        values: list[str] = []
        for raw_item in raw_value:
            if not isinstance(raw_item, str) or not raw_item.strip():
                raise ValueError(
                    f"source {self.source_id!r} option {key!r} "
                    "must contain non-empty strings"
                )
            values.append(raw_item.strip().lower())
        return tuple(values)


@dataclass(frozen=True, slots=True)
class SourceConfig:
    sources: tuple[SourceSpec, ...]
    policy: dict[str, Any]


def _validate_public_url(value: str, source_id: str, field: str = "url") -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"source {source_id!r} field {field!r} must be an HTTP(S) URL"
        )
    if parsed.username or parsed.password:
        raise ValueError(f"source {source_id!r} must not embed credentials in URLs")

    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError(f"source {source_id!r} must use a public URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError(f"source {source_id!r} must use a public URL")


def _require_text_list(spec: SourceSpec, key: str) -> list[str]:
    value = spec.options.get(key)
    if not isinstance(value, list):
        raise ValueError(
            f"source {spec.source_id!r} option {key!r} must be a list"
        )
    result = [
        item.strip() for item in value if isinstance(item, str) and item.strip()
    ]
    if len(result) != len(value) or not result:
        raise ValueError(
            f"source {spec.source_id!r} option {key!r} "
            "must contain non-empty text"
        )
    return result


def _validate_optional_text_list(spec: SourceSpec, key: str) -> None:
    if key not in spec.options:
        return
    value = spec.options[key]
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(
            f"source {spec.source_id!r} option {key!r} must contain only text"
        )


def _validate_public_html(spec: SourceSpec) -> None:
    base_url = spec.require_text("url")
    _validate_public_url(base_url, spec.source_id)
    root_host = (urlsplit(base_url).hostname or "").lower()
    domains = _require_text_list(spec, "allowed_domains")
    normalized_domains = {domain.lower() for domain in domains}
    if root_host not in normalized_domains:
        raise ValueError(
            f"source {spec.source_id!r} allowed_domains must include "
            "the listing host"
        )
    for domain in normalized_domains:
        if (
            not _DOMAIN_PATTERN.fullmatch(domain)
            or domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            raise ValueError(
                f"source {spec.source_id!r} has invalid allowed domain {domain!r}"
            )
    _require_text_list(spec, "job_link_patterns")
    _validate_optional_text_list(spec, "anchor_text_patterns")
    _validate_optional_text_list(spec, "required_anchor_text_patterns")
    _validate_optional_text_list(spec, "exclude_anchor_text_patterns")
    template = str(spec.options.get("page_url_template", "")).strip()
    if template:
        if "{page}" not in template:
            raise ValueError(
                f"source {spec.source_id!r} page_url_template must contain "
                "'{page}'"
            )
        try:
            rendered = template.format(page=0)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"source {spec.source_id!r} has invalid page_url_template"
            ) from exc
        _validate_public_url(rendered, spec.source_id, "page_url_template")
        rendered_host = (urlsplit(rendered).hostname or "").lower()
        if rendered_host not in normalized_domains:
            raise ValueError(
                f"source {spec.source_id!r} page_url_template is outside "
                "allowed_domains"
            )
    spec.int_option("page_start", 0, minimum=0)
    spec.int_option("page_step", 1)
    spec.bool_option("fetch_details", True)
    spec.bool_option("deny_on_robots_error", True)


def _validate_https_origin(spec: SourceSpec, field: str) -> str:
    base_url = spec.require_text(field)
    _validate_public_url(base_url, spec.source_id, field)
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.path not in {"", "/"}:
        raise ValueError(
            f"source {spec.source_id!r} {field} must be an HTTPS origin"
        )
    return base_url


def _validate_oracle_source(spec: SourceSpec) -> None:
    _validate_https_origin(spec, "base_url")
    site_number = spec.require_text("site_number")
    if not _SITE_NUMBER_PATTERN.fullmatch(site_number):
        raise ValueError(
            f"source {spec.source_id!r} site_number contains invalid characters"
        )
    spec.text_list_option("include_terms")
    spec.text_list_option("location_terms")
    spec.int_option("max_scan_items", 2500)


def _validate_workday_source(spec: SourceSpec) -> None:
    _validate_https_origin(spec, "base_url")
    for field in ("tenant", "site"):
        value = spec.require_text(field)
        if not _WORKDAY_IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError(
                f"source {spec.source_id!r} {field} contains invalid characters"
            )
    locale = str(spec.options.get("locale", "en-US")).strip()
    if not _LOCALE_PATTERN.fullmatch(locale):
        raise ValueError(f"source {spec.source_id!r} has invalid locale {locale!r}")
    _require_text_list(spec, "search_terms")
    _require_text_list(spec, "include_terms")
    _validate_optional_text_list(spec, "location_terms")
    spec.int_option("page_size", 20)
    spec.int_option("max_scan_items", 3000)


def _validate_source(spec: SourceSpec) -> None:
    if not _SOURCE_ID_PATTERN.fullmatch(spec.source_id):
        raise ValueError(
            f"source id {spec.source_id!r} must use lowercase letters, numbers, _ or -"
        )
    if spec.source_type not in _SUPPORTED_TYPES:
        raise ValueError(
            f"source {spec.source_id!r} has unsupported type {spec.source_type!r}"
        )
    if spec.source_type == "greenhouse":
        spec.require_text("board_token")
    elif spec.source_type == "lever":
        spec.require_text("site")
        region = str(spec.options.get("region", "global")).strip().lower()
        if region not in {"global", "eu"}:
            raise ValueError(
                f"source {spec.source_id!r} Lever region must be global or eu"
            )
    elif spec.source_type == "oracle_hcm":
        _validate_oracle_source(spec)
    elif spec.source_type == "workday":
        _validate_workday_source(spec)
    elif spec.source_type == "public_html":
        _validate_public_html(spec)
    elif spec.source_type == "smartrecruiters":
        spec.require_text("company_identifier")
        spec.bool_option("fetch_details", True)
    else:
        _validate_public_url(spec.require_text("url"), spec.source_id)
        if spec.source_type == "sitemap":
            spec.bool_option("deny_on_robots_error", True)

    if not spec.company:
        raise ValueError(f"source {spec.source_id!r} requires company")
    spec.int_option("timeout_seconds", 30)
    spec.int_option("rate_limit_per_minute", 30)
    spec.int_option("max_items", 500)
    spec.int_option("max_pages", 100)
    spec.int_option("max_response_bytes", 15_000_000)
    spec.int_option("max_redirects", 5, minimum=0)


def load_source_config(path: str | Path) -> SourceConfig:
    config_path = Path(path)
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("source configuration root must be a mapping")

    raw_sources = loaded.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be a list")

    sources: list[SourceSpec] = []
    seen: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError("each source entry must be a mapping")
        source_id = str(raw.get("id", "")).strip()
        if source_id in seen:
            raise ValueError(f"duplicate source id: {source_id}")
        seen.add(source_id)
        spec = SourceSpec(
            source_id=source_id,
            name=str(raw.get("name", source_id)).strip() or source_id,
            source_type=str(raw.get("type", "")).strip().lower(),
            enabled=_strict_bool(
                raw.get("enabled", False),
                f"source {source_id!r} field 'enabled'",
            ),
            company=str(raw.get("company", "")).strip(),
            options={
                key: value
                for key, value in raw.items()
                if key not in {"id", "name", "type", "enabled", "company"}
            },
        )
        _validate_source(spec)
        sources.append(spec)

    raw_policy = loaded.get("policy", {})
    if not isinstance(raw_policy, dict):
        raise ValueError("policy must be a mapping")
    policy = dict(raw_policy)
    for key, default in _POLICY_DEFAULTS.items():
        policy[key] = _strict_bool(raw_policy.get(key, default), f"policy {key!r}")
    if policy["bypass_captcha"]:
        raise ValueError("bypass_captcha must remain false")
    if policy["use_rotating_proxies"]:
        raise ValueError("use_rotating_proxies must remain false")

    return SourceConfig(tuple(sources), policy)
