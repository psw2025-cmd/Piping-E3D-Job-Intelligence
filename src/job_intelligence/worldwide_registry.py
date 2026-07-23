from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

VALID_STATUSES = {
    "ACTIVE_DIRECT",
    "ACTIVE_GMAIL_ALERT",
    "ACTIVE_PUBLIC_NOTICE",
    "ACTIVE_MANUAL_IMPORT",
    "STAGED_NEEDS_LIVE_PROOF",
    "BLOCKED_RESTRICTED",
    "NO_SOURCE_FOUND",
}
ACTIVE_STATUSES = {
    "ACTIVE_DIRECT",
    "ACTIVE_GMAIL_ALERT",
    "ACTIVE_PUBLIC_NOTICE",
    "ACTIVE_MANUAL_IMPORT",
}
REQUIRED_FIELDS = {
    "company_id",
    "company",
    "country",
    "regions",
    "company_aliases",
    "employer_type",
    "sectors",
    "official_careers_url",
    "ats_family",
    "source_mode",
    "source_ids",
    "alert_supported",
    "priority",
    "status",
}


@dataclass(frozen=True, slots=True)
class RegistryData:
    companies: tuple[dict[str, Any], ...]
    verified_at: str


def _as_text_list(value: Any, field: str, company_id: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{company_id}: {field} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{company_id}: {field} must contain only text")
        cleaned = item.strip()
        if cleaned:
            result.append(cleaned)
    return result


def load_worldwide_registry(
    path: str | Path = "config/worldwide_companies.yaml",
) -> RegistryData:
    registry_path = Path(path)
    loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("worldwide company registry root must be a mapping")
    rows = loaded.get("companies", [])
    if not isinstance(rows, list):
        raise ValueError("worldwide company registry companies must be a list")

    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("every worldwide company entry must be a mapping")
        missing = sorted(REQUIRED_FIELDS - set(raw))
        company_id = str(raw.get("company_id", "")).strip()
        if missing:
            raise ValueError(f"{company_id or '<unknown>'}: missing {', '.join(missing)}")
        if not company_id:
            raise ValueError("company_id must not be blank")
        if company_id in seen_ids:
            raise ValueError(f"duplicate company_id: {company_id}")
        seen_ids.add(company_id)

        status = str(raw.get("status", "")).strip()
        if status not in VALID_STATUSES:
            raise ValueError(f"{company_id}: unsupported status {status!r}")
        source_ids = _as_text_list(raw.get("source_ids"), "source_ids", company_id)
        aliases = _as_text_list(raw.get("company_aliases"), "company_aliases", company_id)
        regions = _as_text_list(raw.get("regions"), "regions", company_id)
        sectors = _as_text_list(raw.get("sectors"), "sectors", company_id)
        local_entities = _as_text_list(
            raw.get("local_entities", []), "local_entities", company_id
        )
        alert_supported = raw.get("alert_supported")
        if not isinstance(alert_supported, bool):
            raise ValueError(f"{company_id}: alert_supported must be true or false")
        try:
            priority = int(raw.get("priority"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{company_id}: priority must be an integer") from exc
        if priority < 1 or priority > 3:
            raise ValueError(f"{company_id}: priority must be between 1 and 3")
        if status == "ACTIVE_DIRECT" and not source_ids:
            raise ValueError(f"{company_id}: ACTIVE_DIRECT requires source_ids")
        if status == "ACTIVE_GMAIL_ALERT" and not alert_supported:
            raise ValueError(
                f"{company_id}: ACTIVE_GMAIL_ALERT requires alert_supported=true"
            )
        official_url = str(raw.get("official_careers_url", "")).strip()
        if not official_url.startswith("https://"):
            raise ValueError(f"{company_id}: official_careers_url must use https")

        normalized = dict(raw)
        normalized.update(
            {
                "company_id": company_id,
                "company": str(raw.get("company", "")).strip(),
                "country": str(raw.get("country", "")).strip(),
                "regions": regions,
                "company_aliases": aliases,
                "local_entities": local_entities,
                "sectors": sectors,
                "source_ids": source_ids,
                "priority": priority,
                "status": status,
            }
        )
        validated.append(normalized)
    return RegistryData(tuple(validated), str(loaded.get("verified_at", "")))


def company_coverage_frame(
    path: str | Path = "config/worldwide_companies.yaml",
) -> pd.DataFrame:
    registry = load_worldwide_registry(path)
    rows: list[dict[str, Any]] = []
    for company in registry.companies:
        row = dict(company)
        for field in (
            "regions",
            "local_entities",
            "company_aliases",
            "sectors",
            "source_ids",
        ):
            row[field] = "; ".join(company.get(field, []))
        row["coverage_active"] = company["status"] in ACTIVE_STATUSES
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["priority", "country", "company"], ascending=[True, True, True]
    ).reset_index(drop=True)


def country_company_matrix(
    path: str | Path = "config/worldwide_companies.yaml",
) -> pd.DataFrame:
    frame = company_coverage_frame(path)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "country",
                "target_companies",
                "active_direct",
                "active_gmail_alert",
                "active_public_notice",
                "active_manual_import",
                "staged",
                "blocked",
                "no_source",
                "active_coverage",
                "coverage_percent",
            ]
        )
    grouped_rows: list[dict[str, Any]] = []
    for country, group in frame.groupby("country", dropna=False):
        total = len(group)
        counts = group["status"].value_counts().to_dict()
        active = int(group["status"].isin(ACTIVE_STATUSES).sum())
        grouped_rows.append(
            {
                "country": country or "Unspecified",
                "target_companies": total,
                "active_direct": counts.get("ACTIVE_DIRECT", 0),
                "active_gmail_alert": counts.get("ACTIVE_GMAIL_ALERT", 0),
                "active_public_notice": counts.get("ACTIVE_PUBLIC_NOTICE", 0),
                "active_manual_import": counts.get("ACTIVE_MANUAL_IMPORT", 0),
                "staged": counts.get("STAGED_NEEDS_LIVE_PROOF", 0),
                "blocked": counts.get("BLOCKED_RESTRICTED", 0),
                "no_source": counts.get("NO_SOURCE_FOUND", 0),
                "active_coverage": active,
                "coverage_percent": round(active * 100.0 / total, 1) if total else 0.0,
            }
        )
    return pd.DataFrame(grouped_rows).sort_values(
        ["coverage_percent", "target_companies", "country"],
        ascending=[True, False, True],
    )


