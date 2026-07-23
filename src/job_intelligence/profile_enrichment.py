from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from .database import connect, init_database
from .models import JobRecord, utc_now_iso

_SPACE_RE = re.compile(r"\s+")
_EXPERIENCE_RE = re.compile(
    r"\b(?:minimum\s+of\s+|min(?:imum)?\.?\s*)?"
    r"(?P<minimum>\d{1,2})(?:\s*[-–to]+\s*(?P<maximum>\d{1,2}))?"
    r"\s*\+?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_CLOSING_PATTERNS = (
    re.compile(
        r"(?:closing\s+date|application\s+deadline|apply\s+by|deadline)\s*[:\-]?\s*"
        r"(?P<value>[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    ),
)
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%b %d %Y",
)


@dataclass(frozen=True, slots=True)
class Taxonomy:
    role_families: dict[str, tuple[str, ...]]
    software_aliases: dict[str, tuple[str, ...]]
    sector_aliases: dict[str, tuple[str, ...]]
    location_aliases: dict[str, tuple[str, str]]
    country_aliases: dict[str, str]
    employment_aliases: dict[str, tuple[str, ...]]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"configuration root must be a mapping: {path}")
    return loaded


def _text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        _normalize(str(item)) for item in value if isinstance(item, str) and item.strip()
    )


def _normalize(value: str) -> str:
    return _SPACE_RE.sub(" ", value.casefold().replace("&", " and ")).strip()


def _mapping_aliases(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, tuple[str, ...]] = {}
    for canonical, aliases in value.items():
        canonical_text = str(canonical).strip()
        if not canonical_text:
            continue
        normalized_aliases = _text_list(aliases)
        output[canonical_text] = tuple(
            dict.fromkeys((_normalize(canonical_text), *normalized_aliases))
        )
    return output


def load_taxonomy(config_dir: str | Path = "config") -> Taxonomy:
    root = Path(config_dir)
    roles = _read_yaml(root / "roles.yaml")
    locations = _read_yaml(root / "locations.yaml")
    taxonomy = _read_yaml(root / "taxonomy.yaml")

    role_families = _mapping_aliases(roles.get("role_families"))
    if not role_families:
        role_families = {
            role: (_normalize(role),)
            for role in roles.get("target_roles", [])
            if isinstance(role, str) and role.strip()
        }

    location_aliases: dict[str, tuple[str, str]] = {}
    raw_locations = locations.get("location_aliases", {})
    if isinstance(raw_locations, dict):
        for alias, details in raw_locations.items():
            if not isinstance(details, dict):
                continue
            city = str(details.get("city", "")).strip()
            country = str(details.get("country", "")).strip()
            if city or country:
                location_aliases[_normalize(str(alias))] = (city, country)

    country_aliases: dict[str, str] = {}
    raw_countries = locations.get("country_aliases", {})
    if isinstance(raw_countries, dict):
        for alias, country in raw_countries.items():
            country_text = str(country).strip()
            if country_text:
                country_aliases[_normalize(str(alias))] = country_text

    return Taxonomy(
        role_families=role_families,
        software_aliases=_mapping_aliases(taxonomy.get("software_aliases")),
        sector_aliases=_mapping_aliases(taxonomy.get("sector_aliases")),
        location_aliases=location_aliases,
        country_aliases=country_aliases,
        employment_aliases=_mapping_aliases(taxonomy.get("employment_aliases")),
    )


def _first_matching_canonical(
    text: str,
    mapping: dict[str, tuple[str, ...]],
) -> str:
    for canonical, aliases in mapping.items():
        if any(alias and alias in text for alias in aliases):
            return canonical
    return ""


