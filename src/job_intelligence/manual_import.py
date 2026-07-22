from __future__ import annotations

import re

from .deduplicate import build_job_key
from .models import JobRecord
from .scoring import score_job

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def create_manual_job(
    *,
    title: str,
    company: str,
    text: str,
    location: str = "",
    apply_url: str = "",
    source_url: str = "",
    source_name: str = "manual",
    published_at: str = "",
) -> JobRecord:
    """Create a normalized job from user-supplied evidence.

    Any email found in the supplied text is recorded only as PUBLIC_UNVERIFIED.
    The function never guesses or verifies addresses.
    """
    emails = _EMAIL_PATTERN.findall(text)
    job = JobRecord(
        title=" ".join(title.split()),
        company=" ".join(company.split()),
        location=" ".join(location.split()),
        description=text.strip(),
        apply_url=apply_url.strip(),
        source_url=source_url.strip(),
        source_name=source_name.strip() or "manual",
        published_at=published_at.strip(),
        recruiter_email=emails[0].lower() if emails else "",
        contact_confidence="PUBLIC_UNVERIFIED" if emails else "",
    )
    result = score_job(job)
    job.match_score = result.score
    job.priority = result.priority
    job.match_reasons = "; ".join(result.reasons)
    job.gaps = "; ".join(result.gaps)
    job.job_key = build_job_key(job)
    return job
