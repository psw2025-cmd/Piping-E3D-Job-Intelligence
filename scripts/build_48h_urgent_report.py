from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PIPING_TERMS = (
    "piping", "pipe layout", "plant layout", "e3d", "aveva e3d", "pdms",
    "sp3d", "smartplant 3d", "smart 3d", "piping designer",
    "piping engineer", "piping checker", "piping lead", "pipe support",
    "piping stress", "3d model coordinator",
)

URGENT_TERMS = (
    "urgent", "urgently", "immediate", "immediately", "asap",
    "join immediately", "immediate joiner", "immediate joining",
    "short notice", "mobilization", "mobilisation", "walk-in", "walk in",
    "hiring now", "priority hiring", "hot job", "start immediately",
    "available immediately",
)

SENIOR_TERMS = (
    "lead", "senior", "sr.", "sr ", "principal", "manager", "head",
    "area lead", "discipline lead", "checker", "coordinator",
)


def parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    candidates = [normalized]
    if len(normalized) == 10:
        candidates.append(normalized + "T00:00:00+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    return None


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def markdown(value: Any) -> str:
    return clean(value).replace("|", "\\|")


def contains_any(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.casefold()
    return [term for term in terms if term.casefold() in lowered]


def load_rows(db_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        required = {
            "job_key", "title", "company", "location", "city", "country",
            "description", "apply_url", "source_url", "source_name",
            "published_at", "found_at", "last_seen_at", "experience_text",
            "skills_text", "software_text", "sector", "recruiter_name",
            "recruiter_email", "contact_confidence", "match_score",
            "match_reasons", "gaps", "priority", "application_status",
            "normalized_role", "canonical_url",
        }
        missing = sorted(required - columns)
        if missing:
            raise RuntimeError(f"jobs table missing columns: {', '.join(missing)}")
        query = """
            SELECT job_key, title, normalized_role, company, location, city, country,
                   description, apply_url, source_url, source_name, published_at,
                   found_at, last_seen_at, experience_text, skills_text, software_text,
                   sector, recruiter_name, recruiter_email, contact_confidence,
                   match_score, match_reasons, gaps, priority, application_status,
                   canonical_url
            FROM jobs
            ORDER BY match_score DESC, published_at DESC, company, title
        """
        return [dict(row) for row in connection.execute(query)]
    finally:
        connection.close()


def classify(
    row: dict[str, Any],
    *,
    cutoff_utc: datetime,
    now_utc: datetime,
) -> dict[str, Any] | None:
    combined = " ".join(
        clean(row.get(name))
        for name in (
            "title", "normalized_role", "description", "experience_text",
            "skills_text", "software_text", "sector",
        )
    )
    piping_hits = contains_any(combined, PIPING_TERMS)
    if not piping_hits:
        return None

    urgent_hits = contains_any(combined, URGENT_TERMS)
    senior_hits = contains_any(combined, SENIOR_TERMS)
    published = parse_datetime(clean(row.get("published_at")))
    found = parse_datetime(clean(row.get("found_at")))
    strict_recent = bool(published and cutoff_utc <= published <= now_utc + timedelta(hours=6))
    date_status = "confirmed_48h" if strict_recent else ("date_unknown" if not published else "older")
    urgency = "urgent" if urgent_hits else "normal"

    url = clean(row.get("apply_url")) or clean(row.get("source_url"))
    identity = clean(row.get("canonical_url")) or url or clean(row.get("job_key"))

    return {
        **row,
        "identity": identity,
        "url": url,
        "published_iso": published.isoformat() if published else "",
        "found_iso": found.isoformat() if found else "",
        "date_status": date_status,
        "urgency": urgency,
        "urgent_hits": sorted(set(urgent_hits)),
        "piping_hits": sorted(set(piping_hits)),
        "senior_fit": bool(senior_hits) or int(row.get("match_score") or 0) >= 70,
        "senior_hits": sorted(set(senior_hits)),
    }


def deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["identity"]
        current = best.get(key)
        row_rank = (
            row["date_status"] == "confirmed_48h",
            row["urgency"] == "urgent",
            int(row.get("match_score") or 0),
            bool(row.get("published_iso")),
        )
        current_rank = (
            current["date_status"] == "confirmed_48h",
            current["urgency"] == "urgent",
            int(current.get("match_score") or 0),
            bool(current.get("published_iso")),
        ) if current else None
        if current is None or row_rank > current_rank:
            best[key] = row
    return list(best.values())


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            row["urgency"] != "urgent",
            row["date_status"] != "confirmed_48h",
            -int(row.get("match_score") or 0),
            row.get("published_iso") or "",
            clean(row.get("company")),
            clean(row.get("title")),
        ),
    )


def table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Urgency | Company | Role | Location | Country | Posted | Score | Apply | Source |",
        "|---|---|---|---|---|---|---:|---|---|",
    ]
    if not rows:
        lines.append("| — | No verified matches | — | — | — | — | 0 | — | — |")
        return lines
    for row in rows:
        url = row["url"]
        apply = f"[Open]({url})" if url else "—"
        posted = row["published_iso"][:10] if row["published_iso"] else "Unknown"
        lines.append(
            f"| **{row['urgency'].upper()}** | {markdown(row.get('company'))} | "
            f"{markdown(row.get('title'))} | {markdown(row.get('location'))} | "
            f"{markdown(row.get('country'))} | {posted} | "
            f"{int(row.get('match_score') or 0)} | {apply} | "
            f"{markdown(row.get('source_name'))} |"
        )
    return lines


