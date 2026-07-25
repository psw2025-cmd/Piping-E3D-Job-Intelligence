from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .public_contacts import normalize_email

JOB_TOKENS = {
    "application",
    "applications",
    "career",
    "careers",
    "cv",
    "employment",
    "hr",
    "hiring",
    "job",
    "jobs",
    "people",
    "recruit",
    "recruiter",
    "recruiting",
    "recruitment",
    "resume",
    "resumes",
    "staffing",
    "talent",
    "vacancy",
    "vacancies",
}
GENERAL_TOKENS = {
    "admin",
    "business",
    "contact",
    "enquiries",
    "enquiry",
    "general",
    "hello",
    "info",
    "office",
}
EXCLUDED_TOKENS = {
    "abuse",
    "accessibility",
    "billing",
    "compliance",
    "copyright",
    "dmarc",
    "donotreply",
    "dpo",
    "gdpr",
    "investor",
    "legal",
    "media",
    "noreply",
    "postmaster",
    "press",
    "privacy",
    "relations",
    "security",
    "support",
    "webmaster",
}
ARTIFACT_LOCAL_RE = re.compile(r"^u00[0-9a-f]{2}", re.IGNORECASE)
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _tokens(email: str) -> tuple[str, list[str]]:
    local = email.split("@", 1)[0].lower()
    tokens = [token for token in re.split(r"[._+\-]+", local) if token]
    return local, tokens


def quality_mailbox_type(email: str) -> tuple[str, str]:
    local, tokens = _tokens(email)
    token_set = set(tokens)
    if ARTIFACT_LOCAL_RE.match(local):
        return "excluded", "escaped HTML/JavaScript prefix in local part"
    if token_set & EXCLUDED_TOKENS:
        return "excluded", "non-application mailbox token"
    if tokens and tokens[0] in GENERAL_TOKENS:
        return "general_business", ""
    if local in JOB_TOKENS or token_set & JOB_TOKENS:
        return "job_or_recruitment", ""
    if local in GENERAL_TOKENS or token_set & GENERAL_TOKENS:
        return "general_business", ""
    return "excluded", "not a role-based organizational mailbox"


def _status(kind: str, mail_route_status: str) -> tuple[str, int, str]:
    routable = mail_route_status in {"mx", "implicit_mx"}
    if kind == "job_or_recruitment":
        if routable:
            return "verified_official_job_mailbox", 100, ""
        return "manual_review_dns", 60, f"mail route not proven: {mail_route_status}"
    if kind == "general_business":
        if routable:
            return "verified_official_general_mailbox", 70, ""
        return "manual_review_dns", 30, f"mail route not proven: {mail_route_status}"
    return "excluded", 0, "excluded by final quality gate"


def _join_unique(values: pd.Series) -> str:
    unique: list[str] = []
    for value in values.fillna("").astype(str):
        stripped = value.strip()
        if stripped and stripped not in unique:
            unique.append(stripped)
    return " | ".join(unique)


