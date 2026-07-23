from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class JobRecord:
    title: str
    company: str
    normalized_role: str = ""
    location: str = ""
    city: str = ""
    country: str = ""
    description: str = ""
    apply_url: str = ""
    source_url: str = ""
    source_name: str = "manual"
    published_at: str = ""
    closing_at: str = ""
    found_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)
    job_type: str = ""
    employment_type: str = ""
    salary_text: str = ""
    experience_text: str = ""
    skills_text: str = ""
    software_text: str = ""
    sector: str = ""
    agency_name: str = ""
    recruiter_name: str = ""
    recruiter_email: str = ""
    contact_source_url: str = ""
    contact_confidence: str = ""
    match_score: int = 0
    match_reasons: str = ""
    gaps: str = ""
    priority: str = "normal"
    duplicate_status: str = "unique"
    application_status: str = "new"
    job_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def searchable_text(self) -> str:
        return " ".join(
            part
            for part in (
                self.title,
                self.normalized_role,
                self.company,
                self.location,
                self.city,
                self.country,
                self.description,
                self.skills_text,
                self.software_text,
                self.experience_text,
                self.sector,
                self.employment_type,
            )
            if part
        ).lower()
