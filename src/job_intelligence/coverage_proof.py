from __future__ import annotations

from typing import Any

import pandas as pd

from .coverage_registry import COVERED_STATUSES

_ALTERNATIVE_ACTIVE = COVERED_STATUSES - {"ACTIVE_DIRECT"}


def _as_number(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(
        frame.get(column, pd.Series(index=frame.index, dtype="float64")),
        errors="coerce",
    ).fillna(0)


def _country_coverage(registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for country, frame in registry.groupby("country", dropna=False):
        total = len(frame)
        proven = int(frame["coverage_proven"].sum())
        rows.append(
            {
                "country": country,
                "total_target_companies": total,
                "configured_coverage_paths": int(frame["coverage_ready"].sum()),
                "proven_operational_coverage": proven,
                "active_direct_sources": int(
                    (
                        frame["status"].eq("ACTIVE_DIRECT")
                        & frame["coverage_proven"]
                    ).sum()
                ),
                "active_gmail_sources": int(
                    (
                        frame["status"].eq("ACTIVE_GMAIL_ALERT")
                        & frame["coverage_proven"]
                    ).sum()
                ),
                "public_notice_sources": int(
                    (
                        frame["status"].eq("ACTIVE_PUBLIC_NOTICE")
                        & frame["coverage_proven"]
                    ).sum()
                ),
                "manual_import_sources": int(
                    (
                        frame["status"].eq("ACTIVE_MANUAL_IMPORT")
                        & frame["coverage_proven"]
                    ).sum()
                ),
                "staged_sources": int(
                    frame["status"].eq("STAGED_NEEDS_LIVE_PROOF").sum()
                ),
                "blocked_sources": int(
                    frame["status"].eq("BLOCKED_RESTRICTED").sum()
                ),
                "no_source_found": int(
                    frame["status"].eq("NO_SOURCE_FOUND").sum()
                ),
                "unproven_configured_paths": int(
                    (frame["coverage_ready"] & ~frame["coverage_proven"]).sum()
                ),
                "jobs_found_today": int(frame["jobs_found_today"].sum()),
                "jobs_found_30d": int(frame["jobs_found_30d"].sum()),
                "last_successful_scan": frame["last_success_at"].max(),
                "coverage_percentage": round(proven * 100 / total, 1) if total else 0,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["coverage_percentage", "total_target_companies", "country"],
        ascending=[True, False, True],
    )


def apply_coverage_proof(
    frames: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Separate configured coverage paths from evidence-backed operational coverage."""
    registry = frames["Company_Registry"].copy()
    status = registry["status"].fillna("").astype(str)
    passing_sources = _as_number(registry, "passing_source_count")
    recent_jobs = _as_number(registry, "jobs_found_30d")

    registry["coverage_ready"] = status.isin(COVERED_STATUSES)
    registry["coverage_proven"] = (
        status.eq("ACTIVE_DIRECT") & passing_sources.gt(0)
    ) | (status.isin(_ALTERNATIVE_ACTIVE) & recent_jobs.gt(0))
    registry["coverage_active"] = registry["coverage_proven"]
    registry["proof_state"] = "not_configured"
    registry.loc[registry["coverage_ready"], "proof_state"] = "configured_unproven"
    registry.loc[registry["coverage_proven"], "proof_state"] = "proven_operational"

    not_proven = registry[~registry["coverage_proven"]].copy()
    missing_columns = [
        "company_id",
        "company",
        "country",
        "priority",
        "status",
        "proof_state",
        "official_careers_url",
        "ats_family",
        "recommended_next_action",
    ]
    missing = not_proven[missing_columns].sort_values(
        ["priority", "country", "company"]
    )
    gaps = missing.copy()
    gaps["gap_type"] = gaps.apply(
        lambda row: (
            "configured_but_unproven"
            if row["proof_state"] == "configured_unproven"
            else {
                "STAGED_NEEDS_LIVE_PROOF": "live_contract_proof",
                "BLOCKED_RESTRICTED": "restricted_source",
                "NO_SOURCE_FOUND": "source_discovery",
            }.get(row["status"], "coverage_missing")
        ),
        axis=1,
    )

    updated = dict(frames)
    updated["Company_Registry"] = registry.sort_values(
        ["country", "priority", "company"]
    )
    updated["Employer_Source_Status"] = registry.sort_values(
        ["proof_state", "status", "priority", "company"]
    )
    updated["Country_Coverage"] = _country_coverage(registry)
    updated["Missing_Companies"] = missing
    updated["Coverage_Gaps"] = gaps
    return updated
