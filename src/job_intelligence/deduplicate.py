from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import JobRecord

_TRACKING_PREFIXES = ("utm_", "trk", "tracking", "source", "ref")


def normalize_text(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(value.split())


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(filtered_query)), "")
    )


def build_job_key(job: JobRecord) -> str:
    canonical_url = canonicalize_url(job.apply_url or job.source_url)
    if canonical_url:
        raw = f"url|{canonical_url}"
    else:
        description_sample = normalize_text(job.description)[:500]
        raw = "|".join(
            (
                "fields",
                normalize_text(job.title),
                normalize_text(job.company),
                normalize_text(job.location),
                description_sample,
            )
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
