from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import JobRecord


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: int
    priority: str
    reasons: tuple[str, ...]
    gaps: tuple[str, ...]


ROLE_TERMS = (
    "lead piping engineer",
    "senior piping engineer",
    "piping design engineer",
    "piping layout engineer",
    "e3d piping designer",
    "pdms piping designer",
    "offshore piping engineer",
    "site piping engineer",
)
E3D_TERMS = ("aveva e3d", "e3d", "pdms")
LAYOUT_TERMS = ("piping layout", "equipment layout", "plot plan", "general arrangement")
SECTOR_TERMS = ("oil and gas", "refinery", "petrochemical", "offshore", "lng", "nuclear")
SITE_TERMS = ("site engineering", "site experience", "brownfield", "punch list", "offshore")
PREFERRED_LOCATIONS = (
    "mumbai",
    "navi mumbai",
    "pune",
    "vadodara",
    "uae",
    "saudi arabia",
    "oman",
    "qatar",
    "kuwait",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_recent(published_at: str, days: int = 7) -> bool:
    if not published_at:
        return False
    try:
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed >= datetime.now(UTC) - timedelta(days=days)
    except ValueError:
        return False


def score_job(job: JobRecord) -> MatchResult:
    text = job.searchable_text
    score = 0
    reasons: list[str] = []
    gaps: list[str] = []

    if _contains_any(text, ROLE_TERMS):
        score += 20
        reasons.append("Target piping/E3D role alignment")
    else:
        gaps.append("Target role wording not detected")

    if _contains_any(text, E3D_TERMS):
        score += 20
        reasons.append("AVEVA E3D or PDMS requirement detected")
    else:
        gaps.append("E3D/PDMS requirement not stated")

    if _contains_any(text, LAYOUT_TERMS):
        score += 15
        reasons.append("Piping or equipment layout scope detected")

    if _contains_any(text, SECTOR_TERMS):
        score += 10
        reasons.append("Relevant EPC process-industry sector detected")

    if any(term in text for term in ("10 years", "12 years", "15 years", "senior", "lead")):
        score += 10
        reasons.append("Senior experience level appears compatible")

    if _contains_any(text, PREFERRED_LOCATIONS):
        score += 10
        reasons.append("Preferred location detected")

    if _contains_any(text, SITE_TERMS):
        score += 5
        reasons.append("Site, brownfield or offshore experience valued")

    if "diploma" in text or "degree or diploma" in text:
        score += 5
        reasons.append("Diploma eligibility stated")
    elif "degree required" in text or "bachelor's degree required" in text:
        gaps.append("Degree may be mandatory")

    if _is_recent(job.published_at):
        score += 5
        reasons.append("Recently published")

    score = min(score, 100)
    priority = "critical" if score >= 85 else "high" if score >= 70 else "normal" if score >= 50 else "low"
    return MatchResult(score, priority, tuple(reasons), tuple(gaps))
