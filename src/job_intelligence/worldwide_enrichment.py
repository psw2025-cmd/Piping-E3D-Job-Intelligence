from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_CLOSING_PATTERNS = (
    re.compile(
        r"(?:closing date|application deadline|apply by)\s*[:\-]?\s*([^\n.;]+)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:closes on|closing on)\s+([^\n.;]+)", re.IGNORECASE),
)

_ROLE_RULES = (
    (
        "Lead/Principal Piping Engineer",
        ("lead piping engineer", "principal piping engineer"),
    ),
    ("Senior Piping Engineer", ("senior piping engineer",)),
    ("Piping Engineer", ("piping engineer", "piping design engineer")),
    (
        "Piping Layout Engineer",
        ("piping layout engineer", "plant layout engineer"),
    ),
    (
        "Senior E3D/PDMS/SP3D Designer",
        ("senior e3d", "senior pdms", "senior sp3d"),
    ),
    (
        "E3D/PDMS/SP3D Piping Designer",
        ("e3d piping", "pdms piping", "sp3d piping"),
    ),
    (
        "Plant Design/Piping Designer",
        ("plant design", "plant layout designer", "piping designer"),
    ),
    ("Piping Stress Engineer", ("piping stress", "stress engineer")),
    (
        "Pipe Support Engineer",
        ("pipe support engineer", "piping support engineer"),
    ),
    (
        "Piping Materials Engineer",
        ("piping materials", "material engineer piping"),
    ),
    (
        "Site/Field Piping Engineer",
        ("site piping", "field piping", "piping field"),
    ),
    ("Offshore Piping Engineer", ("offshore piping",)),
    ("Piping Construction Engineer", ("piping construction",)),
    (
        "3D Model Coordinator",
        ("3d model coordinator", "e3d coordinator", "model coordinator"),
    ),
)

_COUNTRY_RULES = (
    (
        "India",
        (
            "india",
            "mumbai",
            "pune",
            "vadodara",
            "chennai",
            "bengaluru",
            "hyderabad",
            "gurugram",
            "noida",
            "delhi",
            "dahej",
            "hazira",
            "jamnagar",
        ),
    ),
    (
        "United Arab Emirates",
        ("united arab emirates", "uae", "abu dhabi", "dubai", "sharjah"),
    ),
    (
        "Saudi Arabia",
        ("saudi arabia", "al khobar", "khobar", "dammam", "riyadh"),
    ),
    ("Qatar", ("qatar", "doha")),
    ("Oman", ("oman", "muscat")),
    ("Kuwait", ("kuwait",)),
    ("Bahrain", ("bahrain",)),
    (
        "United Kingdom",
        ("united kingdom", "uk", "england", "scotland", "wales"),
    ),
    ("Canada", ("canada",)),
    ("United States", ("united states", "usa", "u.s.")),
    ("Australia", ("australia",)),
    ("Singapore", ("singapore",)),
    ("Malaysia", ("malaysia",)),
    ("Norway", ("norway",)),
    ("Netherlands", ("netherlands",)),
    ("France", ("france",)),
    ("Germany", ("germany",)),
    ("Italy", ("italy",)),
    ("South Korea", ("south korea", "korea")),
    ("Japan", ("japan",)),
    ("Nigeria", ("nigeria",)),
    ("South Africa", ("south africa",)),
    ("Egypt", ("egypt",)),
)

_SECTOR_RULES = (
    ("Nuclear", ("nuclear", "fusion", "iter")),
    ("Offshore", ("offshore", "subsea", "fpso", "platform")),
    ("LNG", ("lng", "liquefied natural gas")),
    (
        "Refinery/Petrochemical",
        ("refinery", "petrochemical", "hydrocarbon", "chemical plant"),
    ),
    ("Oil & Gas", ("oil and gas", "oil & gas", "upstream", "downstream")),
    (
        "Power/Energy",
        ("power plant", "energy", "renewable", "hydrogen", "carbon capture"),
    ),
    ("Mining & Metals", ("mining", "metals", "mineral processing")),
    ("Pharmaceutical", ("pharma", "pharmaceutical")),
    ("Industrial", ("industrial plant", "manufacturing facility")),
)

