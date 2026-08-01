#!/usr/bin/env python3
"""Export Fluor's public Eightfold catalogue and piping/E3D matches to CSV.

Uses only publicly rendered Fluor career pages, honours robots.txt, throttles detail
requests, preserves every catalogue row, and marks extraction uncertainty explicitly.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://careers.fluor.com"
LISTING = f"{BASE}/careers"
UA = "Piping-E3D-Job-Intelligence/0.6 (+public official-source audit)"
KEYWORDS = {
    "piping": r"\bpiping\b|\bpipe\s*(?:layout|design|support|stress|material|route|rack|fitter)\b",
    "e3d": r"\b(?:aveva\s*)?e3d\b",
    "pdms": r"\bpdms\b",
    "sp3d_s3d": r"\b(?:sp3d|s3d|smartplant\s*3d|smart\s*3d)\b",
    "plant_layout": r"\bplant\s*layout\b|\blayout(?:ing)?\b|\bequipment\s*layout\b",
    "navisworks": r"\bnavisworks\b",
    "microstation": r"\bmicrostation\b",
    "autocad": r"\bautocad(?:\s*plant\s*3d)?\b",
    "model_coordination": r"\b3d\s*model(?:ling|ing)?\b|\bmodel\s*coordinat(?:or|ion)\b",
    "site_piping": r"\bsite\s*piping\b|\bconstruction\s*coordinat(?:or|ion)\b",
    "oil_gas_epc": r"\boil\s*(?:&|and)\s*gas\b|\blng\b|\brefiner(?:y|ies)\b|\bpetrochemical\b|\boffshore\b|\bnuclear\b|\bepc(?:m)?\b",
}
FIELDS = [
    "company", "position_id", "ats_job_id", "display_job_id", "title", "posting_name",
    "city_state_country", "all_locations", "country", "department", "business_unit",
    "seniority", "workplace_type", "hot", "posted_utc", "updated_utc", "official_url",
    "detail_http_status", "active_status", "description", "experience", "education",
    "work_authorisation", "urgency_evidence", *[f"kw_{k}" for k in KEYWORDS],
    "matched_keywords", "match_count", "source", "collected_utc", "extraction_notes",
]


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def extract_catalogue(html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Any] = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        text = text.strip()
        if not text or text[0] not in "[{":
            continue
        try:
            candidates.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    positions: dict[str, dict[str, Any]] = {}
    facets: dict[str, Any] = {}
    for root in candidates:
        for node in walk(root):
            if isinstance(node, dict) and isinstance(node.get("positions"), list):
                for item in node["positions"]:
                    if isinstance(item, dict) and item.get("id"):
                        positions[str(item["id"])] = item
                if isinstance(node.get("facets"), dict):
                    facets = node["facets"]
    if not positions:
        # Eightfold sometimes embeds JSON inside a non-JSON assignment. Extract the
        # balanced positions array without depending on private endpoints.
        marker = '"positions":'
        start = html.find(marker)
        if start >= 0:
            arr = html.find("[", start)
            depth = 0
            quoted = escaped = False
            for end in range(arr, len(html)):
                char = html[end]
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char == "[":
                    depth += 1
                elif char == "]":
                    depth -= 1
                    if depth == 0:
                        for item in json.loads(html[arr : end + 1]):
                            if isinstance(item, dict) and item.get("id"):
                                positions[str(item["id"])] = item
                        break
    return list(positions.values()), facets


def epoch(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def find_text(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()[:700]
    return ""


def parse_detail(html: str) -> tuple[str, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    facts = {
        "experience": find_text([r"(?:minimum|at least|requires?).{0,80}?\b\d{1,2}\+?\s+years?.{0,180}", r"\b\d{1,2}\+?\s+years? of.{0,220}"], text),
        "education": find_text([r"(?:bachelor|master|degree|diploma|associate).{0,260}"], text),
        "work_authorisation": find_text([r"(?:authorized|authorised|work authorization|work permit|visa|sponsor|citizenship|clearance).{0,260}"], text),
        "urgency_evidence": find_text([r"\b(?:urgent|immediate(?:ly)?|asap|walk[- ]?in|mobilisation|mobilization)\b.{0,180}"], text),
    }
    return text[:30000], facts


def country_from(location: str) -> str:
    return location.rsplit(",", 1)[-1].strip() if "," in location else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="output/fluor")
    parser.add_argument("--delay", type=float, default=0.45)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-details", type=int, default=2000)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    collected = datetime.now(timezone.utc).isoformat()

    robots = RobotFileParser(urljoin(BASE, "/robots.txt"))
    robots.set_url(urljoin(BASE, "/robots.txt"))
    robots.read()
    if not robots.can_fetch(UA, LISTING):
        raise SystemExit("robots.txt does not permit catalogue retrieval")

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    response = session.get(LISTING, timeout=args.timeout)
    response.raise_for_status()
    catalogue, facets = extract_catalogue(response.text)
    if not catalogue:
        raise SystemExit("No public Eightfold positions found in official Fluor page")

    rows: list[dict[str, Any]] = []
    for index, job in enumerate(catalogue):
        url = job.get("canonicalPositionUrl") or f"{BASE}/careers/job/{job.get('id')}"
        url = urljoin(BASE, str(url))
        detail_status = ""
        description = ""
        facts = {"experience": "", "education": "", "work_authorisation": "", "urgency_evidence": ""}
        notes = ""
        if index < args.max_details and urlparse(url).hostname == "careers.fluor.com" and robots.can_fetch(UA, url):
            try:
                detail = session.get(url, timeout=args.timeout)
                detail_status = str(detail.status_code)
                if detail.status_code == 200:
                    description, facts = parse_detail(detail.text)
                else:
                    notes = f"detail returned HTTP {detail.status_code}"
            except requests.RequestException as exc:
                notes = f"detail request failed: {type(exc).__name__}"
            time.sleep(max(args.delay, 0.0))
        else:
            notes = "detail not fetched because of configured limit/domain/robots policy"

        title = str(job.get("name") or "")
        posting = str(job.get("posting_name") or "")
        locations = job.get("locations") or []
        location = str(job.get("location") or (locations[0] if locations else ""))
        haystack = " ".join([title, posting, description])
        flags = {name: bool(re.search(pattern, haystack, re.I)) for name, pattern in KEYWORDS.items()}
        matched = [name for name, yes in flags.items() if yes]
        status = "confirmed_active" if detail_status == "200" else "potentially_active"
        row = {
            "company": "Fluor", "position_id": job.get("id", ""),
            "ats_job_id": job.get("ats_job_id", ""), "display_job_id": job.get("display_job_id", ""),
            "title": title, "posting_name": posting, "city_state_country": location,
            "all_locations": " | ".join(map(str, locations)), "country": country_from(location),
            "department": " | ".join(map(str, job.get("department") or [])),
            "business_unit": job.get("business_unit", ""), "seniority": job.get("seniority", ""),
            "workplace_type": job.get("work_location_option", ""), "hot": job.get("hot", ""),
            "posted_utc": epoch(job.get("t_create")), "updated_utc": epoch(job.get("t_update")),
            "official_url": url, "detail_http_status": detail_status, "active_status": status,
            "description": description, **facts, **{f"kw_{key}": int(value) for key, value in flags.items()},
            "matched_keywords": " | ".join(matched), "match_count": len(matched),
            "source": LISTING, "collected_utc": collected, "extraction_notes": notes,
        }
        rows.append(row)

    def write_csv(path: Path, data: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    relevant = [row for row in rows if int(row["match_count"]) > 0]
    direct = [row for row in relevant if any(int(row[f"kw_{k}"]) for k in ("piping", "e3d", "pdms", "sp3d_s3d", "plant_layout"))]
    write_csv(out / "Fluor_All_Worldwide_Jobs.csv", rows)
    write_csv(out / "Fluor_Piping_E3D_All_Matches.csv", relevant)
    write_csv(out / "Fluor_Direct_Piping_E3D_Matches.csv", direct)
    summary = {
        "collected_utc": collected, "catalogue_count": len(rows), "keyword_matches": len(relevant),
        "direct_matches": len(direct), "countries": sorted({r["country"] for r in rows if r["country"]}),
        "facets": facets, "all_csv": "Fluor_All_Worldwide_Jobs.csv",
        "filtered_csv": "Fluor_Piping_E3D_All_Matches.csv",
    }
    (out / "Fluor_Worldwide_Summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("catalogue_count", "keyword_matches", "direct_matches")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