def coverage_gap_frame(
    path: str | Path = "config/worldwide_companies.yaml",
) -> pd.DataFrame:
    frame = company_coverage_frame(path)
    if frame.empty:
        return frame
    return frame[~frame["status"].isin(ACTIVE_STATUSES)].sort_values(
        ["priority", "country", "company"], ascending=[True, True, True]
    )


def company_alias_frame(
    path: str | Path = "config/worldwide_companies.yaml",
) -> pd.DataFrame:
    registry = load_worldwide_registry(path)
    rows: list[dict[str, str]] = []
    for company in registry.companies:
        names = [company["company"], *company.get("local_entities", []), *company.get("company_aliases", [])]
        seen: set[str] = set()
        for name in names:
            cleaned = str(name).strip()
            key = cleaned.casefold()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "company_id": company["company_id"],
                    "canonical_company": company["company"],
                    "alias": cleaned,
                    "country": company["country"],
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["canonical_company", "alias"], ascending=[True, True]
    )


def gmail_query_groups(
    path: str | Path = "config/worldwide_companies.yaml",
    *,
    newer_than_days: int = 30,
    max_terms_per_query: int = 25,
) -> pd.DataFrame:
    if newer_than_days < 1:
        raise ValueError("newer_than_days must be >= 1")
    if max_terms_per_query < 1:
        raise ValueError("max_terms_per_query must be >= 1")
    registry = load_worldwide_registry(path)
    alert_companies = [
        company
        for company in registry.companies
        if company["alert_supported"]
        and company["status"] != "BLOCKED_RESTRICTED"
    ]
    terms = sorted(
        {
            str(name).strip()
            for company in alert_companies
            for name in [company["company"], *company.get("company_aliases", [])]
            if str(name).strip()
        },
        key=str.casefold,
    )
    rows: list[dict[str, Any]] = []
    for index in range(0, len(terms), max_terms_per_query):
        chunk = terms[index : index + max_terms_per_query]
        quoted = [f'"{term.replace(chr(34), "")}"' for term in chunk]
        query = (
            f"newer_than:{newer_than_days}d "
            "(job OR vacancy OR hiring OR career OR recruitment) "
            f"({' OR '.join(quoted)})"
        )
        rows.append(
            {
                "query_group": f"employers_{index // max_terms_per_query + 1:02d}",
                "term_count": len(chunk),
                "terms": "; ".join(chunk),
                "gmail_query": query,
            }
        )
    return pd.DataFrame(rows)
