from __future__ import annotations

import calendar
from datetime import UTC, datetime
from typing import Any

import feedparser

from ..models import JobRecord
from ..source_config import SourceSpec
from .common import CollectionResult, EvidenceArtifact, html_to_text, join_nonempty
from .http_client import HttpClient


def _published_at(entry: Any) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        timestamp = calendar.timegm(parsed)
        return datetime.fromtimestamp(timestamp, UTC).replace(microsecond=0).isoformat()
    return str(entry.get("published") or entry.get("updated") or "").strip()


def collect_rss(spec: SourceSpec, client: HttpClient) -> CollectionResult:
    url = spec.require_text("url")
    response = client.get(url)
    feed = feedparser.parse(response.content)
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
        error = getattr(feed, "bozo_exception", "invalid feed")
        raise ValueError(f"source {spec.source_id!r} RSS parse failed: {error}")

    default_location = str(spec.options.get("location", "")).strip()
    max_items = spec.int_option("max_items", 500)
    jobs: list[JobRecord] = []
    for entry in list(feed.entries)[:max_items]:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        if not title:
            continue
        description = html_to_text(
            str(entry.get("summary") or entry.get("description") or "")
        )
        tags = [
            str(tag.get("term", "")).strip()
            for tag in entry.get("tags", []) or []
            if isinstance(tag, dict)
        ]
        jobs.append(
            JobRecord(
                title=title,
                company=spec.company,
                location=default_location,
                description=description,
                apply_url=link,
                source_url=link or response.url,
                source_name=spec.name,
                published_at=_published_at(entry),
                skills_text=join_nonempty(tags, "; "),
            )
        )

    return CollectionResult(
        jobs=jobs,
        evidence=[
            EvidenceArtifact(
                source_url=response.url,
                content_type=response.headers.get(
                    "content-type", "application/rss+xml"
                ),
                body=response.content,
                status_code=response.status_code,
                suffix=".xml",
            )
        ],
    )
