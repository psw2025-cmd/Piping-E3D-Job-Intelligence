from __future__ import annotations

import html
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from ..models import JobRecord


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    source_url: str
    content_type: str
    body: bytes
    status_code: int = 200
    suffix: str = ".bin"


@dataclass(slots=True)
class CollectionResult:
    jobs: list[JobRecord] = field(default_factory=list)
    evidence: list[EvidenceArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "br",
        "p",
        "div",
        "li",
        "ul",
        "ol",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "section",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(html.unescape(value))
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def join_nonempty(values: Iterable[object], separator: str = ", ") -> str:
    cleaned = [str(value).strip() for value in values if str(value or "").strip()]
    return separator.join(cleaned)


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def salary_text_from_range(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    minimum = value.get("min")
    maximum = value.get("max")
    currency = str(value.get("currency", "")).strip()
    interval = str(value.get("interval", "")).strip()
    if minimum is None and maximum is None:
        return ""
    if minimum is not None and maximum is not None:
        amount = f"{minimum}–{maximum}"
    else:
        amount = str(minimum if minimum is not None else maximum)
    parts = [currency, amount]
    if interval:
        parts.append(f"per {interval}")
    return " ".join(part for part in parts if part)


def flatten_json_ld(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        graph = value.get("@graph")
        if graph is not None:
            found.extend(flatten_json_ld(graph))
    elif isinstance(value, list):
        for item in value:
            found.extend(flatten_json_ld(item))
    return found