_SOFTWARE_RULES = (
    ("AVEVA E3D", ("aveva e3d", " e3d ")),
    ("PDMS", ("pdms",)),
    ("SP3D", ("sp3d", "smartplant 3d")),
    ("AutoCAD", ("autocad",)),
    ("Navisworks", ("navisworks",)),
    ("MicroStation", ("microstation",)),
    ("SmartPlant Review", ("smartplant review", "spr")),
    ("CAESAR II", ("caesar ii", "caesar 2")),
)

_ENRICHED_COLUMNS = (
    "normalized_role",
    "country",
    "sector",
    "software",
    "closing_date",
    "employment_type",
    "remote_type",
    "source_category",
    "duplicate_group",
)
_AGGREGATE_COLUMNS = ("source_count", "duplicate_sources", "all_apply_urls")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _searchable(row: pd.Series) -> str:
    return " ".join(
        _text(row.get(column))
        for column in (
            "title",
            "company",
            "location",
            "description",
            "skills_text",
            "experience_text",
            "source_name",
        )
        if _text(row.get(column))
    ).lower()


def _first_rule(
    text: str,
    rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    padded = f" {text} "
    for label, terms in rules:
        if any(term in padded for term in terms):
            return label
    return ""


def _all_rules(
    text: str,
    rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    padded = f" {text} "
    found = [label for label, terms in rules if any(term in padded for term in terms)]
    return "; ".join(dict.fromkeys(found))


def _closing_date(text: str) -> str:
    for pattern in _CLOSING_PATTERNS:
        match = pattern.search(text)
        if match:
            return _SPACE_RE.sub(" ", match.group(1)).strip()[:80]
    return ""


def _source_category(source_name: str) -> str:
    lowered = source_name.lower()
    if lowered.startswith("private:") or "gmail" in lowered or "email" in lowered:
        return "Private/Authorized Alert"
    recruiter_terms = ("airswift", "nes fircroft", "brunel", "petroplan")
    if any(term in lowered for term in recruiter_terms):
        return "Recruiter"
    if lowered == "manual":
        return "Manual"
    return "Official Employer"


def _remote_type(text: str) -> str:
    padded = f" {text} "
    if " remote " in padded:
        return "Remote"
    if " hybrid " in padded:
        return "Hybrid"
    return "On-site/Unspecified"


def _normalize(value: str) -> str:
    return " ".join(_NON_ALNUM_RE.sub(" ", value.lower()).split())


def duplicate_group(row: pd.Series) -> str:
    title = _normalize(_text(row.get("title")))
    company = _normalize(_text(row.get("company")))
    location = _normalize(_text(row.get("location")))
    published = _text(row.get("published_at"))[:10]
    if not published:
        published = _normalize(_text(row.get("description")))[:120]
    raw = "|".join((title, company, location, published))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def enrich_jobs_frame(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    if enriched.empty:
        for column in _ENRICHED_COLUMNS:
            enriched[column] = pd.Series(dtype="string")
        return enriched

    searchable = enriched.apply(_searchable, axis=1)
    enriched["normalized_role"] = searchable.map(
        lambda text: _first_rule(text, _ROLE_RULES)
    )
    enriched["country"] = searchable.map(
        lambda text: _first_rule(text, _COUNTRY_RULES)
    )
    enriched["sector"] = searchable.map(
        lambda text: _first_rule(text, _SECTOR_RULES)
    )
    enriched["software"] = searchable.map(
        lambda text: _all_rules(text, _SOFTWARE_RULES)
    )
    enriched["closing_date"] = searchable.map(_closing_date)
    enriched["employment_type"] = enriched.get(
        "job_type",
        pd.Series(dtype="string"),
    )
    enriched["remote_type"] = searchable.map(_remote_type)
    enriched["source_category"] = (
        enriched.get("source_name", pd.Series(dtype="string"))
        .fillna("")
        .astype(str)
        .map(_source_category)
    )
    enriched["duplicate_group"] = enriched.apply(duplicate_group, axis=1)
    return enriched


def _empty_deduplicated(enriched: pd.DataFrame) -> pd.DataFrame:
    empty = enriched.copy()
    empty["source_count"] = pd.Series(dtype="int64")
    empty["duplicate_sources"] = pd.Series(dtype="string")
    empty["all_apply_urls"] = pd.Series(dtype="string")
    return empty


def deduplicate_worldwide(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched = enrich_jobs_frame(frame)
    if enriched.empty:
        return _empty_deduplicated(enriched), enriched.copy()

    grouped = enriched.groupby("duplicate_group", dropna=False)
    counts = grouped.size().rename("source_count")
    source_names = grouped["source_name"].agg(
        lambda values: "; ".join(
            sorted({str(value) for value in values if str(value)})
        )
    ).rename("duplicate_sources")
    source_urls = grouped["apply_url"].agg(
        lambda values: "\n".join(
            dict.fromkeys(str(value) for value in values if str(value))
        )
    ).rename("all_apply_urls")

    ranked = enriched.copy()
    ranked["_score"] = pd.to_numeric(
        ranked.get("match_score", 0),
        errors="coerce",
    ).fillna(0)
    ranked["_published"] = ranked.get("published_at", "").fillna("").astype(str)
    ranked = ranked.sort_values(
        ["duplicate_group", "_score", "_published", "last_seen_at"],
        ascending=[True, False, False, False],
    )
    deduplicated = ranked.drop_duplicates("duplicate_group", keep="first").drop(
        columns=["_score", "_published"]
    )
    deduplicated = deduplicated.join(counts, on="duplicate_group")
    deduplicated = deduplicated.join(source_names, on="duplicate_group")
    deduplicated = deduplicated.join(source_urls, on="duplicate_group")
    deduplicated = deduplicated.sort_values(
        ["match_score", "published_at", "company", "title"],
        ascending=[False, False, True, True],
    )

    duplicate_groups = set(counts[counts > 1].index)
    variants = enriched[enriched["duplicate_group"].isin(duplicate_groups)].copy()
    variants = variants.join(counts, on="duplicate_group")
    variants = variants.sort_values(
        ["duplicate_group", "source_name", "company", "title"]
    )
    return deduplicated, variants


def registry_frames(
    config_dir: str | Path = "config",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(config_dir)

    def load_rows(name: str, key: str) -> pd.DataFrame:
        path = root / name
        if not path.exists():
            return pd.DataFrame()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = loaded.get(key, []) if isinstance(loaded, dict) else []
        return pd.json_normalize(rows) if isinstance(rows, list) else pd.DataFrame()

    return (
        load_rows("employer_registry.yaml", "employers"),
        load_rows("recruiters.yaml", "recruiters"),
    )


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame.get(column, pd.Series(dtype="string"))


def daily_summary_frame(
    jobs: pd.DataFrame,
    deduplicated: pd.DataFrame,
    source_health: pd.DataFrame,
) -> pd.DataFrame:
    high_priority = int(
        _series(deduplicated, "priority").isin(["critical", "high"]).sum()
    )
    countries = int(
        _series(deduplicated, "country").replace("", pd.NA).nunique()
    )
    employers = int(
        _series(deduplicated, "company").replace("", pd.NA).nunique()
    )
    passing = int(
        _series(source_health, "status")
        .isin(["pass", "pass_with_warnings"])
        .sum()
    )
    failing = int(_series(source_health, "status").eq("fail").sum())
    metrics = [
        ("Generated UTC", pd.Timestamp.now(tz="UTC").isoformat()),
        ("Raw active rows", len(jobs)),
        ("Worldwide deduplicated jobs", len(deduplicated)),
        ("Duplicate variants removed", max(len(jobs) - len(deduplicated), 0)),
        ("Critical/high priority", high_priority),
        ("Countries represented", countries),
        ("Employers represented", employers),
        ("Sources passing", passing),
        ("Sources failing", failing),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value"])
