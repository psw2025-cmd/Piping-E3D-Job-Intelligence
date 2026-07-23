from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import JobRecord

_CLOSING_DATE_PATTERN = re.compile(
    r"(?:closing date|application deadline|apply by|last date)\s*[:\-]\s*"
    r"([^\n\r|;]{4,80})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProfileTaxonomy:
    role_families: tuple[tuple[str, tuple[str, ...]], ...]
    software_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    sector_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    employment_type_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    city_aliases: tuple[tuple[str, str, tuple[str, ...]], ...]
    country_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    region_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    negative_role_terms: tuple[str, ...]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return loaded


def _terms(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        str(item).strip().lower()
        for item in value
        if str(item).strip()
    )


def _alias_groups(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, dict):
        return ()
    groups: list[tuple[str, tuple[str, ...]]] = []
    for canonical, aliases in value.items():
        canonical_text = str(canonical).strip()
        values = _terms(aliases)
        if canonical_text and values:
            groups.append((canonical_text, values))
    return tuple(groups)


def load_profile_taxonomy(config_dir: str | Path) -> ProfileTaxonomy:
    root = Path(config_dir)
    roles = _read_yaml(root / "roles.yaml")
    locations = _read_yaml(root / "locations.yaml")

    city_groups: list[tuple[str, str, tuple[str, ...]]] = []
    raw_cities = locations.get("location_aliases", {})
    if isinstance(raw_cities, dict):
        for city, details in raw_cities.items():
            if not isinstance(details, dict):
                continue
            city_name = str(city).strip()
            country = str(details.get("country", "")).strip()
            aliases = _terms(details.get("aliases"))
            if city_name and aliases:
                city_groups.append((city_name, country, aliases))

    return ProfileTaxonomy(
        role_families=_alias_groups(roles.get("role_families")),
        software_aliases=_alias_groups(roles.get("software_aliases")),
        sector_aliases=_alias_groups(roles.get("sector_aliases")),
        employment_type_aliases=_alias_groups(
            roles.get("employment_type_aliases")
        ),
        city_aliases=tuple(city_groups),
        country_aliases=_alias_groups(locations.get("country_aliases")),
        region_aliases=_alias_groups(locations.get("region_aliases")),
        negative_role_terms=_terms(roles.get("negative_role_terms")),
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    cleaned = " ".join(phrase.lower().split())
    if not cleaned:
        return False
    pattern = re.escape(cleaned).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text) is not None


def _first_match(
    text: str,
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    candidates: list[tuple[int, int, str]] = []
    for order, (canonical, aliases) in enumerate(groups):
        for alias in aliases:
            if _contains_phrase(text, alias):
                candidates.append((len(alias), -order, canonical))
    return max(candidates, default=(0, 0, ""))[2]


def _all_matches(
    text: str,
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    matches: list[str] = []
    for canonical, aliases in groups:
        if any(_contains_phrase(text, alias) for alias in aliases):
            matches.append(canonical)
    return tuple(matches)


def normalize_role(job: JobRecord, taxonomy: ProfileTaxonomy) -> str:
    title_text = " ".join(job.title.lower().split())
    if any(_contains_phrase(title_text, term) for term in taxonomy.negative_role_terms):
        return ""
    title_match = _first_match(title_text, taxonomy.role_families)
    if title_match:
        return title_match
    context = f"{title_text} {job.description[:2000].lower()}"
    return _first_match(context, taxonomy.role_families)


def normalize_location(
    raw_location: str,
    taxonomy: ProfileTaxonomy,
) -> tuple[str, str]:
    text = " ".join(raw_location.lower().split())
    if not text:
        return "", ""

    city_candidates: list[tuple[int, int, str, str]] = []
    for order, (city, country, aliases) in enumerate(taxonomy.city_aliases):
        for alias in aliases:
            if _contains_phrase(text, alias):
                city_candidates.append((len(alias), -order, city, country))
    if city_candidates:
        _, _, city, country = max(city_candidates)
        return city, country

    country = _first_match(text, taxonomy.country_aliases)
    if country:
        return "", country
    region = _first_match(text, taxonomy.region_aliases)
    return "", region


def extract_closing_date_text(text: str) -> str:
    match = _CLOSING_DATE_PATTERN.search(text)
    return " ".join(match.group(1).split()) if match else ""


def enrich_job(
    job: JobRecord,
    *,
    config_dir: str | Path,
    taxonomy: ProfileTaxonomy | None = None,
) -> JobRecord:
    active = taxonomy or load_profile_taxonomy(config_dir)
    searchable = job.searchable_text

    job.normalized_role = job.normalized_role or normalize_role(job, active)
    city, country = normalize_location(job.location, active)
    job.city = job.city or city
    job.country = job.country or country
    job.software_text = job.software_text or "; ".join(
        _all_matches(searchable, active.software_aliases)
    )
    job.sector = job.sector or _first_match(searchable, active.sector_aliases)
    job.employment_type = job.employment_type or _first_match(
        searchable,
        active.employment_type_aliases,
    )
    job.closing_at = job.closing_at or extract_closing_date_text(job.description)
    job.duplicate_status = job.duplicate_status or "unique"
    return job
