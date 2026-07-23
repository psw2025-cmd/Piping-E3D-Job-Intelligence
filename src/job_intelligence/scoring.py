from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .models import JobRecord
from .normalization import enrich_job


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: int
    priority: str
    reasons: tuple[str, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoringProfile:
    weights: dict[str, int]
    thresholds: dict[str, int]
    target_roles: tuple[str, ...]
    e3d_pdms_terms: tuple[str, ...]
    layout_terms: tuple[str, ...]
    sector_terms: tuple[str, ...]
    experience_terms: tuple[str, ...]
    preferred_locations: tuple[str, ...]
    site_offshore_terms: tuple[str, ...]
    diploma_terms: tuple[str, ...]
    mandatory_degree_terms: tuple[str, ...]
    recent_days: int


_DEFAULT_WEIGHTS = {
    "target_role": 20,
    "e3d_pdms": 20,
    "piping_layout": 15,
    "sector": 10,
    "experience": 10,
    "preferred_location": 10,
    "site_offshore": 5,
    "diploma_eligible": 5,
    "recent_posting": 5,
}
_DEFAULT_THRESHOLDS = {"critical": 85, "high": 70, "normal": 50}
_DEFAULT_TERMS = {
    "e3d_pdms": ("aveva e3d", "e3d", "pdms", "sp3d", "smartplant 3d"),
    "piping_layout": (
        "piping layout",
        "equipment layout",
        "plant layout",
        "plot plan",
        "general arrangement",
        "3d model coordination",
    ),
    "experience": ("10 years", "12 years", "15 years", "senior", "lead"),
    "site_offshore": (
        "site engineering",
        "field engineering",
        "site experience",
        "brownfield",
        "punch list",
        "offshore",
    ),
    "diploma_eligible": ("diploma", "degree or diploma"),
    "mandatory_degree": ("degree required", "bachelor's degree required"),
}
_DEFAULT_ROLES = (
    "lead piping engineer",
    "senior piping engineer",
    "piping design engineer",
    "piping layout engineer",
    "e3d piping designer",
    "pdms piping designer",
    "sp3d piping designer",
    "offshore piping engineer",
    "site piping engineer",
)
_DEFAULT_SECTORS = (
    "oil and gas",
    "refinery",
    "petrochemical",
    "offshore",
    "lng",
    "nuclear",
)
_DEFAULT_LOCATIONS = (
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


def _lower_terms(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list | tuple):
        return ()
    return tuple(str(value).strip().lower() for value in values if str(value).strip())


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _merge_int_config(
    defaults: dict[str, int],
    configured: Any,
) -> dict[str, int]:
    merged = dict(defaults)
    for key, value in _mapping_or_empty(configured).items():
        if key not in defaults:
            continue
        try:
            merged[key] = int(value)
        except (TypeError, ValueError):
            continue
    return merged


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return loaded


def _resolve_config_dir(config_dir: str | Path | None) -> Path | None:
    candidates: list[Path] = []
    if config_dir is not None:
        candidates.append(Path(config_dir))
    env_dir = os.getenv("JOB_INTEL_CONFIG_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend(
        (
            Path.cwd() / "config",
            Path(__file__).resolve().parents[2] / "config",
        )
    )
    return next((path for path in candidates if path.is_dir()), None)


def load_scoring_profile(config_dir: str | Path | None = None) -> ScoringProfile:
    resolved = _resolve_config_dir(config_dir)
    roles_data: dict[str, Any] = {}
    locations_data: dict[str, Any] = {}
    scoring_data: dict[str, Any] = {}
    if resolved:
        roles_data = _read_yaml(resolved / "roles.yaml")
        locations_data = _read_yaml(resolved / "locations.yaml")
        scoring_data = _read_yaml(resolved / "scoring.yaml")

    weights = _merge_int_config(_DEFAULT_WEIGHTS, scoring_data.get("weights"))
    thresholds = _merge_int_config(
        _DEFAULT_THRESHOLDS,
        scoring_data.get("thresholds"),
    )
    term_config = _mapping_or_empty(scoring_data.get("terms"))

    location_groups = locations_data.get("locations", {})
    location_values: list[str] = []
    if isinstance(location_groups, dict):
        for values in location_groups.values():
            if isinstance(values, list):
                location_values.extend(str(value) for value in values)

    return ScoringProfile(
        weights=weights,
        thresholds=thresholds,
        target_roles=_lower_terms(roles_data.get("target_roles")) or _DEFAULT_ROLES,
        e3d_pdms_terms=_lower_terms(term_config.get("e3d_pdms"))
        or _DEFAULT_TERMS["e3d_pdms"],
        layout_terms=_lower_terms(term_config.get("piping_layout"))
        or _DEFAULT_TERMS["piping_layout"],
        sector_terms=_lower_terms(roles_data.get("sectors")) or _DEFAULT_SECTORS,
        experience_terms=_lower_terms(term_config.get("experience"))
        or _DEFAULT_TERMS["experience"],
        preferred_locations=_lower_terms(location_values) or _DEFAULT_LOCATIONS,
        site_offshore_terms=_lower_terms(term_config.get("site_offshore"))
        or _DEFAULT_TERMS["site_offshore"],
        diploma_terms=_lower_terms(term_config.get("diploma_eligible"))
        or _DEFAULT_TERMS["diploma_eligible"],
        mandatory_degree_terms=_lower_terms(term_config.get("mandatory_degree"))
        or _DEFAULT_TERMS["mandatory_degree"],
        recent_days=_int_or_default(scoring_data.get("recent_days"), 7),
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_recent(published_at: str, days: int) -> bool:
    if not published_at:
        return False
    try:
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed >= datetime.now(UTC) - timedelta(days=days)
    except ValueError:
        return False


def score_job(
    job: JobRecord,
    *,
    config_dir: str | Path | None = None,
    profile: ScoringProfile | None = None,
) -> MatchResult:
    resolved = _resolve_config_dir(config_dir)
    if resolved is not None:
        enrich_job(job, config_dir=resolved)
    active = profile or load_scoring_profile(resolved)
    text = job.searchable_text
    score = 0
    reasons: list[str] = []
    gaps: list[str] = []

    if _contains_any(text, active.target_roles):
        score += active.weights["target_role"]
        reasons.append(
            f"Target role alignment: {job.normalized_role or job.title}"
        )
    else:
        gaps.append("Target role wording not detected")

    if _contains_any(text, active.e3d_pdms_terms):
        score += active.weights["e3d_pdms"]
        reasons.append("AVEVA E3D, PDMS, SP3D or related 3D requirement detected")
    else:
        gaps.append("E3D/PDMS/SP3D requirement not stated")

    if _contains_any(text, active.layout_terms):
        score += active.weights["piping_layout"]
        reasons.append("Piping, equipment or plant-layout scope detected")

    if _contains_any(text, active.sector_terms):
        score += active.weights["sector"]
        reasons.append(f"Relevant sector detected: {job.sector or 'EPC process industry'}")

    if _contains_any(text, active.experience_terms):
        score += active.weights["experience"]
        reasons.append("Senior or lead experience level appears compatible")

    if _contains_any(text, active.preferred_locations):
        score += active.weights["preferred_location"]
        location = ", ".join(part for part in (job.city, job.country) if part)
        reasons.append(f"Preferred location detected: {location or job.location}")

    if _contains_any(text, active.site_offshore_terms):
        score += active.weights["site_offshore"]
        reasons.append("Site, field, brownfield or offshore experience valued")

    if _contains_any(text, active.diploma_terms):
        score += active.weights["diploma_eligible"]
        reasons.append("Diploma eligibility stated")
    elif _contains_any(text, active.mandatory_degree_terms):
        gaps.append("Degree may be mandatory")

    if _is_recent(job.published_at, active.recent_days):
        score += active.weights["recent_posting"]
        reasons.append("Recently published")

    score = min(score, 100)
    priority = (
        "critical"
        if score >= active.thresholds["critical"]
        else "high"
        if score >= active.thresholds["high"]
        else "normal"
        if score >= active.thresholds["normal"]
        else "low"
    )
    return MatchResult(score, priority, tuple(reasons), tuple(gaps))
