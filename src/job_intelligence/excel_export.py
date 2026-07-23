from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font

from .database import JOB_COLUMNS, connect, fetch_jobs
from .private_import import init_private_import_tables
from .worldwide_enrichment import (
    daily_summary_frame,
    deduplicate_worldwide,
    enrich_jobs_frame,
    registry_frames,
)

REQUIRED_SHEETS = (
    "Daily_Summary",
    "New_Today",
    "High_Priority",
    "Worldwide_Dedup",
    "All_Active",
    "All_Source_Rows",
    "Duplicate_Variants",
    "Manual_Review",
    "Applied",
    "Follow_Up",
    "Expired",
    "Recruiter_Contacts",
    "Country_Summary",
    "Company_Summary",
    "Employer_Coverage",
    "Recruiter_Coverage",
    "Source_Health",
    "Source_Evidence",
    "Private_Imports",
    "Run_Proof",
)
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _empty_jobs_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=JOB_COLUMNS)


def _safe_excel_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    inspected = value.lstrip(" \t\r\n")
    if inspected.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


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
            width = min(max(maximum + 2, 10), 55)
            sheet.column_dimensions[column_cells[0].column_letter].width = width
    workbook.save(path)


def _summary_by(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return pd.DataFrame(columns=[column, "jobs", "critical_high", "newest_posting"])
    active = frame.copy()
    active[column] = active[column].fillna("").astype(str).replace("", "Unspecified")
    grouped = active.groupby(column, dropna=False)
    summary = grouped.size().rename("jobs").to_frame()
    summary["critical_high"] = grouped["priority"].apply(
        lambda values: int(values.isin(["critical", "high"]).sum())
    )
    summary["newest_posting"] = grouped["published_at"].max()
    return summary.reset_index().sort_values(
        ["critical_high", "jobs", column],
        ascending=[False, False, True],
    )


def export_excel(db_path: str | Path, output_path: str | Path) -> Path:
    init_private_import_tables(db_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    jobs = pd.DataFrame(fetch_jobs(db_path))
    if jobs.empty:
        jobs = _empty_jobs_frame()
    jobs = enrich_jobs_frame(jobs)

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
        run_proof = pd.read_sql_query(
            "SELECT * FROM runs ORDER BY started_at DESC",
            connection,
        )

    employer_coverage, recruiter_coverage = registry_frames()
    statuses = jobs.get("application_status", pd.Series(dtype="string"))
    active_rows = jobs[~statuses.isin(["expired", "rejected"])]
    deduplicated, duplicate_variants = deduplicate_worldwide(active_rows)

    review_job_keys = set(
        private_imports.loc[
            private_imports.get("review_required", pd.Series(dtype="int64")).eq(1),
            "job_key",
        ].astype(str)
    )
    today = datetime.now(UTC).date().isoformat()
    found_dates = deduplicated.get("found_at", pd.Series(dtype="string")).astype(str)
    new_today = deduplicated[found_dates.str.startswith(today, na=False)]
    priorities = deduplicated.get("priority", pd.Series(dtype="string"))
    high_priority = deduplicated[priorities.isin(["critical", "high"])]

    raw_statuses = jobs.get("application_status", pd.Series(dtype="string"))
    confidence = jobs.get("contact_confidence", pd.Series(dtype="string"))
    job_keys = jobs.get("job_key", pd.Series(dtype="string")).astype(str)
    manual_review = jobs[
        confidence.isin(["PUBLIC_UNVERIFIED", "PATTERN_SUGGESTION"])
        | raw_statuses.eq("review_required")
        | job_keys.isin(review_job_keys)
    ]
    applied = jobs[raw_statuses.eq("applied")]
    follow_up = jobs[raw_statuses.eq("follow_up")]
    expired = jobs[raw_statuses.eq("expired")]
    emails = jobs.get("recruiter_email", pd.Series(dtype="string"))
    contacts = jobs[emails.fillna("").astype(str).str.len() > 0]

    daily_summary = daily_summary_frame(active_rows, deduplicated, source_health)
    country_summary = _summary_by(deduplicated, "country")
    company_summary = _summary_by(deduplicated, "company")

    sheets = {
        "Daily_Summary": daily_summary,
        "New_Today": new_today,
        "High_Priority": high_priority,
        "Worldwide_Dedup": deduplicated,
        "All_Active": deduplicated,
        "All_Source_Rows": active_rows,
        "Duplicate_Variants": duplicate_variants,
        "Manual_Review": manual_review,
        "Applied": applied,
        "Follow_Up": follow_up,
        "Expired": expired,
        "Recruiter_Contacts": contacts,
        "Country_Summary": country_summary,
        "Company_Summary": company_summary,
        "Employer_Coverage": employer_coverage,
        "Recruiter_Coverage": recruiter_coverage,
        "Source_Health": source_health,
        "Source_Evidence": source_evidence,
        "Private_Imports": private_imports,
        "Run_Proof": run_proof,
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
    if "Worldwide_Dedup" in workbook.sheetnames:
        header = [str(cell.value or "") for cell in next(workbook["Worldwide_Dedup"].rows)]
        required_columns = {
            "normalized_role",
            "country",
            "sector",
            "software",
            "closing_date",
            "source_category",
            "duplicate_group",
            "source_count",
            "duplicate_sources",
            "all_apply_urls",
        }
        absent = sorted(required_columns - set(header))
        if absent:
            errors.append(f"Worldwide_Dedup missing columns: {', '.join(absent)}")
    return errors