def _all_matching_canonicals(
    text: str,
    mapping: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    return tuple(
        canonical
        for canonical, aliases in mapping.items()
        if any(alias and alias in text for alias in aliases)
    )


def _normalize_location(job: JobRecord, taxonomy: Taxonomy) -> tuple[str, str]:
    location_text = _normalize(job.location)
    broader_text = _normalize(f"{job.location} {job.description}")
    matches = sorted(
        (
            (alias, details)
            for alias, details in taxonomy.location_aliases.items()
            if alias and alias in location_text
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    if matches:
        return matches[0][1]

    for alias, country in sorted(
        taxonomy.country_aliases.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if alias and alias in broader_text:
            return "", country
    return "", ""


def _closing_date(text: str) -> str:
    for pattern in _CLOSING_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = _SPACE_RE.sub(" ", match.group("value")).strip()
        for date_format in _DATE_FORMATS:
            try:
                return datetime.strptime(raw, date_format).date().isoformat()
            except ValueError:
                continue
    return ""


def _experience_required(job: JobRecord) -> str:
    if job.experience_text.strip():
        return job.experience_text.strip()
    match = _EXPERIENCE_RE.search(job.searchable_text)
    if not match:
        return ""
    minimum = match.group("minimum")
    maximum = match.group("maximum")
    return f"{minimum}-{maximum} years" if maximum else f"{minimum}+ years"


def enrich_job(job: JobRecord, taxonomy: Taxonomy) -> dict[str, str]:
    title_text = _normalize(job.title)
    searchable = _normalize(job.searchable_text)
    normalized_role = _first_matching_canonical(title_text, taxonomy.role_families)
    if not normalized_role:
        normalized_role = _first_matching_canonical(searchable, taxonomy.role_families)
    city, country = _normalize_location(job, taxonomy)
    software = "; ".join(_all_matching_canonicals(searchable, taxonomy.software_aliases))
    sectors = _all_matching_canonicals(searchable, taxonomy.sector_aliases)
    employment = _first_matching_canonical(
        _normalize(f"{job.job_type} {job.description}"),
        taxonomy.employment_aliases,
    )
    return {
        "normalized_role": normalized_role,
        "city": city,
        "country": country,
        "closing_date": _closing_date(job.description),
        "experience_required": _experience_required(job),
        "software": software,
        "sector": "; ".join(sectors),
        "employment_mode": employment or job.job_type,
    }


def init_enrichment_tables(db_path: str | Path) -> None:
    init_database(db_path)
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS job_observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT NOT NULL,
                source_id TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(job_key, source_id, source_name, source_url)
            );

            CREATE INDEX IF NOT EXISTS idx_job_observations_key
                ON job_observations(job_key);

            CREATE TABLE IF NOT EXISTS job_enrichment (
                job_key TEXT PRIMARY KEY,
                normalized_role TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT '',
                source_names TEXT NOT NULL DEFAULT '',
                closing_date TEXT NOT NULL DEFAULT '',
                experience_required TEXT NOT NULL DEFAULT '',
                software TEXT NOT NULL DEFAULT '',
                sector TEXT NOT NULL DEFAULT '',
                employment_mode TEXT NOT NULL DEFAULT '',
                canonical_job_key TEXT NOT NULL DEFAULT '',
                duplicate_status TEXT NOT NULL DEFAULT 'unique',
                duplicate_source_count INTEGER NOT NULL DEFAULT 1,
                enriched_at TEXT NOT NULL
            );
            """
        )


def record_job_observations(
    db_path: str | Path,
    jobs: Iterable[JobRecord],
    *,
    source_id: str,
    source_type: str,
) -> None:
    init_enrichment_tables(db_path)
    now = utc_now_iso()
    rows = []
    for job in jobs:
        if not job.job_key:
            raise ValueError("job_key must be allocated before recording observations")
        rows.append(
            (
                job.job_key,
                source_id,
                job.source_name,
                source_type,
                job.source_url or job.apply_url,
                job.found_at or now,
                job.last_seen_at or now,
            )
        )
    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO job_observations (
                job_key, source_id, source_name, source_type, source_url,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_key, source_id, source_name, source_url) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                source_type=COALESCE(NULLIF(excluded.source_type, ''), source_type)
            """,
            rows,
        )


def _ensure_default_observations(db_path: str | Path) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO job_observations (
                job_key, source_id, source_name, source_type, source_url,
                first_seen_at, last_seen_at
            )
            SELECT
                jobs.job_key,
                '',
                jobs.source_name,
                CASE
                    WHEN lower(jobs.source_name) LIKE '%manual%' THEN 'manual'
                    WHEN lower(jobs.source_name) LIKE '%private%' THEN 'private_import'
                    ELSE 'unknown'
                END,
                COALESCE(NULLIF(jobs.source_url, ''), jobs.apply_url),
                jobs.found_at,
                jobs.last_seen_at
            FROM jobs
            LEFT JOIN job_observations
                ON job_observations.job_key = jobs.job_key
            WHERE job_observations.job_key IS NULL
            """
        )


def refresh_job_enrichment(
    db_path: str | Path,
    config_dir: str | Path = "config",
) -> None:
    init_enrichment_tables(db_path)
    _ensure_default_observations(db_path)
    taxonomy = load_taxonomy(config_dir)
    with connect(db_path) as connection:
        jobs = connection.execute("SELECT * FROM jobs").fetchall()
        for row in jobs:
            job = JobRecord(
                title=str(row["title"]),
                company=str(row["company"]),
                location=str(row["location"]),
                description=str(row["description"]),
                apply_url=str(row["apply_url"]),
                source_url=str(row["source_url"]),
                source_name=str(row["source_name"]),
                published_at=str(row["published_at"]),
                found_at=str(row["found_at"]),
                last_seen_at=str(row["last_seen_at"]),
                job_type=str(row["job_type"]),
                salary_text=str(row["salary_text"]),
                experience_text=str(row["experience_text"]),
                skills_text=str(row["skills_text"]),
                job_key=str(row["job_key"]),
            )
            enriched = enrich_job(job, taxonomy)
            observations = connection.execute(
                """
                SELECT source_name, source_type
                FROM job_observations
                WHERE job_key = ?
                ORDER BY first_seen_at, observation_id
                """,
                (job.job_key,),
            ).fetchall()
            source_names = tuple(
                dict.fromkeys(str(item["source_name"]) for item in observations if item["source_name"])
            )
            source_types = tuple(
                dict.fromkeys(str(item["source_type"]) for item in observations if item["source_type"])
            )
            source_count = max(len(source_names), 1)
            connection.execute(
                """
                INSERT INTO job_enrichment (
                    job_key, normalized_role, city, country, source_type,
                    source_names, closing_date, experience_required, software,
                    sector, employment_mode, canonical_job_key, duplicate_status,
                    duplicate_source_count, enriched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_key) DO UPDATE SET
                    normalized_role=excluded.normalized_role,
                    city=excluded.city,
                    country=excluded.country,
                    source_type=excluded.source_type,
                    source_names=excluded.source_names,
                    closing_date=excluded.closing_date,
                    experience_required=excluded.experience_required,
                    software=excluded.software,
                    sector=excluded.sector,
                    employment_mode=excluded.employment_mode,
                    canonical_job_key=excluded.canonical_job_key,
                    duplicate_status=excluded.duplicate_status,
                    duplicate_source_count=excluded.duplicate_source_count,
                    enriched_at=excluded.enriched_at
                """,
                (
                    job.job_key,
                    enriched["normalized_role"],
                    enriched["city"],
                    enriched["country"],
                    "; ".join(source_types),
                    "; ".join(source_names),
                    enriched["closing_date"],
                    enriched["experience_required"],
                    enriched["software"],
                    enriched["sector"],
                    enriched["employment_mode"],
                    job.job_key,
                    "cross_source" if source_count > 1 else "unique",
                    source_count,
                    utc_now_iso(),
                ),
            )
        connection.execute(
            "DELETE FROM job_enrichment WHERE job_key NOT IN (SELECT job_key FROM jobs)"
        )
        connection.execute(
            "DELETE FROM job_observations WHERE job_key NOT IN (SELECT job_key FROM jobs)"
        )


def fetch_enriched_jobs(db_path: str | Path) -> list[dict[str, object]]:
    init_enrichment_tables(db_path)
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                jobs.*,
                enrichment.normalized_role,
                enrichment.city,
                enrichment.country,
                enrichment.source_type,
                enrichment.source_names,
                enrichment.closing_date,
                enrichment.experience_required,
                enrichment.software,
                enrichment.sector,
                enrichment.employment_mode,
                enrichment.canonical_job_key,
                enrichment.duplicate_status,
                enrichment.duplicate_source_count,
                enrichment.enriched_at
            FROM jobs
            LEFT JOIN job_enrichment AS enrichment
                ON enrichment.job_key = jobs.job_key
            ORDER BY jobs.found_at DESC, jobs.company, jobs.title
            """
        ).fetchall()
    return [dict(row) for row in rows]


def verify_enrichment(db_path: str | Path) -> list[str]:
    init_enrichment_tables(db_path)
    errors: list[str] = []
    with connect(db_path) as connection:
        missing = connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            LEFT JOIN job_enrichment ON job_enrichment.job_key = jobs.job_key
            WHERE job_enrichment.job_key IS NULL
            """
        ).fetchone()[0]
        if missing:
            errors.append(f"Jobs missing enrichment rows: {missing}")
        orphan_enrichment = connection.execute(
            """
            SELECT COUNT(*)
            FROM job_enrichment
            LEFT JOIN jobs ON jobs.job_key = job_enrichment.job_key
            WHERE jobs.job_key IS NULL
            """
        ).fetchone()[0]
        if orphan_enrichment:
            errors.append(f"Orphan enrichment rows: {orphan_enrichment}")
        orphan_observations = connection.execute(
            """
            SELECT COUNT(*)
            FROM job_observations
            LEFT JOIN jobs ON jobs.job_key = job_observations.job_key
            WHERE jobs.job_key IS NULL
            """
        ).fetchone()[0]
        if orphan_observations:
            errors.append(f"Orphan job observations: {orphan_observations}")
    return errors
