# Piping-E3D-Job-Intelligence

Worldwide, local-first job intelligence, matching and tracking for piping, AVEVA E3D,
PDMS, SP3D, offshore, refinery, nuclear, energy and EPC opportunities.

> **Current implementation:** verified public-source collection, global profile and
> location matrices, employer and recruiter coverage registries, read-only Gmail job
> alert ingestion, private document/email/OCR imports, non-destructive cross-source
> deduplication, and one verified worldwide Excel workbook.

## Safety boundaries

- Use only official public pages, permitted feeds, sitemaps and documented APIs.
- Respect robots.txt, conservative request limits and platform terms.
- Never bypass CAPTCHA, login walls or access controls.
- Never commit Gmail OAuth files, CVs, application records, databases or evidence.
- Gmail access is local, user-authorized and read-only.
- OCR and inferred vacancy fields always require review.
- SQLite is the strict source of truth; Excel is the operating review output.

## Worldwide coverage model

### Active official employer sources

- McDermott — Oracle HCM
- Wood — Oracle HCM
- Petrofac — SelectMinds public pages
- Bechtel — SuccessFactors public pages
- Worley — Eightfold public pages

### Fully configured staged sources

- KBR
- AtkinsRealis
- Fluor
- Technip Energies
- Jacobs

Staged sources remain disabled until their exact public listing, pagination, detail,
evidence and failure-behavior proof passes.

### Recruiter and specialist coverage

The registry includes Airswift, NES Fircroft, Brunel, Petroplan, Orion, TRS Staffing,
MPH, Spencer Ogden, WRS, Matchtech, First Recruitment Group, Progressive Recruitment,
Energy Resourcing, Rigzone, Energy Jobline and Oil and Gas Job Search.

### Authorized alert coverage

Local Gmail OAuth imports user-authorized alerts from LinkedIn, Naukri, Indeed, Bayt,
GulfTalent, employers and recruiters without scraping authenticated pages.

## Implemented capabilities

- Worldwide role, skill, sector and location matrices
- Native Oracle HCM, Greenhouse, Lever and SmartRecruiters collectors
- Safe public HTML, RSS and sitemap collectors
- ATS/fallback registry for SuccessFactors, SelectMinds, Eightfold, Phenom, Workday,
  iCIMS, Taleo, Teamtailor, Workable and Ashby
- Stable strict database identity and evidence hashes
- Non-destructive cross-source duplicate grouping in Excel
- Explainable 0–100 profile scoring with reasons and gaps
- Text, PDF, Word, EML and image-OCR private imports
- Read-only Gmail OAuth job-alert import
- Daily GitHub public-source artifact at 09:00 Asia/Kolkata
- Windows one-command combined public/Gmail/private workbook runner
- Windows Task Scheduler installer

## Quick start on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,gmail]"
job-intel --db data/database/jobs.db init-db
```

## Build the worldwide workbook now

```powershell
.\scripts\run_worldwide_daily.ps1
```

Output:

```text
data\exports\Piping_E3D_Jobs.xlsx
```

Install the daily Windows task:

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

## Public collection only

```powershell
job-intel --db data/database/jobs.db collect `
  --sources config/sources.yaml `
  --evidence-dir data/raw `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Gmail alerts

Place the downloaded Desktop OAuth client file at:

```text
private-input\gmail_credentials.json
```

Then run:

```powershell
job-intel --db data/database/jobs.db import-gmail `
  --credentials private-input/gmail_credentials.json `
  --token private-output/gmail/token.json `
  --evidence-dir private-output/evidence `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

See `docs/GMAIL_ALERTS.md`.

## Private vacancy import

Place vacancy files under `private-input`, then run:

```powershell
.\scripts\run_private_import.ps1
```

Supported inputs:

- `.txt`, `.md`, `.csv`
- `.pdf`
- `.docx`
- `.eml`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`, `.bmp` with OCR

## Worldwide workbook

The workbook contains operating, proof and coverage sheets, including:

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
- `Recruiter_Contacts`
- `Country_Summary`
- `Company_Summary`
- `Employer_Coverage`
- `Recruiter_Coverage`
- `Source_Health`
- `Source_Evidence`
- `Private_Imports`
- `Run_Proof`

Derived fields include normalized role, country, sector, software, closing date,
employment type, remote type, source category, duplicate group, source count,
duplicate sources and all known application URLs.

## Verification

```powershell
job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

A failed or partial source remains visibly failed. The permanent daily workflow cannot
report success when collection, evidence, export or verification fails.

## Repository layout

```text
config/                     Role, location, source, ATS, employer and recruiter registries
src/job_intelligence/       Collectors, scoring, Gmail/private imports and workbook logic
tests/                      Unit, security, resilience and end-to-end tests
scripts/                    Windows and GitHub execution helpers
docs/                       Operation, safety and connector guides
.github/workflows/          CI and scheduled public collection
```

See `docs/WORLDWIDE_OPERATION.md` for the complete operating model.
