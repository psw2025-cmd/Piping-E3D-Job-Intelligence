from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font

from .database import JOB_COLUMNS, connect, fetch_jobs
from .gmail_alerts import init_gmail_tables
from .worldwide_registry import (
    company_alias_frame,
    company_coverage_frame,
    country_company_matrix,
    coverage_gap_frame,
    gmail_query_groups,
)
from .worldwide_views import deduplicate_worldwide, registry_frames, summary_by

REQUIRED_SHEETS = (
    "New_Today",
    "High_Priority",
    "Worldwide_Dedup",
    "All_Active",
    "All_Source_Rows",
    "Duplicate_Variants",
    "Manual_Review",
    "Applied",
    "Follow_Up",
    "Rejected",
    "Expired",
    "Recruiter_Contacts",
    "Country_Summary",
    "Company_Summary",
    "Employer_Coverage",
    "Recruiter_Coverage",
    "Worldwide_Companies",
    "Country_Company_Matrix",
    "Coverage_Gaps",
    "Company_Aliases",
    "Gmail_Query_Groups",
    "Source_Health",
    "Source_Evidence",
    "Private_Imports",
    "Gmail_Alerts",
    "Gmail_Alert_Jobs",
    "Run_Proof",
    "Daily_Summary",
)
REQUIRED_JOB_COLUMNS = (
    "title",
    "normalized_role",
    "company",
    "location",
    "city",
    "country",
    "apply_url",
    "source_name",
    "source_url",
    "published_at",
    "closing_at",
    "experience_text",
    "software_text",
    "sector",
    "employment_type",
    "match_score",
    "match_reasons",
    "gaps",
    "recruiter_email",
    "contact_source_url",
    "contact_confidence",
    "duplicate_status",
    "application_status",
)
REQUIRED_DEDUP_COLUMNS = (
    "duplicate_group",
    "source_count",
    "duplicate_sources",
    "all_apply_urls",
)
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _empty_jobs_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=JOB_COLUMNS)


def _safe_excel_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    inspected = value.lstrip(" \t\r\n")
    return "'" + value if inspected.startswith(_FORMULA_PREFIXES) else value


def _safe_excel_frame(frame: pd.DataFrame) -> pd.DataFrame:
    safe = frame.copy()
    for column in safe.columns:
        safe[column] = safe[column].map(_safe_excel_value)
    return safe


def _format_workbook(path: Path) -> None:
    workbook = load_workbook(path)
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column_cells in sheet.columns:
            values = [str(cell.value or "") for cell in list(column_cells)[:200]]
            maximum = max((len(value) for value in values), default=0)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(
                max(maximum + 2, 10),
                55,
            )
    workbook.save(path)


def _daily_summary(
    *,
    jobs: pd.DataFrame,
    active: pd.DataFrame,
    duplicate_variants: pd.DataFrame,
    new_today: pd.DataFrame,
    high_priority: pd.DataFrame,
    manual_review: pd.DataFrame,
    applied: pd.DataFrame,
    follow_up: pd.DataFrame,
    rejected: pd.DataFrame,
    expired: pd.DataFrame,
    contacts: pd.DataFrame,
    source_health: pd.DataFrame,
    gmail_alerts: pd.DataFrame,
    worldwide_companies: pd.DataFrame,
    coverage_gaps: pd.DataFrame,
) -> pd.DataFrame:
    source_status = source_health.get("status", pd.Series(dtype="string"))
    gmail_status = gmail_alerts.get("status", pd.Series(dtype="string"))
    countries = active.get("country", pd.Series(dtype="string"))
    companies = active.get("company", pd.Series(dtype="string"))
    source_passes = source_status.isin(["pass", "pass_with_warnings"])
    gmail_complete = gmail_status.str.startswith("complete", na=False)
    active_company_coverage = worldwide_companies.get(
        "coverage_active", pd.Series(dtype="bool")
    )
    metrics = (
        ("generated_at", datetime.now(UTC).replace(microsecond=0).isoformat()),
        ("raw_source_rows", len(jobs)),
        ("worldwide_deduplicated_jobs", len(active)),
        ("duplicate_variant_rows", len(duplicate_variants)),
        ("new_today", len(new_today)),
        ("high_priority", len(high_priority)),
        ("countries", int(countries.replace("", pd.NA).nunique())),
        ("companies", int(companies.replace("", pd.NA).nunique())),
        ("manual_review", len(manual_review)),
        ("applied", len(applied)),
        ("follow_up", len(follow_up)),
        ("rejected", len(rejected)),
        ("expired", len(expired)),
        ("recruiter_contacts", len(contacts)),
        ("sources_total", len(source_health)),
        ("sources_passing", int(source_passes.sum())),
        ("sources_failing", int(source_status.eq("fail").sum())),
        ("gmail_messages", len(gmail_alerts)),
        ("gmail_complete", int(gmail_complete.sum())),
        ("gmail_failed", int(gmail_status.eq("failed").sum())),
        ("target_companies", len(worldwide_companies)),
        ("active_company_coverage", int(active_company_coverage.sum())),
        ("company_coverage_gaps", len(coverage_gaps)),
    )
    return pd.DataFrame(metrics, columns=("metric", "value"))


