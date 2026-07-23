from __future__ import annotations

import hashlib
import re
from pathlib import Path

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


def registry_frames(
    config_dir: str | Path = "config",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(config_dir)

    def load_rows(filename: str, key: str) -> pd.DataFrame:
        path = root / filename
        if not path.exists():
            return pd.DataFrame()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = loaded.get(key, []) if isinstance(loaded, dict) else []
        return pd.json_normalize(rows) if isinstance(rows, list) else pd.DataFrame()

    return (
        load_rows("employer_registry.yaml", "employers"),
        load_rows("recruiters.yaml", "recruiters"),
    )
