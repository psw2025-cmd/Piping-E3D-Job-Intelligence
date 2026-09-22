"""A location-grounded local view of collected jobs; never infer location from prose."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .normalization import load_profile_taxonomy, normalize_location

TARGET_CITIES = ("Mumbai", "Thane", "Navi Mumbai")
ROLE = re.compile(
    r"\b(piping|pipe layout|plant layout|e3d|pdms|sp3d|smartplant 3d)\b", re.IGNORECASE
)
EXCLUDED_ROLE = re.compile(
    r"\b(electrical|civil|structural|instrumentation|software|sales|recruiter|accountant)\b",
    re.IGNORECASE,
)
CLOSED = re.compile(
    r"position has been closed|job is no longer available|no longer accepting applications|"
    r"vacancy has been filled|applications are closed|vacancy has now expired|"
    r"job has expired|position is no longer available|deadline\s+passed",
    re.IGNORECASE,
)


def parse_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
            try:
                result = datetime.strptime(text, fmt).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
        else:
            return None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def build_shortlist(rows, config_dir: Path, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    taxonomy = load_profile_taxonomy(config_dir)
    selected = {}
    for row in rows:
        title = str(row.get("title") or "")
        if not ROLE.search(title) or EXCLUDED_ROLE.search(title):
            continue
        if CLOSED.search(str(row.get("description") or "")):
            continue
        if str(row.get("application_status") or "").lower() in {
            "closed",
            "expired",
            "withdrawn",
            "rejected",
        }:
            continue
        closing = parse_date(row.get("closing_at"))
        if closing and closing.date() < now.date():
            continue
        # Raw location is authoritative. Do not trust a stale normalized city over it.
        location = str(row.get("location") or row.get("city") or "")
        parts = [location, *re.split(r"\s*(?:/|;|\||\band\b)\s*", location, flags=re.IGNORECASE)]
        cities = sorted(
            {
                city
                for part in parts
                if (city := normalize_location(part, taxonomy)[0]) in TARGET_CITIES
            }
        )
        if not cities:
            continue
        url = str(row.get("apply_url") or row.get("source_url") or "")
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            continue
        published = parse_date(row.get("published_at"))
        publication = "unknown"
        if published:
            publication = (
                "future_date_review"
                if published > now
                else ("last_30_days" if published >= now - timedelta(days=30) else "older")
            )
        item = {
            "company": row.get("company", ""),
            "title": title,
            "location": location,
            "target_cities": cities,
            "published_at": str(row.get("published_at") or ""),
            "publication_status": publication,
            "last_seen_at": str(row.get("last_seen_at") or ""),
            "match_score": int(row.get("match_score") or 0),
            "apply_url": url,
            "source_name": row.get("source_name", ""),
            "availability": "collected_listing_recheck_before_applying",
        }
        identity = str(row.get("canonical_url") or url).split("#")[0].rstrip("/")
        rank = (
            parse_date(item["last_seen_at"]) or datetime.min.replace(tzinfo=UTC),
            item["match_score"],
        )
        if identity not in selected or rank > selected[identity][0]:
            selected[identity] = (rank, item)
    return sorted(
        (item for _, item in selected.values()),
        key=lambda item: (
            item["publication_status"] != "last_30_days",
            -item["match_score"],
            item["company"],
            item["title"],
        ),
    )


def write_shortlist(
    rows, output_dir: Path, config_dir: Path, *, collection_status: str, now: datetime | None = None
) -> str:
    now = now or datetime.now(UTC)
    jobs = build_shortlist(rows, config_dir, now=now)
    payload = {
        "generated_at_utc": now.isoformat(),
        "collection_status": collection_status,
        "target_cities": list(TARGET_CITIES),
        "count": len(jobs),
        "jobs": jobs,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "MUMBAI_THANE_NAVI_MUMBAI.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    def cell(value):
        return (
            str(value if value is not None else "")
            .replace("|", "\\|")
            .replace("\n", " ")
            .replace("\r", " ")
        )

    lines = [
        "## Mumbai, Thane and Navi Mumbai shortlist",
        "",
        f"Generated: {now.isoformat()} · Collection: **{collection_status}** · Matches: **{len(jobs)}**",
        "",
        "Location comes from job-location fields, not company addresses in descriptions.",
        "New Mumbai/New Bombay are treated as Navi Mumbai. Multi-location roles retain the original location.",
        "Dates marked unknown are not claimed as new. Collected listings need an availability check before applying.",
        "Partial/failed collection means incomplete coverage; zero matches does not mean no vacancies.",
        "",
        "| Company | Role | Location | Posted | Date status | Score | Apply |",
        "|---|---|---|---|---|---:|---|",
    ]
    for job in jobs:
        url = job["apply_url"].replace("(", "%28").replace(")", "%29").replace("|", "%7C")
        lines.append(
            "| "
            + " | ".join(
                cell(job[key])
                for key in (
                    "company",
                    "title",
                    "location",
                    "published_at",
                    "publication_status",
                    "match_score",
                )
            )
            + f" | [Apply]({url}) |"
        )
    if not jobs:
        lines.append("| No local matches in this collection | — | — | — | — | — | — |")
    result = "\n".join(lines) + "\n"
    (output_dir / "MUMBAI_THANE_NAVI_MUMBAI.md").write_text(result, encoding="utf-8")
    return result


def main() -> int:
    import argparse

    from .database import fetch_jobs

    parser = argparse.ArgumentParser(description="Build Mumbai, Thane and Navi Mumbai shortlist")
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--collection-status", default="not_revalidated")
    args = parser.parse_args()
    if not Path(args.db).is_file():
        parser.error("database does not exist; collect sources first")
    print(
        write_shortlist(
            fetch_jobs(args.db),
            Path(args.output),
            Path(args.config_dir),
            collection_status=args.collection_status,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
