from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import JobRecord

_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
}
_TRACKING_PREFIXES = ("utm_",)


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
        if key.lower() not in _TRACKING_KEYS
        and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(filtered_query)), "")
    )


def build_identity_fingerprint(job: JobRecord) -> str:
    raw = "|".join(
        (
            normalize_text(job.title),
            normalize_text(job.company),
            normalize_text(job.location),
            normalize_text(job.description),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_job_key(job: JobRecord) -> str:
    """Return an immutable field-based primary key.

    URL matching is a secondary database identity. Adding an apply URL later therefore
    does not change an existing record's primary key.
    """
    return build_identity_fingerprint(job)
