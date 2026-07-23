from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _load_overrides(config_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(config_dir) / "worldwide_companies.d"
    if not root.exists():
        return []
    overrides: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"worldwide override root must be a mapping: {path}")
        raw_overrides = loaded.get("overrides", [])
        if not isinstance(raw_overrides, list):
            raise ValueError(f"worldwide overrides must be a list: {path}")
        for raw in raw_overrides:
            if not isinstance(raw, dict):
                raise ValueError(f"worldwide override rows must be mappings: {path}")
            company_id = str(raw.get("company_id", "")).strip()
            if not company_id:
                raise ValueError(f"worldwide override requires company_id: {path}")
            if company_id in seen:
                raise ValueError(f"duplicate worldwide override: {company_id}")
            seen.add(company_id)
            overrides.append(dict(raw))
    return overrides


def _source_health_values(
    source_health: pd.DataFrame,
    source_ids: list[str],
) -> tuple[int, str, str]:
    if not source_ids or source_health.empty or "source_id" not in source_health.columns:
        return 0, "", ""
    matching = source_health[source_health["source_id"].isin(source_ids)]
    if matching.empty:
        return 0, "", ""
    statuses = matching.get("status", pd.Series(dtype="string"))
    passing = int(statuses.isin(["pass", "pass_with_warnings"]).sum())
    successes = matching.get("last_success_at", pd.Series(dtype="string")).fillna("")
    attempts = matching.get("last_attempt_at", pd.Series(dtype="string")).fillna("")
    return passing, successes.max(), attempts.max()


def _serialize(value: Any) -> Any:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return value


def _recompute_auxiliary_frames(
    frames: dict[str, pd.DataFrame],
    registry: pd.DataFrame,
) -> None:
    frames["ATS_Coverage"] = (
        registry.groupby("ats_family", dropna=False)
        .agg(
            target_companies=("company_id", "count"),
            active_direct=(
                "status",
                lambda values: int((values == "ACTIVE_DIRECT").sum()),
            ),
            active_alternative=(
                "status",
                lambda values: int(
                    values.isin(
                        [
                            "ACTIVE_GMAIL_ALERT",
                            "ACTIVE_PUBLIC_NOTICE",
                            "ACTIVE_MANUAL_IMPORT",
                        ]
                    ).sum()
                ),
            ),
            staged=(
                "status",
                lambda values: int((values == "STAGED_NEEDS_LIVE_PROOF").sum()),
            ),
            blocked=(
                "status",
                lambda values: int(
                    values.isin(["BLOCKED_RESTRICTED", "NO_SOURCE_FOUND"]).sum()
                ),
            ),
        )
        .reset_index()
        .sort_values(["active_direct", "target_companies"], ascending=[False, False])
    )
    frames["PSU_Notices"] = registry[
        registry["ats_family"].fillna("").str.contains("notice", case=False)
    ].copy()
    frames["Source_Discovery"] = registry[
        registry["status"].isin(["STAGED_NEEDS_LIVE_PROOF", "NO_SOURCE_FOUND"])
    ].copy()
    frames["Blocked_Sources"] = registry[
        registry["status"].eq("BLOCKED_RESTRICTED")
    ].copy()
    stale_cutoff = datetime.now(UTC) - timedelta(days=7)
    success_dates = pd.to_datetime(registry["last_success_at"], errors="coerce", utc=True)
    frames["Stale_Sources"] = registry[
        registry["status"].eq("ACTIVE_DIRECT")
        & (success_dates.isna() | (success_dates < stale_cutoff))
    ].copy()
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
    frames["Country_Company_Matrix"] = registry[matrix_columns].sort_values(
        ["country", "priority", "company"]
    )


def apply_worldwide_company_overrides(
    frames: dict[str, pd.DataFrame],
    source_health: pd.DataFrame,
    *,
    config_dir: str | Path = "config",
) -> dict[str, pd.DataFrame]:
    overrides = _load_overrides(config_dir)
    if not overrides:
        return frames
    updated = dict(frames)
    registry = updated["Company_Registry"].copy()
    if "company_id" not in registry.columns:
        raise ValueError("Company_Registry has no company_id column")
    known = set(registry["company_id"].astype(str))

    for override in overrides:
        company_id = str(override["company_id"])
        if company_id not in known:
            raise ValueError(f"worldwide override references unknown company_id: {company_id}")
        mask = registry["company_id"].astype(str).eq(company_id)
        for key, value in override.items():
            if key == "company_id":
                continue
            registry.loc[mask, key] = _serialize(value)
        source_ids = override.get("source_ids", [])
        if not isinstance(source_ids, list):
            raise ValueError(f"override source_ids must be a list: {company_id}")
        passing, last_success, last_attempt = _source_health_values(
            source_health,
            [str(value) for value in source_ids],
        )
        registry.loc[mask, "passing_source_count"] = passing
        if last_success:
            registry.loc[mask, "last_success_at"] = last_success
        if last_attempt:
            registry.loc[mask, "last_attempt_at"] = last_attempt

    updated["Company_Registry"] = registry
    _recompute_auxiliary_frames(updated, registry)
    return updated
