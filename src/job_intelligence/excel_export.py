from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font

from .database import JOB_COLUMNS, connect, fetch_jobs, init_database

REQUIRED_SHEETS = (
    "New_Today",
    "High_Priority",
    "All_Active",
    "Manual_Review",
    "Applied",
    "Follow_Up",
    "Expired",
    "Recruiter_Contacts",
    "Source_Health",
    "Run_Proof",
)


def _empty_jobs_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=JOB_COLUMNS)


def _format_workbook(path: Path) -> None:
    workbook = load_workbook(path)
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column_cells in sheet.columns:
            values = [str(cell.value or "") for cell in list(column_cells)[:200]]
            width = min(max(max((len(value) for value in values), default=0) + 2, 10), 55)
            sheet.column_dimensions[column_cells[0].column_letter].width = width
    workbook.save(path)


def export_excel(db_path: str | Path, output_path: str | Path) -> Path:
    init_database(db_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    jobs = pd.DataFrame(fetch_jobs(db_path))
    if jobs.empty:
        jobs = _empty_jobs_frame()

    today = datetime.now(UTC).date().isoformat()
    found_dates = jobs.get("found_at", pd.Series(dtype="string")).astype(str)
    new_today = jobs[found_dates.str.startswith(today, na=False)]
    high_priority = jobs[jobs.get("priority", pd.Series(dtype="string")).isin(["critical", "high"])]
    active = jobs[~jobs.get("application_status", pd.Series(dtype="string")).isin(["expired", "rejected"])]
    manual_review = jobs[
        jobs.get("contact_confidence", pd.Series(dtype="string")).isin(["PUBLIC_UNVERIFIED", "PATTERN_SUGGESTION"])
    ]
    applied = jobs[jobs.get("application_status", pd.Series(dtype="string")).eq("applied")]
    follow_up = jobs[jobs.get("application_status", pd.Series(dtype="string")).eq("follow_up")]
    expired = jobs[jobs.get("application_status", pd.Series(dtype="string")).eq("expired")]
    contacts = jobs[
        jobs.get("recruiter_email", pd.Series(dtype="string")).fillna("").astype(str).str.len() > 0
    ]

    with connect(db_path) as connection:
        source_health = pd.read_sql_query(
            "SELECT * FROM source_health ORDER BY last_attempt_at DESC", connection
        )
        run_proof = pd.read_sql_query("SELECT * FROM runs ORDER BY started_at DESC", connection)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        new_today.to_excel(writer, sheet_name="New_Today", index=False)
        high_priority.to_excel(writer, sheet_name="High_Priority", index=False)
        active.to_excel(writer, sheet_name="All_Active", index=False)
        manual_review.to_excel(writer, sheet_name="Manual_Review", index=False)
        applied.to_excel(writer, sheet_name="Applied", index=False)
        follow_up.to_excel(writer, sheet_name="Follow_Up", index=False)
        expired.to_excel(writer, sheet_name="Expired", index=False)
        contacts.to_excel(writer, sheet_name="Recruiter_Contacts", index=False)
        source_health.to_excel(writer, sheet_name="Source_Health", index=False)
        run_proof.to_excel(writer, sheet_name="Run_Proof", index=False)

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
    return errors
