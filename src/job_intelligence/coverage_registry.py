from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
import yaml

COVERAGE_STATUSES = {
    "ACTIVE_DIRECT",
    "ACTIVE_GMAIL_ALERT",
    "ACTIVE_PUBLIC_NOTICE",
    "ACTIVE_MANUAL_IMPORT",
    "STAGED_NEEDS_LIVE_PROOF",
    "BLOCKED_RESTRICTED",
    "NO_SOURCE_FOUND",
}
COVERED_STATUSES = {
    "ACTIVE_DIRECT",
    "ACTIVE_GMAIL_ALERT",
    "ACTIVE_PUBLIC_NOTICE",
    "ACTIVE_MANUAL_IMPORT",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"configuration root must be a mapping: {path}")
    return loaded


def _text_list(value: Any, field: str, company_id: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"company {company_id!r} field {field!r} must be a list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"company {company_id!r} field {field!r} must not be empty")
    return result


def _optional_text_list(value: Any, field: str, company_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"company {company_id!r} field {field!r} must be a list")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(
            f"company {company_id!r} field {field!r} must contain only text"
        )
    return [item.strip() for item in value if item.strip()]


def _validate_public_url(value: str, field: str, company_id: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(
            f"company {company_id!r} field {field!r} must be a public HTTPS URL"
        )
    if parsed.username or parsed.password:
        raise ValueError(f"company {company_id!r} URL must not contain credentials")


def load_worldwide_companies(
    path: str | Path = "config/worldwide_companies.yaml",
) -> list[dict[str, Any]]:
    config_path = Path(path)
    loaded = _load_yaml(config_path)
    raw_companies = loaded.get("companies", [])
    if not isinstance(raw_companies, list):
        raise ValueError("worldwide companies must be a list")

    required_text = (
        "company_id",
        "company",
        "country",
        "employer_type",
        "official_careers_url",
        "ats_family",
        "source_mode",
        "status",
        "verified_at",
    )
    companies: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for raw in raw_companies:
        if not isinstance(raw, dict):
            raise ValueError("each worldwide company entry must be a mapping")
        company_id = str(raw.get("company_id", "")).strip()
        for field in required_text:
            if not str(raw.get(field, "")).strip():
                raise ValueError(f"company {company_id!r} requires {field!r}")
        if company_id in seen_ids:
            raise ValueError(f"duplicate company_id: {company_id}")
        normalized_name = str(raw["company"]).strip().casefold()
        if normalized_name in seen_names:
            raise ValueError(f"duplicate company name: {raw['company']}")
        seen_ids.add(company_id)
        seen_names.add(normalized_name)

        status = str(raw["status"]).strip()
        if status not in COVERAGE_STATUSES:
            raise ValueError(f"company {company_id!r} has unsupported status {status!r}")
        _validate_public_url(
            str(raw["official_careers_url"]).strip(),
            "official_careers_url",
            company_id,
        )
        regions = _text_list(raw.get("regions"), "regions", company_id)
        sectors = _text_list(raw.get("sectors"), "sectors", company_id)
        aliases = _text_list(raw.get("company_aliases"), "company_aliases", company_id)
        local_entities = _optional_text_list(
            raw.get("local_entities"), "local_entities", company_id
        )
        source_ids = _optional_text_list(raw.get("source_ids"), "source_ids", company_id)
        alert_supported = raw.get("alert_supported")
        if not isinstance(alert_supported, bool):
            raise ValueError(f"company {company_id!r} alert_supported must be boolean")
        try:
            priority = int(raw.get("priority", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"company {company_id!r} priority must be an integer") from exc
        if priority not in {1, 2, 3}:
            raise ValueError(f"company {company_id!r} priority must be 1, 2 or 3")
        if status == "ACTIVE_DIRECT" and not source_ids:
            raise ValueError(f"company {company_id!r} ACTIVE_DIRECT requires source_ids")
        if status == "ACTIVE_GMAIL_ALERT" and not alert_supported:
            raise ValueError(
                f"company {company_id!r} ACTIVE_GMAIL_ALERT requires alert_supported"
            )

        entry = dict(raw)
        entry.update(
            {
                "company_id": company_id,
                "company": str(raw["company"]).strip(),
                "regions": regions,
                "sectors": sectors,
                "company_aliases": aliases,
                "local_entities": local_entities,
                "source_ids": source_ids,
                "priority": priority,
                "alert_supported": alert_supported,
            }
        )
        companies.append(entry)
    return companies


def load_gmail_query_groups(
    path: str | Path = "config/gmail_query_groups.yaml",
) -> list[dict[str, Any]]:
    loaded = _load_yaml(Path(path))
    raw_groups = loaded.get("query_groups", [])
    if not isinstance(raw_groups, list):
        raise ValueError("Gmail query_groups must be a list")
    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_groups:
        if not isinstance(raw, dict):
            raise ValueError("each Gmail query group must be a mapping")
        group_id = str(raw.get("id", "")).strip()
        name = str(raw.get("name", "")).strip()
        query = " ".join(str(raw.get("query", "")).split())
        if not group_id or not name or not query:
            raise ValueError("Gmail query group requires id, name and query")
        if group_id in seen:
            raise ValueError(f"duplicate Gmail query group: {group_id}")
        seen.add(group_id)
        enabled = raw.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError(f"Gmail query group {group_id!r} enabled must be boolean")
        max_messages = int(raw.get("max_messages", 200))
        if not 1 <= max_messages <= 1000:
            raise ValueError(
                f"Gmail query group {group_id!r} max_messages must be 1..1000"
            )
        groups.append(
            {
                "id": group_id,
                "name": name,
                "enabled": enabled,
                "max_messages": max_messages,
                "query": query,
            }
        )
    return groups


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _company_job_mask(jobs: pd.DataFrame, entry: dict[str, Any]) -> pd.Series:
    if jobs.empty or "company" not in jobs.columns:
        return pd.Series(False, index=jobs.index, dtype=bool)
    aliases = {_normalize(entry["company"])}
    aliases.update(_normalize(value) for value in entry["company_aliases"])
    aliases.update(_normalize(value) for value in entry["local_entities"])
    companies = jobs["company"].fillna("").map(_normalize)
    return companies.isin(aliases)


def _source_health_by_company(
    source_health: pd.DataFrame,
    source_ids: list[str],
) -> tuple[str, str, int]:
    if not source_ids or source_health.empty or "source_id" not in source_health.columns:
        return "", "", 0
    matching = source_health[source_health["source_id"].isin(source_ids)]
    if matching.empty:
        return "", "", 0
    successes = matching.get("last_success_at", pd.Series(dtype="string")).fillna("")
    attempts = matching.get("last_attempt_at", pd.Series(dtype="string")).fillna("")
    passing = matching.get("status", pd.Series(dtype="string")).isin(
        ["pass", "pass_with_warnings"]
    )
    return successes.max(), attempts.max(), int(passing.sum())


def _serialize_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value or "")


def _recommended_action(status: str, source_mode: str) -> str:
    if status == "STAGED_NEEDS_LIVE_PROOF":
        return "Run bounded live contract proof, retain evidence, then enable only after tests pass."
    if status == "BLOCKED_RESTRICTED":
        return "Use authorized Gmail alerts or private EML/PDF/image import; do not bypass restrictions."
    if status == "NO_SOURCE_FOUND":
        return "Verify official careers site, talent community, public notices and recruiter channels."
    if source_mode == "public_notice":
        return "Implement HTML/PDF notice collector with closing-date and corrigendum tracking."
    if source_mode == "gmail_alert":
        return "Authorize Gmail locally and prove employer/portal alert query coverage."
    if source_mode == "manual_import":
        return "Retain official files locally and route uncertain extraction to Manual_Review."
    return "Maintain health checks and evidence proof."


def coverage_frames(
    jobs: pd.DataFrame,
    source_health: pd.DataFrame,
    *,
    config_dir: str | Path = "config",
) -> dict[str, pd.DataFrame]:
    root = Path(config_dir)
    companies = load_worldwide_companies(root / "worldwide_companies.yaml")
    query_groups = load_gmail_query_groups(root / "gmail_query_groups.yaml")
    now = datetime.now(UTC)
    today = now.date()
    thirty_days_ago = now - timedelta(days=30)
    rows: list[dict[str, Any]] = []

    found_at = pd.to_datetime(
        jobs.get("found_at", pd.Series(index=jobs.index, dtype="string")),
        errors="coerce",
        utc=True,
    )
    for entry in companies:
        mask = _company_job_mask(jobs, entry)
        company_jobs = jobs[mask]
        company_found = found_at[mask]
        last_success, last_attempt, passing_sources = _source_health_by_company(
            source_health,
            entry["source_ids"],
        )
        registry_success = str(entry.get("last_success_at", "")).strip()
        registry_seen = str(entry.get("last_job_seen_at", "")).strip()
        last_job_seen = ""
        if not company_jobs.empty and "last_seen_at" in company_jobs.columns:
            last_job_seen = company_jobs["last_seen_at"].fillna("").astype(str).max()
        rows.append(
            {
                **entry,
                "configured_source_count": len(entry["source_ids"]),
                "passing_source_count": passing_sources,
                "last_success_at": last_success or registry_success,
                "last_attempt_at": last_attempt,
                "last_job_seen_at": last_job_seen or registry_seen,
                "jobs_found_today": int(
                    (company_found.dt.date == today).fillna(False).sum()
                ),
                "jobs_found_30d": int(
                    (company_found >= thirty_days_ago).fillna(False).sum()
                ),
                "coverage_active": entry["status"] in COVERED_STATUSES,
                "recommended_next_action": _recommended_action(
                    entry["status"], str(entry["source_mode"])
                ),
            }
        )

    registry = pd.DataFrame(rows)
    for column in (
        "regions",
        "local_entities",
        "company_aliases",
        "sectors",
        "source_ids",
    ):
        registry[column] = registry[column].map(_serialize_list)

    country_rows: list[dict[str, Any]] = []
    for country, frame in registry.groupby("country", dropna=False):
        total = len(frame)
        active_direct = int(frame["status"].eq("ACTIVE_DIRECT").sum())
        active_gmail = int(frame["status"].eq("ACTIVE_GMAIL_ALERT").sum())
        active_notice = int(frame["status"].eq("ACTIVE_PUBLIC_NOTICE").sum())
        active_manual = int(frame["status"].eq("ACTIVE_MANUAL_IMPORT").sum())
        staged = int(frame["status"].eq("STAGED_NEEDS_LIVE_PROOF").sum())
        blocked = int(frame["status"].eq("BLOCKED_RESTRICTED").sum())
        no_source = int(frame["status"].eq("NO_SOURCE_FOUND").sum())
        covered = active_direct + active_gmail + active_notice + active_manual
        country_rows.append(
            {
                "country": country,
                "total_target_companies": total,
                "active_direct_sources": active_direct,
                "active_gmail_sources": active_gmail,
                "public_notice_sources": active_notice,
                "manual_import_sources": active_manual,
                "staged_sources": staged,
                "blocked_sources": blocked,
                "no_source_found": no_source,
                "jobs_found_today": int(frame["jobs_found_today"].sum()),
                "jobs_found_30d": int(frame["jobs_found_30d"].sum()),
                "last_successful_scan": frame["last_success_at"].max(),
                "coverage_percentage": round(covered * 100 / total, 1) if total else 0,
            }
        )
    country_coverage = pd.DataFrame(country_rows).sort_values(
        ["coverage_percentage", "total_target_companies", "country"],
        ascending=[True, False, True],
    )

    status_gap = registry[~registry["status"].isin(COVERED_STATUSES)].copy()
    missing_companies = status_gap[
        [
            "company_id",
            "company",
            "country",
            "priority",
            "status",
            "official_careers_url",
            "ats_family",
            "recommended_next_action",
        ]
    ].sort_values(["priority", "country", "company"])

    ats_coverage = (
        registry.groupby("ats_family", dropna=False)
        .agg(
            target_companies=("company_id", "count"),
            active_direct=("status", lambda values: int((values == "ACTIVE_DIRECT").sum())),
            active_alternative=(
                "status",
                lambda values: int(values.isin(COVERED_STATUSES - {"ACTIVE_DIRECT"}).sum()),
            ),
            staged=(
                "status",
                lambda values: int((values == "STAGED_NEEDS_LIVE_PROOF").sum()),
            ),
            blocked=(
                "status",
                lambda values: int(values.isin(["BLOCKED_RESTRICTED", "NO_SOURCE_FOUND"]).sum()),
            ),
        )
        .reset_index()
        .sort_values(["active_direct", "target_companies"], ascending=[False, False])
    )

    portal_alert_coverage = pd.DataFrame(query_groups).sort_values(["enabled", "id"], ascending=[False, True])

    recruiter_path = root / "recruiters.yaml"
    recruiter_loaded = _load_yaml(recruiter_path) if recruiter_path.exists() else {}
    recruiter_rows = recruiter_loaded.get("recruiters", [])
    recruiter_status = (
        pd.json_normalize(recruiter_rows) if isinstance(recruiter_rows, list) else pd.DataFrame()
    )
    for column in recruiter_status.columns:
        recruiter_status[column] = recruiter_status[column].map(_serialize_list)

    psu_notices = registry[registry["source_mode"].eq("public_notice")].copy()
    source_discovery = registry[
        registry["status"].isin(["STAGED_NEEDS_LIVE_PROOF", "NO_SOURCE_FOUND"])
    ].copy()
    blocked_sources = registry[registry["status"].eq("BLOCKED_RESTRICTED")].copy()

    stale_cutoff = now - timedelta(days=7)
    success_dates = pd.to_datetime(registry["last_success_at"], errors="coerce", utc=True)
    stale_mask = registry["status"].eq("ACTIVE_DIRECT") & (
        success_dates.isna() | (success_dates < stale_cutoff)
    )
    stale_sources = registry[stale_mask].copy()

    aliases: list[dict[str, str]] = []
    for entry in companies:
        for alias in dict.fromkeys(
            [entry["company"], *entry["company_aliases"], *entry["local_entities"]]
        ):
            aliases.append(
                {
                    "company_id": entry["company_id"],
                    "company": entry["company"],
                    "alias": alias,
                    "normalized_alias": _normalize(alias),
                }
            )
    alias_frame = pd.DataFrame(aliases).sort_values(["company", "alias"])

    matrix_columns = [
        "country",
        "company",
        "priority",
        "employer_type",
        "sectors",
        "status",
        "source_mode",
        "ats_family",
        "official_careers_url",
        "jobs_found_today",
        "jobs_found_30d",
        "last_success_at",
        "last_job_seen_at",
    ]
    company_matrix = registry[matrix_columns].sort_values(
        ["country", "priority", "company"]
    )

    coverage_gaps = missing_companies.copy()
    coverage_gaps["gap_type"] = coverage_gaps["status"].map(
        {
            "STAGED_NEEDS_LIVE_PROOF": "live_contract_proof",
            "BLOCKED_RESTRICTED": "restricted_source",
            "NO_SOURCE_FOUND": "source_discovery",
        }
    )

    return {
        "Company_Registry": registry.sort_values(["country", "priority", "company"]),
        "Country_Coverage": country_coverage,
        "Missing_Companies": missing_companies,
        "Employer_Source_Status": registry.sort_values(["status", "priority", "company"]),
        "ATS_Coverage": ats_coverage,
        "Portal_Alert_Coverage": portal_alert_coverage,
        "Recruiter_Source_Status": recruiter_status,
        "PSU_Notices": psu_notices,
        "Source_Discovery": source_discovery,
        "Stale_Sources": stale_sources,
        "Blocked_Sources": blocked_sources,
        "Coverage_Gaps": coverage_gaps,
        "Company_Aliases": alias_frame,
        "Country_Company_Matrix": company_matrix,
    }
