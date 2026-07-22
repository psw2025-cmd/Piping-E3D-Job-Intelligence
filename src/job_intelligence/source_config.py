from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

_SUPPORTED_TYPES = {"greenhouse", "lever", "smartrecruiters", "rss", "sitemap"}
_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


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
        value = int(self.options.get(key, default))
        if value < minimum:
            raise ValueError(
                f"source {self.source_id!r} option {key!r} must be >= {minimum}"
            )
        return value


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
    elif spec.source_type == "smartrecruiters":
        spec.require_text("company_identifier")
    else:
        _validate_public_url(spec.require_text("url"), spec.source_id)

    if not spec.company:
        raise ValueError(f"source {spec.source_id!r} requires company")
    spec.int_option("timeout_seconds", 30)
    spec.int_option("rate_limit_per_minute", 30)
    spec.int_option("max_items", 500)


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
            enabled=bool(raw.get("enabled", False)),
            company=str(raw.get("company", "")).strip(),
            options={
                key: value
                for key, value in raw.items()
                if key not in {"id", "name", "type", "enabled", "company"}
            },
        )
        _validate_source(spec)
        sources.append(spec)

    policy = loaded.get("policy", {})
    if not isinstance(policy, dict):
        raise ValueError("policy must be a mapping")
    if bool(policy.get("bypass_captcha", False)):
        raise ValueError("bypass_captcha must remain false")
    if bool(policy.get("use_rotating_proxies", False)):
        raise ValueError("use_rotating_proxies must remain false")

    return SourceConfig(tuple(sources), dict(policy))
