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
_WORKDAY_CODE_PATTERN = re.compile(r"^[A-Z]{2}(?:\.[A-Z]{2,3})?\.")


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
    workday_country_codes: tuple[tuple[str, str], ...] = ()


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


def _combined_alias_groups(*values: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    combined: dict[str, list[str]] = {}
    order: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        for canonical, aliases in value.items():
            canonical_text = str(canonical).strip()
            if not canonical_text:
                continue
            if canonical_text not in combined:
                combined[canonical_text] = []
                order.append(canonical_text)
            for alias in _terms(aliases):
                if alias not in combined[canonical_text]:
                    combined[canonical_text].append(alias)
    return tuple(
        (canonical, tuple(combined[canonical]))
        for canonical in order
        if combined[canonical]
    )


def _city_groups(*values: Any) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    groups: list[tuple[str, str, tuple[str, ...]]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        for city, details in value.items():
            if not isinstance(details, dict):
                continue
            city_name = str(city).strip()
            country = str(details.get("country", "")).strip()
            aliases = _terms(details.get("aliases"))
            key = (city_name.lower(), country.lower())
            if city_name and aliases and key not in seen:
                groups.append((city_name, country, aliases))
                seen.add(key)
    return tuple(groups)


def load_profile_taxonomy(config_dir: str | Path) -> ProfileTaxonomy:
    root = Path(config_dir)
    roles = _read_yaml(root / "roles.yaml")
    locations = _read_yaml(root / "locations.yaml")
    expansion = _read_yaml(root / "coverage_expansion.yaml")
    raw_codes = expansion.get("workday_country_codes", {})
    code_pairs = (
        tuple(
            (str(code).strip().upper(), str(country).strip())
            for code, country in raw_codes.items()
            if str(code).strip() and str(country).strip()
        )
        if isinstance(raw_codes, dict)
        else ()
    )

    return ProfileTaxonomy(
        role_families=_combined_alias_groups(
            roles.get("role_families"), expansion.get("role_families")
        ),
        software_aliases=_combined_alias_groups(
            roles.get("software_aliases"), expansion.get("software_aliases")
        ),
        sector_aliases=_combined_alias_groups(
            roles.get("sector_aliases"), expansion.get("sector_aliases")
        ),
        employment_type_aliases=_combined_alias_groups(
            roles.get("employment_type_aliases"),
            expansion.get("employment_type_aliases"),
        ),
        city_aliases=_city_groups(
            locations.get("location_aliases"), expansion.get("location_aliases")
        ),
        country_aliases=_combined_alias_groups(
            locations.get("country_aliases"), expansion.get("country_aliases")
        ),
        region_aliases=_combined_alias_groups(
            locations.get("region_aliases"), expansion.get("region_aliases")
        ),
        negative_role_terms=tuple(
            dict.fromkeys(
                _terms(roles.get("negative_role_terms"))
                + _terms(expansion.get("negative_role_terms"))
            )
        ),
        workday_country_codes=code_pairs,
    )


def _normalized_phrase(value: str) -> str:
    value = re.sub(r"\bsr\.?\b", "senior", value.lower())
    value = re.sub(r"\bjr\.?\b", "junior", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    cleaned = _normalized_phrase(phrase)
    haystack = _normalized_phrase(text)
    if not cleaned:
        return False
    pattern = re.escape(cleaned).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", haystack) is not None


def _first_match(
    text: str,
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    candidates: list[tuple[int, int, str]] = []
    for order, (canonical, aliases) in enumerate(groups):
        for alias in aliases:
            if _contains_phrase(text, alias):
                candidates.append((len(_normalized_phrase(alias)), -order, canonical))
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


def normalize_title_role(title: str, taxonomy: ProfileTaxonomy) -> str:
    title_text = _normalized_phrase(title)
    if any(_contains_phrase(title_text, term) for term in taxonomy.negative_role_terms):
        return ""
    return _first_match(title_text, taxonomy.role_families)


def normalize_role(job: JobRecord, taxonomy: ProfileTaxonomy) -> str:
    title_match = normalize_title_role(job.title, taxonomy)
    if title_match:
        return title_match
    title_text = _normalized_phrase(job.title)
    context = f"{title_text} {job.description[:2000].lower()}"
    return _first_match(context, taxonomy.role_families)


def _workday_location(
    raw_location: str,
    taxonomy: ProfileTaxonomy,
) -> tuple[str, str]:
    raw = raw_location.strip()
    if not _WORKDAY_CODE_PATTERN.match(raw):
        return "", ""
    parts = [part.strip() for part in raw.split(".") if part.strip()]
    if len(parts) < 2:
        return "", ""
    country_codes = dict(taxonomy.workday_country_codes)
    country = country_codes.get(parts[0].upper(), "")
    if not country:
        return "", ""
    city_index = 2 if len(parts) > 2 and re.fullmatch(r"[A-Z]{2,3}", parts[1]) else 1
    if city_index >= len(parts):
        return "", country
    city = re.split(r"\s+-\s+|\d", parts[city_index], maxsplit=1)[0].strip(" ,-_")
    return city, country


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

    workday_city, workday_country = _workday_location(raw_location, taxonomy)
    if workday_country:
        return workday_city, workday_country

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