def export_excel(db_path: str | Path, output_path: str | Path) -> Path:
    init_gmail_tables(db_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    jobs = pd.DataFrame(fetch_jobs(db_path))
    if jobs.empty:
        jobs = _empty_jobs_frame()

    with connect(db_path) as connection:
        source_health = pd.read_sql_query(
            "SELECT * FROM source_health ORDER BY last_attempt_at DESC",
            connection,
        )
        source_evidence = pd.read_sql_query(
            "SELECT * FROM source_evidence ORDER BY fetched_at DESC",
            connection,
        )
        private_imports = pd.read_sql_query(
            "SELECT * FROM private_imports ORDER BY imported_at DESC",
            connection,
        )
        gmail_alerts = pd.read_sql_query(
            "SELECT * FROM gmail_alert_messages ORDER BY imported_at DESC",
            connection,
        )
        gmail_alert_jobs = pd.read_sql_query(
            "SELECT * FROM gmail_alert_jobs ORDER BY message_id, candidate_index",
            connection,
        )
        run_proof = pd.read_sql_query(
            "SELECT * FROM runs ORDER BY started_at DESC",
            connection,
        )

    statuses = jobs.get("application_status", pd.Series(dtype="string"))
    active_source_rows = jobs[~statuses.isin(["expired", "rejected"])]
    active, duplicate_variants = deduplicate_worldwide(active_source_rows)
    employer_coverage, recruiter_coverage = registry_frames()
    worldwide_companies = company_coverage_frame()
    country_company_coverage = country_company_matrix()
    coverage_gaps = coverage_gap_frame()
    company_aliases = company_alias_frame()
    generated_gmail_queries = gmail_query_groups()

    review_job_keys = set(
        private_imports.loc[
            private_imports.get("review_required", pd.Series(dtype="int64")).eq(1),
            "job_key",
        ].astype(str)
    )
    today = datetime.now(UTC).date().isoformat()
    found_dates = active.get("found_at", pd.Series(dtype="string")).astype(str)
    new_today = active[found_dates.str.startswith(today, na=False)]
    priorities = active.get("priority", pd.Series(dtype="string"))
    high_priority = active[priorities.isin(["critical", "high"])]

    confidence = jobs.get("contact_confidence", pd.Series(dtype="string"))
    job_keys = jobs.get("job_key", pd.Series(dtype="string")).astype(str)
    uncertain_contacts = confidence.isin(
        ["PUBLIC_UNVERIFIED", "PATTERN_SUGGESTION", "ALERT_SUPPLIED"]
    )
    manual_review = jobs[
        uncertain_contacts
        | statuses.eq("review_required")
        | job_keys.isin(review_job_keys)
    ]
    applied = jobs[statuses.eq("applied")]
    follow_up = jobs[statuses.eq("follow_up")]
    rejected = jobs[statuses.eq("rejected")]
    expired = jobs[statuses.eq("expired")]
    emails = jobs.get("recruiter_email", pd.Series(dtype="string"))
    contacts = jobs[emails.fillna("").astype(str).str.len() > 0]
    country_summary = summary_by(active, "country")
    company_summary = summary_by(active, "company")
    daily_summary = _daily_summary(
        jobs=jobs,
        active=active,
        duplicate_variants=duplicate_variants,
        new_today=new_today,
        high_priority=high_priority,
        manual_review=manual_review,
        applied=applied,
        follow_up=follow_up,
        rejected=rejected,
        expired=expired,
        contacts=contacts,
        source_health=source_health,
        gmail_alerts=gmail_alerts,
        worldwide_companies=worldwide_companies,
        coverage_gaps=coverage_gaps,
    )

    sheets = {
        "New_Today": new_today,
        "High_Priority": high_priority,
        "Worldwide_Dedup": active,
        "All_Active": active,
        "All_Source_Rows": active_source_rows,
        "Duplicate_Variants": duplicate_variants,
        "Manual_Review": manual_review,
        "Applied": applied,
        "Follow_Up": follow_up,
        "Rejected": rejected,
        "Expired": expired,
        "Recruiter_Contacts": contacts,
        "Country_Summary": country_summary,
        "Company_Summary": company_summary,
        "Employer_Coverage": employer_coverage,
        "Recruiter_Coverage": recruiter_coverage,
        "Worldwide_Companies": worldwide_companies,
        "Country_Company_Matrix": country_company_coverage,
        "Coverage_Gaps": coverage_gaps,
        "Company_Aliases": company_aliases,
        "Gmail_Query_Groups": generated_gmail_queries,
        "Source_Health": source_health,
        "Source_Evidence": source_evidence,
        "Private_Imports": private_imports,
        "Gmail_Alerts": gmail_alerts,
        "Gmail_Alert_Jobs": gmail_alert_jobs,
        "Run_Proof": run_proof,
        "Daily_Summary": daily_summary,
    }
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            _safe_excel_frame(frame).to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )
    _format_workbook(output)
    return output


def verify_excel(path: str | Path) -> list[str]:
    workbook_path = Path(path)
    errors: list[str] = []
    if not workbook_path.exists():
        return [f"Excel output does not exist: {workbook_path}"]
    if workbook_path.stat().st_size == 0:
        return [f"Excel output is empty: {workbook_path}"]

    workbook = load_workbook(workbook_path, read_only=True)
    missing = [sheet for sheet in REQUIRED_SHEETS if sheet not in workbook.sheetnames]
    if missing:
        errors.append(f"Missing sheets: {', '.join(missing)}")
    if "All_Active" in workbook.sheetnames:
        headers = {
            str(cell.value or "").strip()
            for cell in next(workbook["All_Active"].iter_rows(min_row=1, max_row=1))
        }
        missing_columns = [
            column for column in REQUIRED_JOB_COLUMNS if column not in headers
        ]
        if missing_columns:
            errors.append(f"Missing job columns: {', '.join(missing_columns)}")
        missing_dedup = [
            column for column in REQUIRED_DEDUP_COLUMNS if column not in headers
        ]
        if missing_dedup:
            errors.append(f"Missing dedup columns: {', '.join(missing_dedup)}")
    return errors
