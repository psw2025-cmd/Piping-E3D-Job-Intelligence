from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(value: object) -> str:
    return " ".join(_NON_ALNUM.sub(" ", str(value or "").lower()).split())


def duplicate_group(row: pd.Series) -> str:
    role = _normalize(row.get("normalized_role") or row.get("title"))
    company = _normalize(row.get("company"))
    location = _normalize(
        row.get("city") or row.get("location") or row.get("country")
    )
    published = str(row.get("published_at") or "")[:10]
    if not published:
        published = _normalize(row.get("description"))[:120]
    return hashlib.sha256(
        "|".join((role, company, location, published)).encode("utf-8")
    ).hexdigest()[:20]


def deduplicate_worldwide(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched = frame.copy()
    if enriched.empty:
        enriched["duplicate_group"] = pd.Series(dtype="string")
        enriched["source_count"] = pd.Series(dtype="int64")
        enriched["duplicate_sources"] = pd.Series(dtype="string")
        enriched["all_apply_urls"] = pd.Series(dtype="string")
        return enriched, enriched.copy()

    enriched["duplicate_group"] = enriched.apply(duplicate_group, axis=1)
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
        ranked.get("match_score", 0), errors="coerce"
    ).fillna(0)
    ranked["_published"] = ranked.get("published_at", "").fillna("").astype(str)
    ranked = ranked.sort_values(
        ["duplicate_group", "_score", "_published", "last_seen_at"],
        ascending=[True, False, False, False],
    )
    dedup = ranked.drop_duplicates("duplicate_group", keep="first").drop(
        columns=["_score", "_published"]
    )
    dedup = dedup.join(counts, on="duplicate_group")
    dedup = dedup.join(source_names, on="duplicate_group")
    dedup = dedup.join(source_urls, on="duplicate_group")
    dedup["duplicate_status"] = dedup["source_count"].map(
        lambda count: "cross_source_duplicate" if count > 1 else "unique"
    )
    dedup = dedup.sort_values(
        ["match_score", "published_at", "company", "title"],
        ascending=[False, False, True, True],
    )

    duplicate_ids = set(counts[counts > 1].index)
    variants = enriched[enriched["duplicate_group"].isin(duplicate_ids)].copy()
    variants = variants.join(counts, on="duplicate_group")
    variants = variants.sort_values(
        ["duplicate_group", "source_name", "company", "title"]
    )
    return dedup, variants


def summary_by(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return pd.DataFrame(
            columns=[column, "jobs", "critical_high", "newest_posting"]
        )
    values = frame.copy()
    values[column] = values[column].fillna("").astype(str).replace("", "Unspecified")
    grouped = values.groupby(column, dropna=False)
    summary = grouped.size().rename("jobs").to_frame()
    summary["critical_high"] = grouped["priority"].apply(
        lambda priorities: int(priorities.isin(["critical", "high"]).sum())
    )
    summary["newest_posting"] = grouped["published_at"].max()
    return summary.reset_index().sort_values(
        ["critical_high", "jobs", column], ascending=[False, False, True]
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _rows_frame(root: Path, filename: str, key: str) -> pd.DataFrame:
    rows = _read_yaml(root / filename).get(key, [])
    return pd.json_normalize(rows) if isinstance(rows, list) else pd.DataFrame()


def registry_frames(
    config_dir: str | Path = "config",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    root = Path(config_dir)
    return (
        _rows_frame(root, "employer_registry.yaml", "employers"),
        _rows_frame(root, "recruiters.yaml", "recruiters"),
        _rows_frame(root, "portal_registry.yaml", "portals"),
    )


def taxonomy_frames(
    config_dir: str | Path = "config",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(config_dir)
    roles = _read_yaml(root / "roles.yaml")
    locations = _read_yaml(root / "locations.yaml")
    expansion = _read_yaml(root / "coverage_expansion.yaml")

    role_rows: list[dict[str, str]] = []
    for source, mapping in (
        ("base", roles.get("role_families", {})),
        ("expansion", expansion.get("role_families", {})),
    ):
        if not isinstance(mapping, dict):
            continue
        for role, aliases in mapping.items():
            role_rows.append(
                {
                    "source": source,
                    "canonical_role": str(role),
                    "aliases": "; ".join(str(alias) for alias in aliases or []),
                }
            )

    location_rows: list[dict[str, str]] = []
    for source, data in (("base", locations), ("expansion", expansion)):
        groups = data.get("locations", {})
        aliases = data.get("location_aliases", {})
        if isinstance(groups, dict):
            for group, values in groups.items():
                for value in values or []:
                    location_rows.append(
                        {
                            "source": source,
                            "group": str(group),
                            "location": str(value),
                            "country": "",
                            "aliases": "",
                        }
                    )
        if isinstance(aliases, dict):
            for city, details in aliases.items():
                if not isinstance(details, dict):
                    continue
                location_rows.append(
                    {
                        "source": source,
                        "group": "alias",
                        "location": str(city),
                        "country": str(details.get("country", "")),
                        "aliases": "; ".join(
                            str(alias) for alias in details.get("aliases", []) or []
                        ),
                    }
                )
    return pd.DataFrame(role_rows), pd.DataFrame(location_rows)


def coverage_gaps(
    employer_coverage: pd.DataFrame,
    source_health: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not employer_coverage.empty:
        for record in employer_coverage.to_dict("records"):
            status = str(record.get("status", ""))
            if status == "active_supported":
                continue
            rows.append(
                {
                    "category": "employer",
                    "name": record.get("company", ""),
                    "status": status,
                    "priority": record.get("priority", ""),
                    "detail": record.get("notes", "") or "No active verified source",
                }
            )
    if not source_health.empty:
        for record in source_health.to_dict("records"):
            status = str(record.get("status", ""))
            records = int(record.get("records_found", 0) or 0)
            if status == "pass" and records > 0:
                continue
            rows.append(
                {
                    "category": "source",
                    "name": record.get("source_name", record.get("source_id", "")),
                    "status": status or "unknown",
                    "priority": "",
                    "detail": record.get("error_message", "")
                    or f"records_found={records}",
                }
            )
    return pd.DataFrame(
        rows, columns=["category", "name", "status", "priority", "detail"]
    )
