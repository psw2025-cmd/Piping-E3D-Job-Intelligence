# Worldwide Operation

The system combines verified official public sources, configured staged ATS sources,
user-authorized Gmail alerts, private files and recruiter coverage into one daily workbook.

## One-command Windows run

```powershell
.\scripts\run_worldwide_daily.ps1
```

The runner performs these steps:

1. Collect every enabled official public source.
2. Import Gmail alerts when the local OAuth credential exists.
3. Export one worldwide deduplicated workbook.
4. Verify the database, public/private/Gmail evidence and workbook contract.

Install the recurring local task:

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

## Source states

- `active_supported`: enabled for daily public collection.
- `staged_source`: fully configured but disabled until exact live proof passes.
- `official_site_verified`: official career entry recorded; connector research remains.
- `connector_planned`: public portal recorded; source-specific configuration remains.
- `email_alert_ingestion_ready`: covered through local read-only Gmail OAuth.

A staged source must prove:

1. Public listing access without authentication bypass.
2. Bounded pagination that terminates and does not repeat pages.
3. Correct title, company, location and official application URL extraction.
4. Global role-profile filtering that rejects unrelated jobs.
5. Evidence retention with SHA-256 verification.
6. Visible failed or partial status when any source fails.
7. Full Ruff, pytest, CLI smoke, workbook and offline daily-bundle gates.

## ATS strategy

The connector registry covers Oracle HCM, Greenhouse, Lever, SmartRecruiters,
SuccessFactors, SelectMinds, Eightfold, Phenom, Workday, iCIMS, Taleo, Teamtailor,
Workable and Ashby.

The safe fallback order is:

1. Documented public API.
2. Official RSS, XML or sitemap.
3. Bounded official public HTML.
4. User-authorized Gmail alerts.
5. Private PDF, Word, EML, text or image import.

## Duplicate handling

SQLite keeps strict identity aliases, canonical URLs and source evidence. Excel adds a
second non-destructive grouping layer based on normalized role, company, location and
posting evidence.

- `Worldwide_Dedup` keeps the strongest representative row.
- `All_Source_Rows` retains every active database row.
- `Duplicate_Variants` retains every row from groups found through multiple sources.
- `all_apply_urls` preserves all known application links.

This avoids losing distinct requisitions while reducing repeated official, recruiter and
email-alert representations in the operating view.

## GitHub versus local operation

GitHub Actions processes only public sources and uploads a verified artifact. Gmail OAuth
credentials, CVs, private vacancy files, application status and local recruiter records
remain on the user's Windows computer.