def clean_contacts(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        clean = frame.copy()
        for column in ("organization_aliases", "source_urls", "duplicate_source_count"):
            if column not in clean.columns:
                clean[column] = pd.Series(dtype="string")
        return clean, frame.copy()

    working = frame.copy()
    working["email"] = working["email"].fillna("").astype(str).map(normalize_email)
    decisions = working["email"].map(quality_mailbox_type)
    working["mailbox_type"] = decisions.map(lambda item: item[0])
    working["quality_reason"] = decisions.map(lambda item: item[1])
    excluded = working[
        working["email"].eq("") | working["mailbox_type"].eq("excluded")
    ].copy()
    clean = working[
        working["email"].ne("") & ~working["mailbox_type"].eq("excluded")
    ].copy()

    status_values = clean.apply(
        lambda row: _status(
            str(row.get("mailbox_type", "")),
            str(row.get("mail_route_status", "")),
        ),
        axis=1,
    )
    clean["verification_status"] = status_values.map(lambda item: item[0])
    clean["priority_score"] = status_values.map(lambda item: item[1])
    clean["review_reason"] = status_values.map(lambda item: item[2])

    clean = clean.sort_values(
        ["priority_score", "organization", "email"],
        ascending=[False, True, True],
    )
    grouped_rows: list[dict[str, Any]] = []
    for email, group in clean.groupby("email", sort=True, dropna=False):
        chosen = group.iloc[0].to_dict()
        chosen["email"] = email
        chosen["organization_aliases"] = _join_unique(group["organization"])
        chosen["source_urls"] = _join_unique(group["source_url"])
        chosen["duplicate_source_count"] = len(group)
        grouped_rows.append(chosen)
    clean = pd.DataFrame(grouped_rows)
    if not clean.empty:
        clean = clean.sort_values(
            ["priority_score", "organization", "email"],
            ascending=[False, True, True],
        ).reset_index(drop=True)
    return clean, excluded.reset_index(drop=True)


def _safe_excel_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    inspected = value.lstrip(" \t\r\n")
    return "'" + value if inspected.startswith(FORMULA_PREFIXES) else value


def _safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    safe = frame.copy()
    for column in safe.columns:
        safe[column] = safe[column].map(_safe_excel_value)
    return safe


def finalize_output(output_dir: str | Path) -> Path:
    output = Path(output_dir)
    input_path = output / "All_Official_Contacts.csv"
    if not input_path.exists():
        raise FileNotFoundError(f"missing raw contacts: {input_path}")
    raw = pd.read_csv(input_path).fillna("")
    clean, excluded = clean_contacts(raw)
    failures_path = output / "Failures.csv"
    failures = (
        pd.read_csv(failures_path).fillna("")
        if failures_path.exists()
        else pd.DataFrame(columns=["organization", "url", "stage", "error"])
    )
    previous_summary_path = output / "summary.json"
    previous_summary = (
        json.loads(previous_summary_path.read_text(encoding="utf-8"))
        if previous_summary_path.exists()
        else {}
    )

    verified_job = clean[
        clean["verification_status"].eq("verified_official_job_mailbox")
    ] if not clean.empty else clean.copy()
    verified_general = clean[
        clean["verification_status"].eq("verified_official_general_mailbox")
    ] if not clean.empty else clean.copy()
    manual_review = clean[
        clean["verification_status"].eq("manual_review_dns")
    ] if not clean.empty else clean.copy()
    frames = {
        "All_Official_Contacts": clean,
        "Official_Job_Mailboxes": verified_job,
        "Official_General_Mailboxes": verified_general,
        "Manual_Review_DNS": manual_review,
        "Excluded_Quality": excluded,
        "Failures": failures,
    }
    for name, frame in frames.items():
        frame.to_csv(output / f"{name}.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at_utc": _now(),
        "targets_scanned": int(previous_summary.get("targets_scanned", 0)),
        "raw_contact_rows": len(raw),
        "all_official_contacts": len(clean),
        "official_job_mailboxes": len(verified_job),
        "official_general_mailboxes": len(verified_general),
        "manual_review_dns": len(manual_review),
        "excluded_by_quality_gate": len(excluded),
        "failures": len(failures),
        "unique_emails": clean["email"].nunique() if not clean.empty else 0,
        "organizations_with_contacts": (
            clean["organization"].nunique() if not clean.empty else 0
        ),
    }
    summary_frame = pd.DataFrame(summary.items(), columns=["metric", "value"])
    summary_frame.to_csv(output / "Summary.csv", index=False)
    workbook_path = output / "Global_Official_Hiring_Contacts.xlsx"
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for name, frame in frames.items():
            _safe_frame(frame).to_excel(writer, sheet_name=name[:31], index=False)
        summary_frame.to_excel(writer, sheet_name="Summary", index=False)
    previous_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "SUMMARY.md").write_text(
        "# Global Official Hiring Contacts — Final Quality Gate\n\n"
        + "\n".join(
            f"- **{key.replace('_', ' ').title()}**: {value}"
            for key, value in summary.items()
        )
        + "\n",
        encoding="utf-8",
    )
    archive_path = output / "Global_Official_Hiring_Contacts_Bundle.zip"
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in sorted(output.iterdir()):
            if path != archive_path and path.is_file():
                archive.write(path, arcname=path.name)
    return archive_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply final quality gate to contact output")
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    archive = finalize_output(args.output)
    print(f"PASS: finalized official hiring contact bundle at {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
