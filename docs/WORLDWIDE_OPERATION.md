# Worldwide Job Intelligence Operation

## Scope

The system combines five evidence paths into one daily workbook:

1. Verified official employer sources enabled in `config/sources.yaml`.
2. Fully configured but disabled employer sources awaiting live proof.
3. User-authorized Gmail job alerts.
4. Private PDF, Word, EML, text and image vacancy imports.
5. Recruiter and specialist-portal coverage recorded in `config/recruiters.yaml`.

The system never bypasses login, CAPTCHA, robots.txt or access controls.

## One-command daily run on Windows

```powershell
.\scripts\run_worldwide_daily.ps1
```

The runner performs these steps in order:

1. Collect enabled official public sources.
2. Import Gmail alerts when local OAuth credentials exist.
3. Export one worldwide deduplicated workbook.
4. Verify the database, evidence hashes and workbook contract.

Output:

```text
data\exports\Piping_E3D_Jobs.xlsx
```

## Install the Windows daily task

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

The default local run time is 09:15. Change it explicitly when required:

```powershell
.\scripts\install_worldwide_daily_task.ps1 -RunTime "08:30"
```

## GitHub daily run

The GitHub workflow remains public-source-only. It does not receive Gmail tokens,
private vacancy evidence, CVs or application records. It creates a portable verified
artifact every day at 09:00 Asia/Kolkata.

## Source states

- `active_supported`: enabled and intended for daily collection.
- `staged_source`: fully configured but disabled until live proof passes.
- `connector_planned`: official portal recorded but source configuration is incomplete.
- `email_alert_ingestion_ready`: supported through local read-only Gmail OAuth.

A staged source must not be enabled until all of the following pass:

1. Listing page or documented feed is publicly accessible.
2. Pagination terminates correctly and does not repeat pages.
3. Job detail parsing produces title, company, location and official URL.
4. Profile filtering rejects unrelated vacancies.
5. Raw evidence is retained and its SHA-256 is recorded.
6. A failed source produces a visible failed or partial run.
7. Unit tests and the full GitHub Actions gate pass.

## Worldwide workbook

The workbook includes:

- `Daily_Summary`
- `New_Today`
- `High_Priority`
- `Worldwide_Dedup`
- `All_Active`
- `All_Source_Rows`
- `Duplicate_Variants`
- `Manual_Review`
- `Applied`
- `Follow_Up`
- `Expired`
- `Recruiter_Contacts`
- `Country_Summary`
- `Company_Summary`
- `Employer_Coverage`
- `Recruiter_Coverage`
- `Source_Health`
- `Source_Evidence`
- `Private_Imports`
- `Run_Proof`

Derived worldwide fields include normalized role, country, sector, software,
closing date, employment type, remote type, source category, duplicate group,
source count, duplicate sources and all known application URLs.

## Deduplication behavior

Database identity remains strict and non-destructive. The workbook adds a second,
non-destructive duplicate grouping layer based on normalized title, company, location
and posting evidence. `Worldwide_Dedup` keeps the strongest representative row while
`Duplicate_Variants` preserves every source variant and URL.

This prevents accidental loss when two employers use similar titles while still
combining the same vacancy found through official, recruiter and email sources.