def write_report(
    rows: list[dict[str, Any]],
    output_md: Path,
    output_json: Path,
    *,
    now_utc: datetime,
    hours: int,
    timezone_name: str,
) -> None:
    tz = ZoneInfo(timezone_name)
    cutoff_utc = now_utc - timedelta(hours=hours)
    classified = [
        item for row in rows
        if (item := classify(row, cutoff_utc=cutoff_utc, now_utc=now_utc)) is not None
    ]
    classified = sort_rows(deduplicate(classified))
    confirmed = [row for row in classified if row["date_status"] == "confirmed_48h"]
    urgent_confirmed = [row for row in confirmed if row["urgency"] == "urgent"]
    normal_confirmed = [row for row in confirmed if row["urgency"] == "normal"]
    urgent_unknown = [
        row for row in classified
        if row["urgency"] == "urgent" and row["date_status"] == "date_unknown"
    ]
    active_unknown = [
        row for row in classified
        if row["urgency"] == "normal" and row["date_status"] == "date_unknown"
    ]

    countries = sorted({clean(row.get("country")) for row in classified if clean(row.get("country"))})
    locations = sorted({clean(row.get("location")) for row in classified if clean(row.get("location"))})

    generated_local = now_utc.astimezone(tz)
    cutoff_local = cutoff_utc.astimezone(tz)
    lines = [
        "# Latest 48-Hour Global Piping Opportunity Scan",
        "",
        f"Generated: `{generated_local.isoformat()}`",
        f"Strict publication window: `{cutoff_local.isoformat()}` to `{generated_local.isoformat()}`",
        "",
        "## Evidence rules",
        "",
        "- **Confirmed 48h** requires a parseable official/source-supplied `published_at` inside the window.",
        "- **Urgent** requires explicit wording such as urgent, immediate, ASAP, walk-in or mobilisation.",
        "- Roles with no reliable publication date are shown separately and are **not claimed as today/yesterday**.",
        "- Coverage is limited to enabled, permitted sources; this is not a claim of every vacancy on Earth.",
        "",
        "## Metrics",
        "",
        f"- Relevant active piping records inspected: `{len(classified)}`",
        f"- Confirmed within {hours} hours: `{len(confirmed)}`",
        f"- Confirmed urgent within {hours} hours: `{len(urgent_confirmed)}`",
        f"- Urgent but publication date unknown: `{len(urgent_unknown)}`",
        f"- Countries represented: `{len(countries)}`",
        f"- Distinct locations represented: `{len(locations)}`",
        "",
        "## Confirmed urgent — published in the last 48 hours",
        "",
        *table(urgent_confirmed),
        "",
        "## Confirmed normal — published in the last 48 hours",
        "",
        *table(normal_confirmed),
        "",
        "## Urgent active roles — publication date not proven",
        "",
        *table(urgent_unknown),
        "",
        "## Other active roles — publication date not proven",
        "",
        *table(active_unknown[:100]),
        "",
        "## Coverage observed in this run",
        "",
        f"- Countries: {', '.join(countries) if countries else 'None reported'}",
        f"- Locations: {', '.join(locations[:100]) if locations else 'None reported'}",
        "",
    ]
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "generated_at_utc": now_utc.isoformat(),
        "timezone": timezone_name,
        "window_hours": hours,
        "cutoff_utc": cutoff_utc.isoformat(),
        "metrics": {
            "relevant_active_records": len(classified),
            "confirmed_recent": len(confirmed),
            "confirmed_urgent": len(urgent_confirmed),
            "urgent_date_unknown": len(urgent_unknown),
            "countries": len(countries),
            "locations": len(locations),
        },
        "countries": countries,
        "locations": locations,
        "confirmed_urgent": urgent_confirmed,
        "confirmed_normal": normal_confirmed,
        "urgent_date_unknown": urgent_unknown,
        "active_date_unknown": active_unknown,
    }
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a strict 48-hour global piping vacancy report.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--now-utc", default="")
    args = parser.parse_args()
    if args.hours < 1 or args.hours > 168:
        raise SystemExit("--hours must be between 1 and 168")
    now_utc = parse_datetime(args.now_utc) if args.now_utc else datetime.now(UTC)
    if now_utc is None:
        raise SystemExit("invalid --now-utc")
    rows = load_rows(Path(args.db))
    write_report(
        rows,
        Path(args.output_md),
        Path(args.output_json),
        now_utc=now_utc,
        hours=args.hours,
        timezone_name=args.timezone,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
