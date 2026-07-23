# Piping-E3D-Job-Intelligence

Worldwide, local-first job intelligence, matching and tracking for piping, AVEVA E3D,
PDMS, SP3D, offshore, refinery, nuclear, energy and EPC opportunities.

> **Implemented:** worldwide role/location taxonomies, verified official sources,
> staged ATS sources, recruiter coverage, read-only Gmail alerts, private document/email
> imports, strict database identity, cross-source workbook deduplication and one verified
> daily Excel tracker.

## Safety

- Use only official public pages, permitted feeds, sitemaps and documented APIs.
- Respect robots.txt, request limits and platform terms.
- Never bypass CAPTCHA, login walls or access controls.
- Gmail access is local, user-authorized and read-only.
- Never commit OAuth files, CVs, applications, databases or evidence.
- SQLite remains the strict source of truth; Excel is the operating review output.

## Official-source coverage

Enabled sources:

- McDermott — Oracle HCM
- Wood — Oracle HCM
- Bechtel — SAP SuccessFactors
- Petrofac — three SelectMinds channels
- Worley — Eightfold public pages

Configured but disabled until exact live proof passes:

- KBR
- AtkinsRealis
- Fluor
- Technip Energies
- Jacobs

The employer registry also tracks L&T Energy Hydrocarbon, Saipem, Kent, Aker Solutions,
Samsung E&A, JGC, Chiyoda, NPCC, Penspen, Bilfinger, MAIRE Tecnimont, Black & Veatch,
Burns & McDonnell, Hatch and Ramboll.

## Recruiters and alert sources

The recruiter registry includes Airswift, NES Fircroft, Brunel, Petroplan, Orion, TRS,
MPH, Spencer Ogden, WRS, Matchtech, First Recruitment Group, Progressive Recruitment,
Energy Resourcing, Rigzone, Energy Jobline and Oil and Gas Job Search.

Local Gmail OAuth imports user-authorized alerts from LinkedIn, Naukri, Indeed, Bayt,
GulfTalent, employers and recruiters without scraping authenticated pages.

## Quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,gmail]"
job-intel --db data/database/jobs.db init-db
```

## Build the worldwide workbook

```powershell
.\scripts\run_worldwide_daily.ps1
```

Output:

```text
data\exports\Piping_E3D_Jobs.xlsx
```

Install the Windows daily task:

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

## Gmail alerts

Save the Desktop OAuth client file as
`private-input\gmail_credentials.json`, then run:

```powershell
.\.venv\Scripts\python.exe scripts\import_gmail_alerts.py `
  --db data/database/jobs.db `
  --credentials private-input/gmail_credentials.json `
  --token private-output/gmail/token.json `
  --evidence-dir private-output/evidence `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Workbook

The daily workbook includes `Worldwide_Dedup`, `All_Source_Rows`,
`Duplicate_Variants`, country/company summaries, employer/recruiter coverage,
application tracking, source health, evidence, private imports and run proof.

The deduplicated view keeps the strongest representative row while preserving every
source variant and application URL. Database identity remains strict and non-destructive.

## Automatic GitHub collection

`daily-live-job-intelligence` runs every day at 09:00 Asia/Kolkata and uploads a
verified artifact. GitHub remains public-source-only; Gmail tokens and private records
stay local.

## Verification

```powershell
job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

A failed or partial source remains visibly failed. Collection, evidence, workbook or
verification failure cannot be reported as a successful daily run.
